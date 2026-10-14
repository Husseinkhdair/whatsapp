import asyncio
import base64
import json
import logging
import os
import re
import shutil
import sys
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from playwright.async_api import (
    async_playwright,
    Playwright,
    BrowserContext,
    Page,
    Error as PlaywrightError,
    TimeoutError as PlaywrightTimeoutError,
)

from app.config import (
    SESSIONS_DIR,
    SESSIONS_META_FILE,
    DEFAULT_HEADLESS,
    WHATSAPP_WEB_URL,
    PLAYWRIGHT_ARGS,
    AUTO_SLEEP_SECONDS,
    get_session_user_agent,
)
from app.models import SessionStatusEnum
from app.database import db_manager

logger = logging.getLogger("whatsapp_manager")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


class WhatsAppSession:
    """Manages an individual WhatsApp Web browser session with persistence."""

    def __init__(
        self,
        session_id: str,
        name: str,
        description: Optional[str] = None,
        headless: Optional[bool] = None,
        created_at: Optional[str] = None,
    ):
        self.session_id = session_id
        self.name = name
        self.description = description
        self.headless = DEFAULT_HEADLESS if headless is None else headless
        self.created_at = created_at or datetime.now().isoformat()
        self.last_active: Optional[str] = None
        self.phone_number: Optional[str] = None
        self.push_name: Optional[str] = None

        self.status = SessionStatusEnum.OFFLINE
        self.error_message: Optional[str] = None
        self.qr_code_base64: Optional[str] = None
        self.last_qr_update: Optional[float] = None

        self.user_data_dir = SESSIONS_DIR / session_id / "user_data"
        self.user_data_dir.mkdir(parents=True, exist_ok=True)

        self._playwright: Optional[Playwright] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._monitor_task: Optional[asyncio.Task] = None
        self._idle_task: Optional[asyncio.Task] = None
        self._send_lock = asyncio.Lock()
        self._is_closing = False

    def _reset_idle_sleep(self):
        """Schedule automatic shutdown of Chromium if idle to free 100% RAM."""
        if self._idle_task and not self._idle_task.done():
            self._idle_task.cancel()
        if AUTO_SLEEP_SECONDS > 0:
            self._idle_task = asyncio.create_task(self._auto_sleep_worker())

    async def _auto_sleep_worker(self):
        try:
            await asyncio.sleep(AUTO_SLEEP_SECONDS)
            if self.is_running and not self._send_lock.locked():
                logger.info(f"Session {self.session_id} has been idle for {AUTO_SLEEP_SECONDS}s. Sleeping browser to release RAM...")
                await self.stop()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug(f"Auto-sleep worker error: {e}")

    @property
    def is_running(self) -> bool:
        return self._context is not None and self.status != SessionStatusEnum.OFFLINE

    @property
    def has_saved_session(self) -> bool:
        """Check if persistent storage exists for this session."""
        return self.user_data_dir.exists() and any(self.user_data_dir.iterdir())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "name": self.name,
            "description": self.description,
            "status": self.status,
            "phone_number": self.phone_number,
            "push_name": self.push_name,
            "created_at": self.created_at,
            "last_active": self.last_active,
            "is_running": self.is_running,
            "has_saved_session": self.has_saved_session,
            "headless": self.headless,
            "error_message": self.error_message,
        }

    async def start(self) -> bool:
        """Start or restart the browser context and navigate to WhatsApp Web."""
        if self.is_running:
            logger.info(f"Session {self.session_id} is already running.")
            return True

        self._is_closing = False
        self.status = SessionStatusEnum.STARTING
        self.error_message = None
        self.qr_code_base64 = None

        try:
            logger.info(f"Starting session {self.session_id} (Headless: {self.headless})...")
            self._playwright = await async_playwright().start()

            # Dedicated isolated directories per session to prevent any data collisions
            cache_dir = self.user_data_dir.parent / "cache"
            crash_dir = self.user_data_dir.parent / "crashes"
            cache_dir.mkdir(parents=True, exist_ok=True)
            crash_dir.mkdir(parents=True, exist_ok=True)

            session_ua = get_session_user_agent(self.session_id)
            session_args = list(PLAYWRIGHT_ARGS) + [
                f"--disk-cache-dir={str(cache_dir.resolve())}",
                f"--crash-dumps-dir={str(crash_dir.resolve())}",
            ]

            self._context = await self._playwright.chromium.launch_persistent_context(
                user_data_dir=str(self.user_data_dir.resolve()),
                headless=self.headless,
                user_agent=session_ua,
                args=session_args,
                viewport={"width": 1280, "height": 800},
                accept_downloads=False,
                bypass_csp=True,
            )

            # Use existing page or create new one
            pages = self._context.pages
            self._page = pages[0] if pages else await self._context.new_page()

            # Navigate to WhatsApp Web
            await self._page.goto(WHATSAPP_WEB_URL, wait_until="domcontentloaded", timeout=60000)

            # Start background state monitor
            self._monitor_task = asyncio.create_task(self._monitor_loop())
            self.last_active = datetime.now().isoformat()
            return True

        except Exception as e:
            logger.error(f"Failed to start session {self.session_id}: {e}", exc_info=True)
            self.status = SessionStatusEnum.ERROR
            self.error_message = str(e)
            await self.stop()
            return False

    async def stop(self) -> bool:
        """Gracefully stop the browser context while preserving session data."""
        self._is_closing = True
        logger.info(f"Stopping session {self.session_id}...")

        if self._idle_task and not self._idle_task.done():
            self._idle_task.cancel()

        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

        try:
            if self._page and not self._page.is_closed():
                await self._page.close()
        except Exception:
            pass

        try:
            if self._context:
                await self._context.close()
        except Exception:
            pass

        try:
            if self._playwright:
                await self._playwright.stop()
        except Exception:
            pass

        self._page = None
        self._context = None
        self._playwright = None
        self.status = SessionStatusEnum.OFFLINE
        self.qr_code_base64 = None
        logger.info(f"Session {self.session_id} stopped.")
        return True

    async def _monitor_loop(self):
        """Monitors WhatsApp Web page state to update status and extract QR code."""
        while not self._is_closing:
            try:
                if not self._page or self._page.is_closed():
                    self.status = SessionStatusEnum.OFFLINE
                    break

                # 1. Check if logged in (Chats list or pane-side is visible)
                logged_in_selector = (
                    'div[id="pane-side"], div[data-testid="chat-list"], '
                    'div[aria-label="Chat list"], div[role="navigation"]'
                )
                logged_in_elem = await self._page.query_selector(logged_in_selector)

                if logged_in_elem:
                    if self.status != SessionStatusEnum.CONNECTED:
                        logger.info(f"Session {self.session_id} is now CONNECTED!")
                        self.status = SessionStatusEnum.CONNECTED
                        self.qr_code_base64 = None
                        self.last_active = datetime.now().isoformat()
                        # Try to detect profile info
                        await self._detect_profile_info()
                        # Save session state & metadata to MongoDB
                        try:
                            if self._context:
                                state_dict = await self._context.storage_state()
                                await db_manager.save_storage_state(self.session_id, state_dict)
                            await db_manager.save_session_meta(self.to_dict())
                        except Exception as sync_err:
                            logger.debug(f"MongoDB session backup error: {sync_err}")
                        # Start idle sleep countdown so browser doesn't stay open wasting RAM
                        self._reset_idle_sleep()

                    await asyncio.sleep(3)
                    continue

                # 2. Check for QR code element
                qr_canvas_selector = 'canvas[aria-label*="QR"], div[data-ref] canvas, canvas'
                qr_canvas = await self._page.query_selector(qr_canvas_selector)

                if qr_canvas and await qr_canvas.is_visible():
                    self.status = SessionStatusEnum.SCAN_QR
                    # Capture canvas screenshot directly as base64 image
                    try:
                        qr_bytes = await qr_canvas.screenshot()
                        self.qr_code_base64 = "data:image/png;base64," + base64.b64encode(qr_bytes).decode("utf-8")
                        self.last_qr_update = asyncio.get_event_loop().time()
                    except Exception as qr_err:
                        logger.debug(f"Could not take canvas screenshot: {qr_err}")

                    # Check for reload QR button (if QR expired)
                    reload_button = await self._page.query_selector(
                        'button:has-text("Click to reload"), [data-testid="popup-contents"] button, '
                        'span[data-icon="refresh"], button[aria-label="Reload QR code"]'
                    )
                    if reload_button and await reload_button.is_visible():
                        logger.info(f"QR code expired for {self.session_id}. Clicking reload button...")
                        await reload_button.click()

                    await asyncio.sleep(2)
                    continue

                # 3. Check for "WhatsApp is open in another window" / "Use Here" dialog
                use_here_btn = await self._page.query_selector(
                    'button:has-text("Use Here"), '
                    'button:has-text("استخدام هنا"), '
                    'div[role="button"]:has-text("Use Here"), '
                    'div[role="button"]:has-text("استخدام هنا")'
                )
                if use_here_btn and await use_here_btn.is_visible():
                    logger.info(f"Session {self.session_id}: Detected 'Use Here' prompt. Reclaiming active session...")
                    try:
                        await use_here_btn.click()
                        await asyncio.sleep(2)
                        continue
                    except Exception:
                        pass

                # 4. Check for loading progress bar / "Starting chat" / "Loading chats"
                loading_elem = await self._page.query_selector('progress, [data-testid="startup-progress"]')
                if loading_elem:
                    self.status = SessionStatusEnum.LOGGING_IN
                    await asyncio.sleep(2)
                    continue

                # 5. Check for true unlinked / logged out notification (ignore if Use Here button exists)
                if not use_here_btn:
                    logged_out_dialog = await self._page.query_selector(
                        'div[data-animate-modal-popup="true"]:has-text("Device was logged out"), '
                        'div[data-animate-modal-popup="true"]:has-text("You have been logged out"), '
                        'div[role="dialog"]:has-text("Logged out")'
                    )
                    if logged_out_dialog and await logged_out_dialog.is_visible():
                        logger.warning(f"Session {self.session_id} was logged out from device.")
                        self.status = SessionStatusEnum.DISCONNECTED
                        await asyncio.sleep(4)
                        continue

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"Monitor error in {self.session_id}: {e}")

            await asyncio.sleep(2)

    async def _detect_profile_info(self):
        """Attempt to extract phone number or push name from header or profile icon."""
        try:
            if not self._page or self._page.is_closed():
                return
            # WhatsApp stores my user info inside localStorage or state if available
            user_info = await self._page.evaluate("""
                () => {
                    try {
                        const keys = Object.keys(localStorage);
                        const userKey = keys.find(k => k.includes('last-wid') || k.includes('user'));
                        if (userKey) {
                            return localStorage.getItem(userKey);
                        }
                    } catch (e) {}
                    return null;
                }
            """)
            if user_info:
                # Often formatted like "1234567890@c.us"
                match = re.search(r'(\d{8,15})@', str(user_info))
                if match:
                    self.phone_number = match.group(1)
        except Exception:
            pass

    async def get_screenshot(self) -> bytes:
        """Capture screenshot of the current page for live visual inspection."""
        if not self._page or self._page.is_closed():
            raise RuntimeError("Session browser is not running.")
        return await self._page.screenshot(full_page=False)

    async def send_message(self, phone: str, message: str) -> Dict[str, Any]:
        """Send a WhatsApp message on-demand (wakes up browser if asleep, sleeps after)."""
        # Auto-wake if browser is currently stopped to save RAM
        if not self.is_running:
            if not self.has_saved_session:
                raise RuntimeError(
                    f"الحساب '{self.session_id}' لم يتم مسح رمز QR له بعد. يرجى مسح رمز QR لربطه أولاً."
                )
            logger.info(f"Session {self.session_id} is asleep. Waking up on-demand for API request...")
            started = await self.start()
            if not started:
                raise RuntimeError(f"فشل إيقاظ متصفح الجلسة: {self.error_message}")

            # Wait until CONNECTED (max 25s)
            for _ in range(25):
                if self.status == SessionStatusEnum.CONNECTED:
                    break
                await asyncio.sleep(1)

        if self.status != SessionStatusEnum.CONNECTED:
            raise RuntimeError(f"الحساب غير متصل حالياً (الحالة: {self.status}). يرجى التحقق من اتصال الهاتف.")

        clean_phone = re.sub(r"\D", "", phone)
        if len(clean_phone) < 7:
            raise ValueError(f"Invalid phone number format: '{phone}'. Must include country code and digits.")

        async with self._send_lock:
            if not self._page or self._page.is_closed():
                raise RuntimeError("Session page is not available.")

            try:
                encoded_msg = urllib.parse.quote(message)
                send_url = f"https://web.whatsapp.com/send?phone={clean_phone}&text={encoded_msg}"

                logger.info(f"Fast dispatch for session {self.session_id} to {clean_phone}...")

                # Check if page is already on web.whatsapp.com - do instant SPA navigation instead of 20s full reload!
                try:
                    current_url = self._page.url or ""
                except Exception:
                    current_url = ""

                if "web.whatsapp.com" in current_url:
                    # Soft-navigate via client router: takes 300ms instead of 15 seconds!
                    await self._page.evaluate(f"""
                        () => {{
                            const target = "https://web.whatsapp.com/send?phone={clean_phone}&text={encoded_msg}";
                            let a = document.getElementById('_fast_wa_nav');
                            if (!a) {{
                                a = document.createElement('a');
                                a.id = '_fast_wa_nav';
                                document.body.appendChild(a);
                            }}
                            a.href = target;
                            a.click();
                        }}
                    """)
                else:
                    await self._page.goto(send_url, wait_until="domcontentloaded", timeout=30000)

                # Rapid parallel polling for send button or invalid number dialog (poll every 100ms, max 8s)
                send_button_selector = (
                    'span[data-icon="send"], '
                    'button[data-testid="compose-btn-send"], '
                    'button[aria-label="Send"], '
                    'button[aria-label="إرسال"]'
                )
                invalid_dialog_selector = 'div[data-animate-modal-popup="true"], div[role="dialog"]'

                found_button = None
                for _ in range(50):
                    # 1. Quick check for send button
                    btn = await self._page.query_selector(send_button_selector)
                    if btn and await btn.is_visible():
                        found_button = btn
                        break

                    # 2. Quick check for invalid phone popup
                    inv = await self._page.query_selector(invalid_dialog_selector)
                    if inv and await inv.is_visible():
                        try:
                            dialog_text = await self._page.evaluate("el => el.innerText", inv) or ""
                            if "invalid" in dialog_text.lower() or "غير صالح" in dialog_text:
                                ok_btn = await self._page.query_selector('div[role="dialog"] button, button:has-text("OK")')
                                if ok_btn:
                                    await ok_btn.click()
                                raise ValueError(f"Phone number '{clean_phone}' is not registered on WhatsApp or is invalid.")
                        except ValueError:
                            raise
                        except Exception:
                            pass

                    await asyncio.sleep(0.12)

                if found_button:
                    await found_button.click()
                else:
                    # Alternative: Focus text editor and press Enter
                    input_selector = (
                        'footer div[contenteditable="true"], '
                        'div[data-testid="conversation-compose-box-input"], '
                        'div[contenteditable="true"][data-tab="10"]'
                    )
                    chat_input = await self._page.query_selector(input_selector)
                    if chat_input and await chat_input.is_visible():
                        await chat_input.focus()
                        await self._page.keyboard.press("Enter")
                    else:
                        raise RuntimeError("Could not find message input box or send button.")

                # Short 0.5s pause to ensure WebSocket packet dispatched
                await asyncio.sleep(0.5)
                self.last_active = datetime.now().isoformat()

                result = {
                    "session_id": self.session_id,
                    "phone": clean_phone,
                    "status": "SENT",
                    "timestamp": datetime.now().isoformat(),
                    "message": message,
                }
                # Log message in MongoDB
                try:
                    await db_manager.log_message(result)
                except Exception as log_err:
                    logger.debug(f"MongoDB log message error: {log_err}")

                return result

            except Exception as e:
                logger.error(f"Error sending message in session {self.session_id} to {clean_phone}: {e}")
                # Log failed attempt
                try:
                    await db_manager.log_message({
                        "session_id": self.session_id,
                        "phone": clean_phone,
                        "status": "FAILED",
                        "timestamp": datetime.now().isoformat(),
                        "message": message,
                        "error": str(e),
                    })
                except Exception:
                    pass
                raise
            finally:
                # Reset idle timer to sleep browser after sending to release RAM!
                self._reset_idle_sleep()


