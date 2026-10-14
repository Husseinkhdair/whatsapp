import asyncio
import logging
import secrets
from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import APIRouter, HTTPException, status

from app.models import (
    SendOtpRequest,
    SendOtpResponse,
    VerifyOtpRequest,
    VerifyOtpResponse,
    OtpAttemptDetail,
    ApiResponse,
)
from app.whatsapp_manager import whatsapp_manager
from app.database import db_manager

logger = logging.getLogger("otp_router")

router = APIRouter(prefix="/api/otp", tags=["بوابة إرسال والتحقق من OTP الذكية (Smart OTP Gateway)"])


@router.post(
    "/send",
    response_model=ApiResponse,
    summary="إرسال وتوليد رمز OTP تلقائي مع التبديل التلقائي بين الحسابات",
)
async def send_smart_otp(request: SendOtpRequest):
    """
    بوابة إرسال ذكية لرموز التحقق (OTP):
    1. تقوم بتوليد رمز OTP عشوائي تلقائياً (6 أرقام) إذا لم يُحدد العميل رمزاً.
    2. توليد معرف طلب فريد (request_id) يتم إرجاعه في الاستجابة وحفظه في MongoDB مع وقت انتهاء الصلاحية.
    3. تختار أول حساب واتساب جاهز وترسل من خلاله فوراً وبأقصى سرعة.
    4. إذا تعثر الحساب الأول، تسجل المشكلة وتنتقل تلقائياً للحساب التالي حتى يتم تسليم الرمز.
    5. يتم تسجيل تقرير كامل لكل محاولة في قاعدة البيانات.
    """
    # 1. Determine OTP code (Auto-generate 6-digit random code if not provided)
    raw_otp = request.otp.strip() if request.otp else ""
    if raw_otp:
        otp_code = raw_otp
    else:
        otp_code = f"{secrets.randbelow(900000) + 100000}"

    # 2. Generate unique request_id
    request_id = f"req_{secrets.token_hex(6)}"

    # 3. Determine expiration
    expires_minutes = request.expires_in_minutes or 5
    expires_at = datetime.now() + timedelta(minutes=expires_minutes)
    expires_in_seconds = expires_minutes * 60

    # 4. Prepare message text
    if request.message:
        if "{otp}" in request.message:
            final_text = request.message.replace("{otp}", otp_code)
        else:
            final_text = f"{request.message}\n\n🔐 كود التحقق: *{otp_code}*"
    else:
        final_text = (
            f"🔐 رمز التحقق الخاص بك هو: *{otp_code}*\n"
            f"صالح لمدة {expires_minutes} دقائق. يرجى عدم مشاركة هذا الرمز مع أي شخص لحماية حسابك."
        )

    # 5. Collect candidate accounts
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

    logger.info(f"Starting Smart OTP Dispatch to {request.phone} (ReqID: {request_id}, OTP: {otp_code}) with {len(candidates)} accounts.")

    # 6. Failover Loop: Try accounts sequentially
    for session in candidates:
        attempt_time = datetime.now().isoformat()
        try:
            logger.info(f"OTP Attempt: Trying account '{session.session_id}'...")
            await session.send_message(request.phone, final_text)

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

    is_success = sent_by_account is not None

    # 7. Store OTP verification record in MongoDB (and in-memory fallback)
    if is_success:
        verification_record = {
            "request_id": request_id,
            "phone": request.phone,
            "otp_code": otp_code,
            "status": "PENDING",
            "expires_at": expires_at.isoformat(),
            "created_at": datetime.now().isoformat(),
            "attempts_count": 0,
            "verified_at": None,
            "sent_by_account": sent_by_account,
        }
        await db_manager.save_otp_verification(verification_record)

    # 8. Save comprehensive Failover Report to MongoDB
    report_data = {
        "request_id": request_id,
        "phone": request.phone,
        "otp_code": otp_code,
        "message": final_text,
        "sent_by_account": sent_by_account,
        "success": is_success,
        "total_attempts": len(attempts),
        "attempts": [a.model_dump() for a in attempts],
        "created_at": datetime.now().isoformat(),
    }
    await db_manager.log_otp_report(report_data)

    response_data = SendOtpResponse(
        request_id=request_id,
        phone=request.phone,
        otp=otp_code,
        sent_by_account=sent_by_account,
        expires_in_seconds=expires_in_seconds,
        attempts_count=len(attempts),
        attempts=attempts,
        message="تم إرسال رمز الـ OTP بنجاح وحفظ طلب التحقق في قاعدة البيانات" if is_success else "فشلت جميع الحسابات في إرسال رمز الـ OTP",
    )

    if not is_success:
        return ApiResponse(
            success=False,
            message=f"فشلت المحاولة على جميع الحسابات المتاحة ({len(attempts)} حساب). تم تسجيل المشاكل في التقرير.",
            data=response_data.model_dump(),
        )

    return ApiResponse(
        success=True,
        message=f"تم إرسال رمز التحقق بنجاح عبر حساب '{sent_by_account}'. معرف الطلب: {request_id}",
        data=response_data.model_dump(),
    )


