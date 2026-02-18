import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import async_sessionmaker
from telethon import TelegramClient, helpers
from telethon.tl.functions.messages import SendMediaRequest, SendMultiMediaRequest
from telethon.tl.types import (
    InputDocument,
    InputMediaDocument,
    InputMediaPhoto,
    InputPhoto,
    InputSingleMedia,
    MessageMediaDocument,
    MessageMediaPhoto,
)

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


def _build_input_media(media):
    if isinstance(media, MessageMediaDocument) and media.document:
        doc = media.document
        return InputMediaDocument(
            id=InputDocument(
                id=doc.id,
                access_hash=doc.access_hash,
                file_reference=doc.file_reference,
            ),
            spoiler=False,
        )
    if isinstance(media, MessageMediaPhoto) and media.photo:
        photo = media.photo
        return InputMediaPhoto(
            id=InputPhoto(
                id=photo.id,
                access_hash=photo.access_hash,
                file_reference=photo.file_reference,
            ),
            spoiler=False,
        )
    return None


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
                logger.info("Forwarded msg %d -> %d (type=%s)", message.id, target_chat, content_type.value)
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

    async def _raw_send_media(self, message, target_chat: int):
        input_media = _build_input_media(message.media)
        if not input_media:
            return None
        target = await self.client.get_input_entity(target_chat)
        result = await self.client(SendMediaRequest(
            peer=target,
            media=input_media,
            message=message.text or "",
            random_id=helpers.generate_random_long(),
        ))
        return result

    async def _try_forward(self, message, target_chat: int):
        # S1: direct forward (unrestricted channels)
        try:
            result = await self.client.forward_messages(target_chat, message)
            logger.info("[S1] direct forward OK for msg %d", message.id)
            return result[0] if isinstance(result, list) else result
        except Exception as e:
            logger.info("[S1] failed msg %d: %s", message.id, e)

        # S2: raw MTProto SendMediaRequest (bypass Telethon noforwards check)
        if message.media:
            try:
                result = await self._raw_send_media(message, target_chat)
                if result:
                    logger.info("[S2] raw SendMediaRequest OK for msg %d", message.id)
                    return result
            except Exception as e:
                logger.info("[S2] raw SendMediaRequest failed msg %d: %s", message.id, e)

        # S3: download bytes → re-upload (last resort for media)
        if message.media:
            logger.info("[S3] downloading msg %d...", message.id)
            data = await self.client.download_media(message, bytes)
            if data:
                result = await self.client.send_file(
                    target_chat,
                    data,
                    caption=message.text or "",
                    formatting_entities=message.entities,
                )
                logger.info("[S3] download+reupload OK for msg %d", message.id)
                return result

        # S4: text-only
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
        # S1: direct forward
        try:
            return await self.client.forward_messages(target_chat, messages)
        except Exception:
            pass

        # S2: raw MTProto SendMultiMediaRequest (bypass noforwards)
        target = await self.client.get_input_entity(target_chat)
        multi_media = []
        for m in messages:
            if m.media:
                im = _build_input_media(m.media)
                if im:
                    multi_media.append(InputSingleMedia(
                        media=im,
                        message=m.text or "",
                        random_id=helpers.generate_random_long(),
                    ))
        if multi_media:
            try:
                result = await self.client(SendMultiMediaRequest(
                    peer=target,
                    multi_media=multi_media,
                ))
                logger.info("[S2] raw SendMultiMediaRequest OK for album")
                return result
            except Exception as e:
                logger.info("[S2] raw SendMultiMediaRequest failed: %s", e)

        # S3: download → re-upload (last resort)
        files = []
        caps = []
        for msg in messages:
            if msg.media:
                data = await self.client.download_media(msg, bytes)
                if data:
                    files.append(data)
                    caps.append(msg.text or "")

        if files:
            return await self.client.send_file(target_chat, files, caption=caps)

        raise RuntimeError("Album forward failed: no media found")