class WhatsAppManager:
    """Coordinates and manages multiple WhatsApp accounts/sessions."""

    def __init__(self):
        self.sessions: Dict[str, WhatsAppSession] = {}
        self._load_saved_metadata()

    def _load_saved_metadata(self):
        """Loads sessions metadata from disk and prepares session instances."""
        if SESSIONS_META_FILE.exists():
            try:
                with open(SESSIONS_META_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for item in data:
                        session_id = item["session_id"]
                        self.sessions[session_id] = WhatsAppSession(
                            session_id=session_id,
                            name=item.get("name", session_id),
                            description=item.get("description"),
                            headless=item.get("headless", DEFAULT_HEADLESS),
                            created_at=item.get("created_at"),
                        )
                logger.info(f"Loaded {len(self.sessions)} sessions from metadata file.")
            except Exception as e:
                logger.error(f"Failed to load sessions metadata: {e}")

    def save_metadata(self):
        """Persists sessions registry metadata to disk."""
        try:
            records = [
                {
                    "session_id": s.session_id,
                    "name": s.name,
                    "description": s.description,
                    "headless": s.headless,
                    "created_at": s.created_at,
                }
                for s in self.sessions.values()
            ]
            with open(SESSIONS_META_FILE, "w", encoding="utf-8") as f:
                json.dump(records, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save sessions metadata: {e}")

    def get_all_sessions(self) -> List[Dict[str, Any]]:
        return [s.to_dict() for s in self.sessions.values()]

    def get_session(self, session_id: str) -> Optional[WhatsAppSession]:
        return self.sessions.get(session_id)

    def create_session(
        self,
        session_id: str,
        name: str,
        description: Optional[str] = None,
        headless: Optional[bool] = None,
    ) -> WhatsAppSession:
        if session_id in self.sessions:
            raise ValueError(f"Session with ID '{session_id}' already exists.")

        session = WhatsAppSession(
            session_id=session_id,
            name=name,
            description=description,
            headless=headless,
        )
        self.sessions[session_id] = session
        self.save_metadata()
        logger.info(f"Created new session record '{session_id}'.")
        # Save to MongoDB
        asyncio.create_task(db_manager.save_session_meta(session.to_dict()))
        return session

    async def delete_session(self, session_id: str) -> bool:
        session = self.sessions.get(session_id)
        if not session:
            raise KeyError(f"Session '{session_id}' not found.")

        # Stop browser if running
        await session.stop()

        # Delete user_data storage directory
        session_dir = SESSIONS_DIR / session_id
        if session_dir.exists():
            shutil.rmtree(session_dir, ignore_errors=True)

        # Remove from dictionary and save
        del self.sessions[session_id]
        self.save_metadata()
        # Delete from MongoDB
        await db_manager.delete_session_meta(session_id)
        logger.info(f"Deleted session '{session_id}' and all associated persistent data.")
        return True

    async def shutdown(self):
        """Stops all running sessions gracefully on server shutdown."""
        logger.info("Shutting down all WhatsApp sessions...")
        for session in list(self.sessions.values()):
            if session.is_running:
                await session.stop()


# Global Singleton Instance
whatsapp_manager = WhatsAppManager()
