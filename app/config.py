import os
from pathlib import Path

# Base Paths
BASE_DIR = Path(__file__).resolve().parent.parent
data_env = os.getenv("DATA_DIR")
DATA_DIR = Path(data_env) if data_env else (BASE_DIR / "data")
SESSIONS_DIR = DATA_DIR / "sessions"
SESSIONS_META_FILE = DATA_DIR / "sessions.json"

# Ensure data directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

# Application Settings
DEFAULT_HEADLESS = os.getenv("WHATSAPP_HEADLESS", "true").lower() in ("true", "1", "yes")
SERVER_HOST = os.getenv("HOST", "0.0.0.0")
SERVER_PORT = int(os.getenv("PORT", "8000"))

# WhatsApp Web Configuration
WHATSAPP_WEB_URL = "https://web.whatsapp.com"

def get_session_user_agent(session_id: str) -> str:
    """Generate a realistic, distinct User-Agent per session to prevent device collision."""
    # Deterministic minor version variation based on session_id
    hash_seed = sum(ord(c) for c in session_id) % 20
    build_num = 6943 + hash_seed
    patch_num = 100 + hash_seed
    return (
        f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        f"AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/133.0.{build_num}.{patch_num} Safari/537.36"
    )

# Playwright launch arguments for maximum stealth, isolation, and minimal RAM
PLAYWRIGHT_ARGS = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-accelerated-2d-canvas",
    "--no-first-run",
    "--no-zygote",
    "--disable-gpu",
    "--disable-blink-features=AutomationControlled",
    "--disable-extensions",
    "--disable-default-apps",
    "--mute-audio",
    "--no-default-browser-check",
    "--disable-background-timer-throttling",
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
    "--disable-ipc-flooding-protection",
    "--js-flags=--max-old-space-size=256",
]
