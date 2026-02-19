import os
import sqlite3

from telethon import TelegramClient

from app.core.config import settings


def create_client() -> TelegramClient:
    session_path = f"sessions/{settings.session_name}"
    os.makedirs("sessions", exist_ok=True)

    db = sqlite3.connect(f"{session_path}.session")
    db.execute("PRAGMA journal_mode=WAL")
    db.close()

    return TelegramClient(
        session_path,
        settings.api_id,
        settings.api_hash,
    )
