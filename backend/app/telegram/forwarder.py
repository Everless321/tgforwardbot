import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import async_sessionmaker
from telethon import TelegramClient

from app.core.events import event_bus
from app.models.message import ContentType, MessageLog, MessageStatus

logger = logging.getLogger(__name__)

ALBUM_WAIT_SECONDS = 1.5


def detect_content_type(message) -> ContentType:
    if message.grouped_id:
        return ContentType.ALBUM
    if message.photo:
        return ContentType.PHOTO
    if message.gif:
        return ContentType.ANIMATION
    if message.video or message.video_note:
        return ContentType.VIDEO
    if message.audio:
        return ContentType.AUDIO
    if message.voice:
        return ContentType.VOICE
    if message.sticker:
        return ContentType.STICKER
    if message.document:
        return ContentType.DOCUMENT
    if message.text:
        return ContentType.TEXT
    return ContentType.OTHER


class MessageForwarder:
    def __init__(self, client: TelegramClient, session_factory: async_sessionmaker):
        self.client = client
        self._session_factory = session_factory
        self._album_cache: dict[int, dict] = {}
        self._album_tasks: dict[int, asyncio.Task] = {}

    async def forward(self, message, target_chat: int, rule_id: int) -> None:
        if message.grouped_id:
            await self._collect_album(message, target_chat, rule_id)
            return
        await self._forward_single(message, target_chat, rule_id)

    # ── single message ──────────────────────────────────────────────

    async def _forward_single(self, message, target_chat: int, rule_id: int) -> None:
        content_type = detect_content_type(message)

        async with self._session_factory() as session:
            log = MessageLog(
                rule_id=rule_id,
                source_msg_id=message.id,
                content_type=content_type,
                status=MessageStatus.PENDING,
            )
            session.add(log)

            try:
                result = await self._try_forward(message, target_chat)
                log.target_msg_id = result.id if result else None
                log.status = MessageStatus.SUCCESS
                logger.info("Forwarded msg %d -> %d", message.id, target_chat)
                await event_bus.publish({
                    "type": "forward_result",
                    "rule_id": rule_id,
                    "source_msg_id": message.id,
                    "target_msg_id": result.id if result else None,
                    "status": "success",
                    "content_type": content_type.value,
                    "error": None,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
            except Exception as e:
                log.status = MessageStatus.FAILED
                log.error = str(e)[:500]
                logger.error("Failed to forward msg %d: %s", message.id, e)
                await event_bus.publish({
                    "type": "forward_result",
                    "rule_id": rule_id,
                    "source_msg_id": message.id,
                    "target_msg_id": None,
                    "status": "failed",
                    "content_type": content_type.value,
                    "error": str(e)[:500],
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })

            await session.commit()

    async def _try_forward(self, message, target_chat: int):
        # Strategy 1: direct forward (unrestricted channels)
        try:
            result = await self.client.forward_messages(target_chat, message)
            return result[0] if isinstance(result, list) else result
        except Exception:
            pass

        # Strategy 2: send media reference (file_id, avoids re-upload)
        if message.media:
            try:
                return await self.client.send_file(
                    target_chat,
                    message.media,
                    caption=message.text or "",
                    formatting_entities=message.entities,
                )
            except Exception:
                pass

            # Strategy 3: download bytes → re-upload
            data = await self.client.download_media(message, bytes)
            if data:
                return await self.client.send_file(
                    target_chat,
                    data,
                    caption=message.text or "",
                    formatting_entities=message.entities,
                )

        # Strategy 4: text-only
        if message.text:
            return await self.client.send_message(
                target_chat,
                message.text,
                formatting_entities=message.entities,
            )

        raise RuntimeError(f"Unsupported message type for msg {message.id}")

    # ── album handling ──────────────────────────────────────────────

    async def _collect_album(self, message, target_chat: int, rule_id: int) -> None:
        gid = message.grouped_id
        if gid not in self._album_cache:
            self._album_cache[gid] = {
                "messages": [],
                "target_chat": target_chat,
                "rule_id": rule_id,
            }
        self._album_cache[gid]["messages"].append(message)

        if gid in self._album_tasks:
            self._album_tasks[gid].cancel()

        self._album_tasks[gid] = asyncio.create_task(self._flush_album(gid))

    async def _flush_album(self, grouped_id: int) -> None:
        await asyncio.sleep(ALBUM_WAIT_SECONDS)

        album = self._album_cache.pop(grouped_id, None)
        self._album_tasks.pop(grouped_id, None)
        if not album:
            return

        messages = sorted(album["messages"], key=lambda m: m.id)
        target_chat = album["target_chat"]
        rule_id = album["rule_id"]

        async with self._session_factory() as session:
            log = MessageLog(
                rule_id=rule_id,
                source_msg_id=messages[0].id,
                content_type=ContentType.ALBUM,
                status=MessageStatus.PENDING,
            )
            session.add(log)

            try:
                results = await self._try_forward_album(messages, target_chat)
                first = results[0] if isinstance(results, list) and results else results
                log.target_msg_id = first.id if first else None
                log.status = MessageStatus.SUCCESS
                logger.info("Forwarded album (%d items) -> %d", len(messages), target_chat)
                await event_bus.publish({
                    "type": "forward_result",
                    "rule_id": rule_id,
                    "source_msg_id": messages[0].id,
                    "target_msg_id": first.id if first else None,
                    "status": "success",
                    "content_type": ContentType.ALBUM.value,
                    "error": None,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
            except Exception as e:
                log.status = MessageStatus.FAILED
                log.error = str(e)[:500]
                logger.error("Failed to forward album: %s", e)
                await event_bus.publish({
                    "type": "forward_result",
                    "rule_id": rule_id,
                    "source_msg_id": messages[0].id,
                    "target_msg_id": None,
                    "status": "failed",
                    "content_type": ContentType.ALBUM.value,
                    "error": str(e)[:500],
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })

            await session.commit()

    async def _try_forward_album(self, messages: list, target_chat: int) -> list:
        # Strategy 1: direct forward
        try:
            return await self.client.forward_messages(target_chat, messages)
        except Exception:
            pass

        # Strategy 2: send media references as album
        try:
            files = [m.media for m in messages if m.media]
            captions = [m.text or "" for m in messages if m.media]
            if files:
                return await self.client.send_file(target_chat, files, caption=captions)
        except Exception:
            pass

        # Strategy 3: download all → re-upload as album
        files = []
        captions = []
        for msg in messages:
            if msg.media:
                data = await self.client.download_media(msg, bytes)
                if data:
                    files.append(data)
                    captions.append(msg.text or "")

        if files:
            return await self.client.send_file(target_chat, files, caption=captions)

        raise RuntimeError("Album forward failed: no media found")
