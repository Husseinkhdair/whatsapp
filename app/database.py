import asyncio
import json
import logging
import os
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

import motor.motor_asyncio
from pymongo.errors import PyMongoError

from app.config import DATA_DIR

logger = logging.getLogger("database")

DB_CONFIG_FILE = DATA_DIR / "db_config.json"

DEFAULT_MONGO_URI = os.getenv(
    "MONGODB_URI",
    "mongodb+srv://hussein:KbNmS.9u9%40sqgaJ@cluster0.476b6ge.mongodb.net/?retryWrites=true&w=majority"
)


class DatabaseManager:
    """Manages asynchronous MongoDB connection, settings persistence, and collections."""

    def __init__(self):
        self.uri: str = self._load_saved_uri()
        self.client: Optional[motor.motor_asyncio.AsyncIOMotorClient] = None
        self.db = None
        self.is_connected: bool = False
        self.last_error: Optional[str] = None
        self.db_name: str = "whatsapp_manager"

    def _load_saved_uri(self) -> str:
        """Loads MongoDB URI from local config or falls back to default."""
        if DB_CONFIG_FILE.exists():
            try:
                with open(DB_CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("mongo_uri", DEFAULT_MONGO_URI)
            except Exception as e:
                logger.error(f"Error reading {DB_CONFIG_FILE}: {e}")
        return DEFAULT_MONGO_URI

    def _save_uri(self, uri: str):
        """Saves MongoDB URI to config file."""
        try:
            with open(DB_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump({"mongo_uri": uri, "updated_at": datetime.now().isoformat()}, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save db config: {e}")

    async def connect(self):
        """Attempts to connect to MongoDB and ping the server."""
        if not self.uri:
            self.is_connected = False
            self.last_error = "لم يتم تحديد رابط قاعدة بيانات MongoDB"
            return False

        try:
            logger.info("Connecting to MongoDB Atlas...")
            # Set short timeout so it doesn't hang if credentials or network fail
            self.client = motor.motor_asyncio.AsyncIOMotorClient(
                self.uri,
                serverSelectionTimeoutMS=6000,
                connectTimeoutMS=6000,
            )
            self.db = self.client[self.db_name]
            await self.client.admin.command("ping")
            self.is_connected = True
            self.last_error = None
            logger.info("Connected to MongoDB successfully!")
            return True
        except Exception as e:
            self.is_connected = False
            self.last_error = str(e)
            logger.warning(f"Could not connect to MongoDB: {e}")
            return False

    async def disconnect(self):
        if self.client:
            self.client.close()
            self.client = None
        self.is_connected = False

    async def update_uri(self, new_uri: str) -> Dict[str, Any]:
        """Validates new URI, tests connection, and saves it if valid."""
        clean_uri = new_uri.strip()
        # Automatically encode unencoded @ in password if present
        # Format: mongodb+srv://user:pass@host/...
        if "@" in clean_uri:
            parts = clean_uri.split("@")
            if len(parts) > 2:
                # Multiple @ signs means password contains raw @
                prefix = "@".join(parts[:-1])
                host_part = parts[-1]
                if "://" in prefix:
                    proto, auth = prefix.split("://", 1)
                    if ":" in auth:
                        u, p = auth.split(":", 1)
                        clean_uri = f"{proto}://{u}:{urllib.parse.quote(p)}@{host_part}"

        # Test connection
        temp_client = motor.motor_asyncio.AsyncIOMotorClient(
            clean_uri,
            serverSelectionTimeoutMS=6000,
            connectTimeoutMS=6000,
        )
        try:
            await temp_client.admin.command("ping")
            temp_client.close()
        except Exception as e:
            temp_client.close()
            return {
                "success": False,
                "message": f"فشل الاتصال بقاعدة البيانات: {e}",
            }

        # Success - apply and persist
        await self.disconnect()
        self.uri = clean_uri
        self._save_uri(clean_uri)
        await self.connect()

        return {
            "success": True,
            "message": "تم تحديث رابط قاعدة البيانات والاتصال بنجاح! 🎉",
        }

    # Data Operations: Sessions
    async def save_session_meta(self, session_data: Dict[str, Any]):
        if not self.is_connected or self.db is None:
            return
        try:
            session_id = session_data["session_id"]
            await self.db.sessions.update_one(
                {"session_id": session_id},
                {"$set": {**session_data, "updated_at": datetime.now().isoformat()}},
                upsert=True,
            )
        except Exception as e:
            logger.error(f"MongoDB save session error: {e}")

    async def delete_session_meta(self, session_id: str):
        if not self.is_connected or self.db is None:
            return
        try:
            await self.db.sessions.delete_one({"session_id": session_id})
            await self.db.session_storage.delete_one({"session_id": session_id})
        except Exception as e:
            logger.error(f"MongoDB delete session error: {e}")

    # Data Operations: Browser Session State (Cookies/Tokens persistence in cloud)
    async def save_storage_state(self, session_id: str, state_dict: Dict[str, Any]):
        if not self.is_connected or self.db is None:
            return
        try:
            await self.db.session_storage.update_one(
                {"session_id": session_id},
                {"$set": {"state": state_dict, "updated_at": datetime.now().isoformat()}},
                upsert=True,
            )
            logger.info(f"Backed up browser tokens for {session_id} to MongoDB.")
        except Exception as e:
            logger.error(f"MongoDB storage state save error: {e}")

    async def get_storage_state(self, session_id: str) -> Optional[Dict[str, Any]]:
        if not self.is_connected or self.db is None:
            return None
        try:
            record = await self.db.session_storage.find_one({"session_id": session_id})
            if record and "state" in record:
                return record["state"]
        except Exception as e:
            logger.error(f"MongoDB storage state get error: {e}")
        return None

    # Data Operations: Message History
    async def log_message(self, log_entry: Dict[str, Any]):
        if not self.is_connected or self.db is None:
            return
        try:
            await self.db.message_logs.insert_one({
                **log_entry,
                "created_at": datetime.now().isoformat(),
            })
        except Exception as e:
            logger.error(f"MongoDB log message error: {e}")

    async def get_message_logs(self, session_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        if not self.is_connected or self.db is None:
            return []
        try:
            query = {"session_id": session_id} if session_id else {}
            cursor = self.db.message_logs.find(query, {"_id": 0}).sort("created_at", -1).limit(limit)
            return await cursor.to_list(length=limit)
        except Exception as e:
            logger.error(f"MongoDB get logs error: {e}")
            return []


db_manager = DatabaseManager()
