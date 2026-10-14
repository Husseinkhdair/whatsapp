import asyncio
from fastapi import APIRouter, HTTPException, status

from app.models import (
    SendMessageRequest,
    BulkMessageRequest,
    BulkMessageResponse,
    BulkMessageItem,
    ApiResponse,
)
from app.whatsapp_manager import whatsapp_manager

router = APIRouter(prefix="/api/sessions", tags=["التحكم وإرسال الرسائل (Messages API)"])


@router.post(
    "/{session_id}/send-message",
    response_model=ApiResponse,
    summary="إرسال رسالة واتساب عبر حساب محدد",
)
async def send_single_message(session_id: str, request: SendMessageRequest):
    """
    إرسال رسالة نصية إلى رقم هاتف محدد عبر الحساب المختار.
    - **session_id**: معرف الحساب المتصل.
    - **phone**: رقم المستلم الدولي (مثال: +966500000000 أو 9647700000000).
    - **message**: نص الرسالة.
    """
    session = whatsapp_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"الحساب '{session_id}' غير موجود.")

    if not session.is_running and not session.has_saved_session:
        raise HTTPException(
            status_code=400,
            detail=f"الحساب '{session_id}' لم يتم ربطه بواتساب بعد. يرجى مسح رمز QR لربطه أولاً.",
        )

    try:
        result = await session.send_message(request.phone, request.message)
        return ApiResponse(
            success=True,
            message="تم إرسال الرسالة بنجاح عبر واتساب ويب",
            data=result,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"فشل إرسال الرسالة: {e}")


@router.post(
    "/{session_id}/send-bulk",
    response_model=ApiResponse,
    summary="إرسال رسائل جماعية إلى عدة أرقام مع فاصل زمني",
)
async def send_bulk_messages(session_id: str, request: BulkMessageRequest):
    """
    إرسال رسالة موحدة إلى قائمة أرقام هواتف، مع تطبيق فاصل زمني تلقائي بين الرسائل لتفادي حظر الحساب.
    """
    session = whatsapp_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"الحساب '{session_id}' غير موجود.")

    if not session.is_running and not session.has_saved_session:
        raise HTTPException(
            status_code=400,
            detail=f"الحساب '{session_id}' لم يتم ربطه بواتساب بعد. يرجى مسح رمز QR لربطه أولاً.",
        )

    results = []
    sent_count = 0
    failed_count = 0

    for i, phone in enumerate(request.phones):
        try:
            await session.send_message(phone, request.message)
            results.append(BulkMessageItem(phone=phone, status="SENT"))
            sent_count += 1
        except Exception as e:
            results.append(BulkMessageItem(phone=phone, status="FAILED", error=str(e)))
            failed_count += 1

        # Apply delay between messages if there are remaining phones
        if i < len(request.phones) - 1:
            await asyncio.sleep(request.delay_seconds or 3.0)

    summary_data = BulkMessageResponse(
        total=len(request.phones),
        sent_count=sent_count,
        failed_count=failed_count,
        results=results,
    )

    return ApiResponse(
        success=True,
        message=f"اكتملت الحملة: تم إرسال {sent_count} وفشل {failed_count}",
        data=summary_data.model_dump(),
    )
