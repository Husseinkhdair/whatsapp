from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

class SessionStatusEnum:
    OFFLINE = "OFFLINE"
    STARTING = "STARTING"
    SCAN_QR = "SCAN_QR"
    LOGGING_IN = "LOGGING_IN"
    CONNECTED = "CONNECTED"
    DISCONNECTED = "DISCONNECTED"
    ERROR = "ERROR"

class CreateSessionRequest(BaseModel):
    session_id: str = Field(
        ...,
        min_length=2,
        max_length=50,
        pattern=r"^[a-zA-Z0-9_\-]+$",
        description="معرف الجلسة الفريد (حروف إنجليزية، أرقام، شرطة أو شرطة سفلية)"
    )
    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="اسم الحساب التعريفي (مثال: حساب المبيعات، الدعم الفني)"
    )
    description: Optional[str] = Field(None, max_length=255, description="وصف اختياري للحساب")
    headless: Optional[bool] = Field(None, description="تشغيل المتصفح في الخلفية (افتراضياً True)")

class SessionResponse(BaseModel):
    session_id: str
    name: str
    description: Optional[str] = None
    status: str
    phone_number: Optional[str] = None
    push_name: Optional[str] = None
    created_at: str
    last_active: Optional[str] = None
    is_running: bool
    has_saved_session: bool

class SendMessageRequest(BaseModel):
    phone: str = Field(
        ...,
        min_length=7,
        max_length=25,
        description="رقم الهاتف متضمناً مفتاح الدولة (مثال: 966500000000 أو +9647700000000)"
    )
    message: str = Field(
        ...,
        min_length=1,
        max_length=10000,
        description="نص الرسالة المراد إرسالها"
    )

class BulkMessageItem(BaseModel):
    phone: str
    status: str
    error: Optional[str] = None

class BulkMessageRequest(BaseModel):
    phones: List[str] = Field(..., min_length=1, max_length=500, description="قائمة أرقام الهواتف")
    message: str = Field(..., min_length=1, max_length=10000, description="نص الرسالة الموحدة")
    delay_seconds: Optional[float] = Field(3.0, ge=1.0, le=60.0, description="الفاصل الزمني بين كل رسالة والأخرى بالثواني")

class BulkMessageResponse(BaseModel):
    total: int
    sent_count: int
    failed_count: int
    results: List[BulkMessageItem]

class ApiResponse(BaseModel):
    success: bool
    message: str
    data: Optional[Any] = None

class SendOtpRequest(BaseModel):
    phone: str = Field(
        ...,
        min_length=7,
        max_length=25,
        description="رقم هاتف المستلم مع المفتاح الدولي"
    )
    otp: Optional[str] = Field(
        None,
        description="رمز التحقق (مثال: 123456). إذا تُرك فارغاً سيتم توليد رمز عشوائي من 6 أرقام تلقائياً"
    )
    message: Optional[str] = Field(
        None,
        description="نص الرسالة المخصص. إذا تُرك فارغاً سيتم استخدام القالب الافتراضي مع رمز الـ OTP"
    )
    expires_in_minutes: Optional[int] = Field(
        5,
        ge=1,
        le=60,
        description="مدة صلاحية رمز التحقق بالدقائق (افتراضياً 5 دقائق)"
    )
    account_priority: Optional[List[str]] = Field(
        None,
        description="ترتيب أولوية الحسابات المراد المحاولة بها. إذا تُركت فارغة، سيتم تجربة جميع الحسابات الجاهزة تلقائياً"
    )

class OtpAttemptDetail(BaseModel):
    account_id: str
    status: str
    error: Optional[str] = None
    timestamp: str

class SendOtpResponse(BaseModel):
    request_id: str
    phone: str
    otp: Optional[str] = None
    sent_by_account: Optional[str] = None
    expires_in_seconds: int = 300
    attempts_count: int
    attempts: List[OtpAttemptDetail]
    message: str

class VerifyOtpRequest(BaseModel):
    request_id: str = Field(..., description="معرف الطلب المستلم عند إرسال الـ OTP (مثال: req_9f8a12b3)")
    otp: str = Field(..., min_length=3, max_length=10, description="رمز الـ OTP المدخل من قبل المستخدم")

class VerifyOtpResponse(BaseModel):
    valid: bool
    success: bool = True
    request_id: str
    phone: Optional[str] = None
    message: str
    verified_at: Optional[str] = None
