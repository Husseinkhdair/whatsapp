import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import SERVER_HOST, SERVER_PORT
from app.routers.sessions import router as sessions_router
from app.routers.messages import router as messages_router
from app.whatsapp_manager import whatsapp_manager


import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup actions
    print("[INFO] WhatsApp Web Multi-Account Manager API is starting...")
    yield
    # Shutdown actions: Cleanly close any running browsers
    print("[INFO] Shutting down browser sessions safely...")
    await whatsapp_manager.shutdown()


app = FastAPI(
    title="WhatsApp Web Multi-Account Manager API",
    description="""
    نظام متكامل لإدارة عدة حسابات واتساب ويب (WhatsApp Web) في نفس الوقت:
    * **حفظ الجلسات تلقائياً**: لا حاجة لمسح رمز QR في كل مرة بعد تسجيل الدخول.
    * **واجهة تحكم ويب متطورة**: لعرض الحسابات وحالاتها ومسح QR وإرسال الرسائل.
    * **RESTful API شامل**: لإنشاء الحسابات، التحقق من الاتصال، التقاط صورة للشاشة، وإرسال الرسائل الفردية والجماعية.
    """,
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Enable CORS for external integrations
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API Routers
app.include_router(sessions_router)
app.include_router(messages_router)

# Mount Static Files (Frontend UI)
STATIC_DIR = Path(__file__).resolve().parent / "app" / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", include_in_schema=False)
async def serve_dashboard():
    """تقديم لوحة التحكم الرئيسية."""
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": "WhatsApp Multi-Account API is running. Visit /docs for API documentation."}


@app.get("/api/health", tags=["صحة الخادم (System)"], summary="فحص جاهزية الخادم")
async def health_check():
    """نقطة نهاية للتأكد من تشغيل النظام والاطلاع على عدد الحسابات وحالاتها."""
    sessions = whatsapp_manager.get_all_sessions()
    connected_count = sum(1 for s in sessions if s["status"] == "CONNECTED")
    running_count = sum(1 for s in sessions if s["is_running"])

    return {
        "status": "healthy",
        "total_accounts": len(sessions),
        "running_sessions": running_count,
        "connected_sessions": connected_count,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=SERVER_HOST, port=SERVER_PORT, reload=False)
