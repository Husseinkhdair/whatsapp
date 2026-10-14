import asyncio
import logging
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, HTTPException, status

from app.models import (
    SendOtpRequest,
    SendOtpResponse,
    OtpAttemptDetail,
    ApiResponse,
)
from app.whatsapp_manager import whatsapp_manager
from app.database import db_manager

logger = logging.getLogger("otp_router")

router = APIRouter(prefix="/api/otp", tags=["بوابة إرسال OTP الذكية (Smart OTP Gateway)"])


@router.post(
    "/send",
    response_model=ApiResponse,
    summary="إرسال رمز OTP مع التبديل التلقائي بين الحسابات عند الفشل",
)
async def send_smart_otp(request: SendOtpRequest):
    """
    بوابة إرسال ذكية لرموز التحقق (OTP):
    1. تختار أول حساب واتساب جاهز وترسل من خلاله.
    2. إذا فشل الحساب الأول لأي سبب (انقطاع، حظر، خطأ، بطء)، يتم تسجيل الخطأ في التقرير والتبديل فوراً للحساب التالي.
    3. تستمر المحاولة بالتتابع حتى يتم تسليم الـ OTP بنجاح.
    4. يتم تسجيل تقرير كامل لكل محاولة والسبب في MongoDB.
    """
    # 1. Prepare final message text
    if request.message:
        final_text = request.message
    elif request.otp:
        final_text = (
            f"🔐 رمز التحقق الخاص بك هو: *{request.otp}*\n"
            f"يرجى عدم مشاركة هذا الرمز مع أي شخص لحماية حسابك."
        )
    else:
        raise HTTPException(
            status_code=400,
            detail="يجب إدخال إما رمز الـ OTP أو نص الرسالة المطلوب إرسالها.",
        )

    # 2. Collect candidate accounts
    all_sessions = whatsapp_manager.sessions.values()
    # Candidate accounts are those linked via QR (has_saved_session or currently running)
    ready_sessions = [s for s in all_sessions if s.has_saved_session or s.is_running]

    if not ready_sessions:
        raise HTTPException(
            status_code=400,
            detail="لا يوجد أي حساب واتساب مربوط وجاهز للإرسال حالياً. يرجى ربط حساب واحد على الأقل عبر مسح رمز QR.",
        )

    # Determine priority list
    candidates = []
    if request.account_priority:
        for acc_id in request.account_priority:
            matched = whatsapp_manager.get_session(acc_id)
            if matched and (matched.has_saved_session or matched.is_running):
                candidates.append(matched)
        # Append remaining ready sessions not explicitly listed
        for s in ready_sessions:
            if s not in candidates:
                candidates.append(s)
    else:
        candidates = ready_sessions

    attempts: List[OtpAttemptDetail] = []
    sent_by_account: Optional[str] = None

    logger.info(f"Starting Smart OTP Dispatch to {request.phone} with {len(candidates)} candidate accounts.")

    # 3. Failover Loop: Try accounts one by one
    for session in candidates:
        attempt_time = datetime.now().isoformat()
        try:
            logger.info(f"OTP Attempt: Trying account '{session.session_id}'...")
            res = await session.send_message(request.phone, final_text)

            attempts.append(OtpAttemptDetail(
                account_id=session.session_id,
                status="SUCCESS",
                error=None,
                timestamp=attempt_time,
            ))
            sent_by_account = session.session_id
            logger.info(f"OTP Success! Dispatched to {request.phone} via account '{sent_by_account}'.")
            break  # Dispatched successfully! Stop trying other accounts.

        except Exception as exc:
            error_msg = str(exc)
            logger.warning(
                f"OTP Attempt FAILED on account '{session.session_id}': {error_msg}. "
                f"Logging to report and switching to next available account..."
            )
            attempts.append(OtpAttemptDetail(
                account_id=session.session_id,
                status="FAILED",
                error=error_msg,
                timestamp=attempt_time,
            ))
            # Continue loop to next account

    # 4. Save comprehensive Failover Report to MongoDB
    is_success = sent_by_account is not None
    report_data = {
        "phone": request.phone,
        "otp_code": request.otp,
        "message": final_text,
        "sent_by_account": sent_by_account,
        "success": is_success,
        "total_attempts": len(attempts),
        "attempts": [a.model_dump() for a in attempts],
        "created_at": datetime.now().isoformat(),
    }
    await db_manager.log_otp_report(report_data)

    response_data = SendOtpResponse(
        phone=request.phone,
        sent_by_account=sent_by_account,
        attempts_count=len(attempts),
        attempts=attempts,
        message="تم تسليم رمز الـ OTP بنجاح" if is_success else "فشلت جميع الحسابات في إرسال رمز الـ OTP",
    )

    if not is_success:
        return ApiResponse(
            success=False,
            message=f"فشلت المحاولة على جميع الحسابات المتاحة ({len(attempts)} حساب). تم تسجيل المشاكل في التقرير.",
            data=response_data.model_dump(),
        )

    return ApiResponse(
        success=True,
        message=f"تم إرسال رمز التحقق OTP بنجاح عبر حساب '{sent_by_account}' بعد {len(attempts)} محاولة.",
        data=response_data.model_dump(),
    )


@router.get(
    "/reports",
    response_model=ApiResponse,
    summary="استعراض تقارير إرسال الـ OTP ومحاولات التبديل التلقائي",
)
async def get_otp_reports(limit: int = 50):
    """
    استعراض سجل تقارير الـ OTP، موضحاً الحساب الذي نجح في الإرسال والحسابات التي فشلت وسبب فشل كل منها.
    """
    reports = await db_manager.get_otp_reports(limit=limit)
    return ApiResponse(
        success=True,
        message=f"تم جلب {len(reports)} تقرير OTP",
        data=reports,
    )
