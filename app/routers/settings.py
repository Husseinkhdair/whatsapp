import re
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.database import db_manager
from app.models import ApiResponse

router = APIRouter(prefix="/api/database", tags=["إعدادات قاعدة البيانات (MongoDB)"])


class UpdateMongoUriRequest(BaseModel):
    mongo_uri: str = Field(
        ...,
        min_length=10,
        description="رابط الاتصال بقاعدة بيانات MongoDB (مثال: mongodb+srv://...)"
    )


def mask_uri(uri: str) -> str:
    """Masks password inside MongoDB URI for display security."""
    if not uri:
        return ""
    # Mask password pattern ://username:password@
    return re.sub(r"://([^:]+):([^@]+)@", r"://\1:******@", uri)


@router.get("/status", response_model=ApiResponse, summary="حالة الاتصال بـ MongoDB")
async def get_database_status():
    """استرجاع حالة الاتصال الحالية بقاعدة البيانات، والخطأ إن وجد."""
    return ApiResponse(
        success=True,
        message="تم جلب حالة قاعدة البيانات",
        data={
            "is_connected": db_manager.is_connected,
            "masked_uri": mask_uri(db_manager.uri),
            "raw_uri": db_manager.uri,
            "db_name": db_manager.db_name,
            "last_error": db_manager.last_error,
        },
    )


@router.post("/update", response_model=ApiResponse, summary="تعديل واختبار رابط MongoDB")
async def update_database_uri(request: UpdateMongoUriRequest):
    """
    تحديث رابط قاعدة بيانات MongoDB والاتصال بها مباشرة من لوحة التحكم.
    يقوم النظام باختبار الرابط أولاً قبل حفظه.
    """
    result = await db_manager.update_uri(request.mongo_uri)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])

    return ApiResponse(
        success=True,
        message=result["message"],
        data={
            "is_connected": db_manager.is_connected,
            "masked_uri": mask_uri(db_manager.uri),
        },
    )


@router.get("/logs", response_model=ApiResponse, summary="سجل الرسائل المرسلة المخزن في MongoDB")
async def get_message_logs(limit: int = 50):
    """استعراض سجل الرسائل التي تم إرسالها من جميع الحسابات المحفوظة في MongoDB."""
    logs = await db_manager.get_message_logs(limit=limit)
    return ApiResponse(
        success=True,
        message=f"تم جلب {len(logs)} سجل رسالة",
        data=logs,
    )