@router.post(
    "/verify",
    response_model=VerifyOtpResponse,
    summary="التحقق من صحة رمز الـ OTP المدخل ومطابقته في قاعدة البيانات",
)
async def verify_otp(request: VerifyOtpRequest):
    """
    التحقق من صحة رمز OTP المدخل:
    - يرسل العميل request_id و otp.
    - يتحقق النظام في قاعدة بيانات MongoDB:
      1. إذا كان طلب التحقق غير موجود -> valid: false
      2. إذا انتهت صلاحيته الزمنية -> valid: false
      3. إذا تم استخدامه وتوثيقه مسبقاً -> valid: false
      4. إذا كان الكود مطابقاً -> valid: true ويتم تعليم الطلب كـ VERIFIED
      5. إذا كان الكود خاطئاً -> valid: false
    """
    req_id = request.request_id.strip()
    user_otp = str(request.otp).strip()

    record = await db_manager.get_otp_verification(req_id)
    if not record:
        return VerifyOtpResponse(
            valid=False,
            success=False,
            request_id=req_id,
            message="طلب التحقق غير موجود أو غير صالح (request_id غير معرّف).",
        )

    phone = record.get("phone")

    # Check if already verified
    if record.get("status") == "VERIFIED":
        return VerifyOtpResponse(
            valid=False,
            success=False,
            request_id=req_id,
            phone=phone,
            message="تم استخدام رمز التحقق هذا مسبقاً ولا يمكن استخدامه مرة أخرى.",
            verified_at=record.get("verified_at"),
        )

    # Check expiration
    expires_at_str = record.get("expires_at")
    if expires_at_str:
        try:
            expires_at = datetime.fromisoformat(expires_at_str)
            if datetime.now() > expires_at:
                return VerifyOtpResponse(
                    valid=False,
                    success=False,
                    request_id=req_id,
                    phone=phone,
                    message="انتهت صلاحية رمز التحقق (انتهت المهلة الزمنية المحددة). يرجى طلب رمز جديد.",
                )
        except Exception:
            pass

    # Check OTP match
    expected_otp = str(record.get("otp_code", "")).strip()

    if expected_otp != user_otp:
        await db_manager.increment_otp_attempt(req_id)
        return VerifyOtpResponse(
            valid=False,
            success=False,
            request_id=req_id,
            phone=phone,
            message="رمز التحقق غير صحيح. يرجى التأكد وإعادة المحاولة.",
        )

    # Success: Mark as verified in DB
    verified_at = datetime.now().isoformat()
    await db_manager.mark_otp_verified(req_id, verified_at)

    return VerifyOtpResponse(
        valid=True,
        success=True,
        request_id=req_id,
        phone=phone,
        message="رمز التحقق صحيح ومطابق! تم تأكيد العملية بنجاح. ✅",
        verified_at=verified_at,
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

