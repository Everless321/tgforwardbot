from telethon import TelegramClient

from app.core.config import settings


def create_client() -> TelegramClient:
    return TelegramClient(
        settings.session_name,
        settings.api_id,
        settings.api_hash,
    )
