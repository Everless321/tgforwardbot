import sqlite3

from telethon import TelegramClient

from app.core.config import settings


def create_client() -> TelegramClient:
    db = sqlite3.connect(f"{settings.session_name}.session")
    db.execute("PRAGMA journal_mode=WAL")
    db.close()

    return TelegramClient(
        settings.session_name,
        settings.api_id,
        settings.api_hash,
    )
