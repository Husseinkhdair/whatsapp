import io
from fastapi import APIRouter, HTTPException, Query, Response, status
from fastapi.responses import Response

from app.models import (
    CreateSessionRequest,
    SessionResponse,
    ApiResponse,
)
from app.whatsapp_manager import whatsapp_manager

router = APIRouter(prefix="/api/sessions", tags=["إدارة الجلسات والحسابات (Sessions)"])


@router.get("", response_model=ApiResponse, summary="عرض جميع حسابات الواتساب")
async def list_sessions():
    """استرجاع قائمة بجميع الحسابات المسجلة وحالاتها الحالية (متصل، قيد الفحص، غير متصل)."""
    sessions = whatsapp_manager.get_all_sessions()
    return ApiResponse(
        success=True,
        message=f"تم العثور على {len(sessions)} حساب",
        data=sessions,
    )


@router.post("", response_model=ApiResponse, status_code=status.HTTP_201_CREATED, summary="إنشاء حساب واتساب جديد")
async def create_session(request: CreateSessionRequest):
    """
    تسجيل جلسة/حساب واتساب جديد في النظام.
    - **session_id**: معرف فريد باللغة الإنجليزية (مثل: sales_1, support, acc_01).
    - **name**: الاسم التعريفي للحساب (مثل: حساب المبيعات الرئيسي).
    - **headless**: تشغيل المتصفح في الخلفية بدون واجهة مرئية (افتراضياً True).
    """
    try:
        session = whatsapp_manager.create_session(
            session_id=request.session_id,
            name=request.name,
            description=request.description,
            headless=request.headless,
        )
        return ApiResponse(
            success=True,
            message="تم إنشاء الحساب بنجاح، يمكنك الآن تشغيل الجلسة لمسح رمز QR",
            data=session.to_dict(),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"حدث خطأ أثناء إنشاء الحساب: {e}")


@router.get("/{session_id}", response_model=ApiResponse, summary="عرض تفاصيل حساب محدد")
async def get_session(session_id: str):
    """استعراض تفاصيل وبيانات حساب محدد وحالته اللحظية."""
    session = whatsapp_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"الحساب '{session_id}' غير موجود.")
    return ApiResponse(
        success=True,
        message="تم جلب بيانات الحساب",
        data=session.to_dict(),
    )


@router.post("/{session_id}/start", response_model=ApiResponse, summary="تشغيل جلسة الحساب ومزامنة المتصفح")
async def start_session(session_id: str):
    """
    بدء تشغيل المتصفح لحساب واتساب والانتقال إلى WhatsApp Web.
    - إذا كانت الجلسة مسجلة مسبقاً، سيتم الدخول تلقائياً دون طلب QR!
    - إذا كانت جلسة جديدة، سيتوفر رمز QR لمسحه بالكاميرا.
    """
    session = whatsapp_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"الحساب '{session_id}' غير موجود.")

    success = await session.start()
    if not success:
        raise HTTPException(
            status_code=500,
            detail=f"فشل تشغيل الجلسة: {session.error_message or 'خطأ غير معروف'}",
        )

    return ApiResponse(
        success=True,
        message="تم بدء تشغيل الجلسة بنجاح، يرجى متابعة حالة الـ QR أو الاتصال",
        data=session.to_dict(),
    )


@router.post("/{session_id}/stop", response_model=ApiResponse, summary="إيقاف جلسة الحساب مع حفظ البيانات")
async def stop_session(session_id: str):
    """إيقاف متصفح الجلسة مؤقتاً مع الحفاظ الكامل على الجلسة وملفات تعريف الارتباط مسجلة الدخول."""
    session = whatsapp_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"الحساب '{session_id}' غير موجود.")

    await session.stop()
    return ApiResponse(
        success=True,
        message="تم إيقاف الجلسة بنجاح مع بقاء البيانات محفوظة",
        data=session.to_dict(),
    )


@router.post("/{session_id}/restart", response_model=ApiResponse, summary="إعادة تشغيل الجلسة")
async def restart_session(session_id: str):
    """إعادة تشغيل الجلسة لتحديث الاتصال."""
    session = whatsapp_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"الحساب '{session_id}' غير موجود.")

    await session.stop()
    success = await session.start()
    return ApiResponse(
        success=success,
        message="تمت إعادة تشغيل الجلسة",
        data=session.to_dict(),
    )


@router.delete("/{session_id}", response_model=ApiResponse, summary="حذف الحساب وجميع بياناته المخزنة")
async def delete_session(session_id: str):
    """حذف الحساب نهائياً ومسح بيانات الجلسة وسجل الدخول من الخادم."""
    try:
        await whatsapp_manager.delete_session(session_id)
        return ApiResponse(
            success=True,
            message=f"تم حذف الحساب '{session_id}' وجميع ملفات جلسته بنجاح",
        )
    except KeyError:
        raise HTTPException(status_code=404, detail=f"الحساب '{session_id}' غير موجود.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"حدث خطأ أثناء الحذف: {e}")


@router.get("/{session_id}/qr", summary="الحصول على رمز QR لمسح الحساب")
async def get_session_qr(
    session_id: str,
    format: str = Query("json", description="الصيغة المطلوبة: 'json' (base64) أو 'image' (صورة PNG مباشرة)"),
):
    """
    استرجاع رمز الاستجابة السريعة (QR Code) لربط الهاتف.
    - إذا كان الحساب متصلاً بالفعل، سيتم إشعارك بأنه متصل.
    - يمكن الحصول عليه بصيغة Data-URL Base64 أو كملف صورة PNG مباشرة.
    """
    session = whatsapp_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"الحساب '{session_id}' غير موجود.")

    if not session.is_running:
        raise HTTPException(
            status_code=400,
            detail="الجلسة غير مشغلة حالياً. يرجى طلب /start أولاً لتشغيل الجلسة وتوليد رمز QR.",
        )

    if session.status == "CONNECTED":
        return ApiResponse(
            success=True,
            message="الحساب متصل بالفعل ولا يتطلب مسح QR Code",
            data={"status": "CONNECTED", "qr_code": None},
        )

    qr_b64 = session.qr_code_base64
    if not qr_b64:
        return ApiResponse(
            success=False,
            message="جاري تحميل رمز QR من واتساب ويب، يرجى المحاولة بعد لحظات...",
            data={"status": session.status, "qr_code": None},
        )

    if format.lower() == "image":
        import base64
        # Extract binary png from data:image/png;base64,...
        header, b64_data = qr_b64.split(",", 1)
        image_bytes = base64.b64decode(b64_data)
        return Response(content=image_bytes, media_type="image/png")

    return ApiResponse(
        success=True,
        message="تم جلب رمز QR بنجاح",
        data={
            "status": session.status,
            "qr_code": qr_b64,
        },
    )


@router.get("/{session_id}/screenshot", summary="معاينة شاشة المتصفح المباشرة (Screenshot)")
async def get_session_screenshot(session_id: str):
    """التقاط صورة حية لشاشة WhatsApp Web في المتصفح للتأكد من الحالة وحل المشاكل."""
    session = whatsapp_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"الحساب '{session_id}' غير موجود.")

    if not session.is_running:
        raise HTTPException(status_code=400, detail="المتصفح غير قيد التشغيل حالياً.")

    try:
        screenshot_bytes = await session.get_screenshot()
        return Response(content=screenshot_bytes, media_type="image/png")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"فشل التقاط صورة الشاشة: {e}")
