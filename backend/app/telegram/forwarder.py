import asyncio
import io
import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import async_sessionmaker
from telethon import TelegramClient, helpers
from telethon.tl.functions.messages import SendMediaRequest, SendMultiMediaRequest
from telethon.tl.types import (
    DocumentAttributeAudio,
    DocumentAttributeFilename,
    DocumentAttributeVideo,
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


def _guess_upload_name(message) -> str:
    file = getattr(message, "file", None)
    if file and getattr(file, "name", None):
        return file.name

    ext = None
    if file and getattr(file, "ext", None):
        ext = file.ext

    if not ext:
        if message.photo:
            ext = ".jpg"
        elif message.video or message.video_note:
            ext = ".mp4"
        elif message.audio or message.voice:
            ext = ".ogg"
        elif message.document:
            ext = ".bin"
        else:
            ext = ".bin"

    return f"msg_{message.id}{ext}"


def _named_bytes_io(data: bytes, filename: str) -> io.BytesIO:
    bio = io.BytesIO(data)
    bio.name = filename
    return bio


def _extract_media_attrs(message) -> dict:
    attrs = {}
    doc = getattr(getattr(message, "media", None), "document", None)
    if not doc:
        return attrs
    for attr in doc.attributes:
        if isinstance(attr, DocumentAttributeVideo):
            attrs["duration"] = attr.duration
            attrs["w"] = attr.w
            attrs["h"] = attr.h
            attrs["supports_streaming"] = getattr(attr, "supports_streaming", True)
        elif isinstance(attr, DocumentAttributeAudio):
            attrs["duration"] = attr.duration
            attrs["title"] = getattr(attr, "title", None)
            attrs["performer"] = getattr(attr, "performer", None)
            attrs["voice"] = getattr(attr, "voice", False)
        elif isinstance(attr, DocumentAttributeFilename):
            attrs["file_name"] = attr.file_name
    return attrs


async def _download_thumb(client, message) -> bytes | None:
    doc = getattr(getattr(message, "media", None), "document", None)
    if not doc or not getattr(doc, "thumbs", None):
        return None
    try:
        return await client.download_media(message, bytes, thumb=-1)
    except Exception:
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
        logger.info("[Rule %d] Forwarding msg %d (type=%s)", rule_id, message.id, content_type.value)

        async with self._session_factory() as session:
            log = MessageLog(
                rule_id=rule_id,
                source_msg_id=message.id,
                content_type=content_type,
                status=MessageStatus.PENDING,
            )
            session.add(log)

            try:
                result = await self._try_forward(message, target_chat, rule_id=rule_id)
                log.target_msg_id = result.id if result else None
                log.status = MessageStatus.SUCCESS
                logger.info("[Rule %d] msg %d -> target OK (type=%s)", rule_id, message.id, content_type.value)
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
                logger.error("[Rule %d] msg %d FAILED: %s", rule_id, message.id, e)
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

    async def _try_forward(self, message, target_chat: int, rule_id: int = 0):
        # S1: direct forward (unrestricted channels)
        try:
            result = await self.client.forward_messages(target_chat, message)
            logger.info("[Rule %d] S1 direct forward msg %d -> OK", rule_id, message.id)
            return result[0] if isinstance(result, list) else result
        except Exception as e:
            logger.info("[Rule %d] S1 failed msg %d: %s, trying S2...", rule_id, message.id, e)

        # S2: raw MTProto SendMediaRequest (bypass Telethon noforwards check)
        if message.media:
            try:
                result = await self._raw_send_media(message, target_chat)
                if result:
                    logger.info("[Rule %d] S2 raw MTProto msg %d -> OK", rule_id, message.id)
                    return result
            except Exception as e:
                logger.info("[Rule %d] S2 failed msg %d: %s, trying S3...", rule_id, message.id, e)

        # S3: download bytes → re-upload with metadata preserved
        if message.media:
            logger.info("[Rule %d] S3 downloading msg %d...", rule_id, message.id)
            data = await self.client.download_media(message, bytes)
            if data:
                media_attrs = _extract_media_attrs(message)
                file_name = media_attrs.get("file_name", _guess_upload_name(message))
                upload_file = _named_bytes_io(data, file_name)

                thumb = await _download_thumb(self.client, message)

                send_kwargs = {
                    "caption": message.text or "",
                    "formatting_entities": message.entities,
                }

                if thumb:
                    send_kwargs["thumb"] = _named_bytes_io(thumb, "thumb.jpg")

                if media_attrs.get("duration") is not None:
                    send_kwargs["duration"] = media_attrs["duration"]
                    if media_attrs.get("voice"):
                        send_kwargs["voice_note"] = True
                    if media_attrs.get("w"):
                        send_kwargs["width"] = media_attrs["w"]
                        send_kwargs["height"] = media_attrs["h"]
                        send_kwargs["supports_streaming"] = media_attrs.get("supports_streaming", True)

                if media_attrs.get("title"):
                    send_kwargs["title"] = media_attrs["title"]
                if media_attrs.get("performer"):
                    send_kwargs["performer"] = media_attrs["performer"]

                send_kwargs = {k: v for k, v in send_kwargs.items() if v is not None}

                result = await self.client.send_file(target_chat, upload_file, **send_kwargs)
                logger.info(
                    "[Rule %d] S3 download+reupload OK msg %d (thumb=%s, duration=%s)",
                    rule_id, message.id, thumb is not None, media_attrs.get("duration"),
                )
                return result

        # S4: text-only
        if message.text:
            logger.info("[Rule %d] S4 text-only msg %d -> sending", rule_id, message.id)
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
                results = await self._try_forward_album(messages, target_chat, rule_id=rule_id)
                first = results[0] if isinstance(results, list) and results else results
                log.target_msg_id = first.id if first else None
                log.status = MessageStatus.SUCCESS
                logger.info("[Rule %d] album (%d items) -> target OK", rule_id, len(messages))
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
                logger.error("[Rule %d] album FAILED: %s", rule_id, e)
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

    async def _try_forward_album(self, messages: list, target_chat: int, rule_id: int = 0) -> list:
        # S1: direct forward
        try:
            result = await self.client.forward_messages(target_chat, messages)
            logger.info("[Rule %d] S1 direct forward album (%d items) -> OK", rule_id, len(messages))
            return result
        except Exception as e:
            logger.info("[Rule %d] S1 album failed: %s, trying S2...", rule_id, e)

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
                logger.info("[Rule %d] S2 raw MTProto album (%d items) -> OK", rule_id, len(messages))
                return result
            except Exception as e:
                logger.info("[Rule %d] S2 album failed: %s, trying S3...", rule_id, e)

        # S3: download → re-upload with metadata preserved
        files = []
        caps = []
        for msg in messages:
            if msg.media:
                data = await self.client.download_media(msg, bytes)
                if data:
                    media_attrs = _extract_media_attrs(msg)
                    file_name = media_attrs.get("file_name", _guess_upload_name(msg))
                    files.append(_named_bytes_io(data, file_name))
                    caps.append(msg.text or "")

        if files:
            logger.info("[Rule %d] S3 album download+reupload (%d files) -> sending", rule_id, len(files))
            return await self.client.send_file(target_chat, files, caption=caps)

        raise RuntimeError("Album forward failed: no media found")
