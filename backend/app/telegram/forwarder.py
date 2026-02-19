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
    InputMediaUploadedDocument,
    InputMediaUploadedPhoto,
    InputPhoto,
    InputSingleMedia,
    MessageMediaDocument,
    MessageMediaPhoto,
)

from app.core.events import event_bus
from app.models.message import ContentType, MessageLog, MessageStatus
from app.telegram.fast_transfer import parallel_download_media, parallel_upload_file

logger = logging.getLogger(__name__)

ALBUM_WAIT_SECONDS = 1.5
PHOTO_SIZE_LIMIT = 10 * 1024 * 1024  # 10MB, Telegram 照片上传限制


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
        logger.info("[规则 %d] 转发消息 %d (类型=%s)", rule_id, message.id, content_type.value)

        async with self._session_factory() as session:
            log = MessageLog(
                rule_id=rule_id,
                source_msg_id=message.id,
                content_type=content_type,
                status=MessageStatus.PENDING,
                text_preview=(message.text or "")[:200] or None,
            )
            session.add(log)

            try:
                result = await self._try_forward(message, target_chat, rule_id=rule_id)
                log.target_msg_id = result.id if result else None
                log.status = MessageStatus.SUCCESS
                logger.info("[规则 %d] 消息 %d -> 转发成功 (类型=%s)", rule_id, message.id, content_type.value)
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
                logger.error("[规则 %d] 消息 %d 转发失败: %s", rule_id, message.id, e)
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
        # S1: 直接转发
        try:
            result = await self.client.forward_messages(target_chat, message)
            logger.info("[规则 %d] S1 直接转发消息 %d -> 成功", rule_id, message.id)
            return result[0] if isinstance(result, list) else result
        except Exception as e:
            logger.info("[规则 %d] S1 失败消息 %d: %s, 尝试 S2...", rule_id, message.id, e)

        # S2: 原始 MTProto 协议
        if message.media:
            try:
                result = await self._raw_send_media(message, target_chat)
                if result:
                    logger.info("[规则 %d] S2 原始协议消息 %d -> 成功", rule_id, message.id)
                    return result
            except Exception as e:
                logger.info("[规则 %d] S2 失败消息 %d: %s, 尝试 S3...", rule_id, message.id, e)

        # S3: 下载 → 重传（保留元数据）
        if message.media:
            logger.info("[规则 %d] S3 下载消息 %d...", rule_id, message.id)
            data = await parallel_download_media(self.client, message)
            if data:
                media_attrs = _extract_media_attrs(message)
                file_name = media_attrs.get("file_name", _guess_upload_name(message))
                is_video = bool(message.video or message.video_note)
                thumb = await _download_thumb(self.client, message)

                upload_file = _named_bytes_io(data, file_name)

                send_kwargs = {
                    "caption": message.text or "",
                    "formatting_entities": message.entities,
                }

                if thumb:
                    send_kwargs["thumb"] = _named_bytes_io(thumb, "thumb.jpg")

                if is_video:
                    send_kwargs["supports_streaming"] = True

                if media_attrs.get("duration") is not None:
                    send_kwargs["duration"] = media_attrs["duration"]
                    if media_attrs.get("voice"):
                        send_kwargs["voice_note"] = True
                    if media_attrs.get("w"):
                        send_kwargs["width"] = media_attrs["w"]
                        send_kwargs["height"] = media_attrs["h"]

                if media_attrs.get("title"):
                    send_kwargs["title"] = media_attrs["title"]
                if media_attrs.get("performer"):
                    send_kwargs["performer"] = media_attrs["performer"]

                send_kwargs = {k: v for k, v in send_kwargs.items() if v is not None}

                force_document = False
                if message.photo and len(data) > PHOTO_SIZE_LIMIT:
                    force_document = True
                    logger.info("[规则 %d] 消息 %d 照片超过10MB, 改为文档发送", rule_id, message.id)

                result = await self.client.send_file(target_chat, upload_file, force_document=force_document, **send_kwargs)
                logger.info(
                    "[规则 %d] S3 下载重传成功消息 %d (封面=%s, 时长=%s)",
                    rule_id, message.id, thumb is not None, media_attrs.get("duration"),
                )
                return result

        # S4: 纯文本
        if message.text:
            logger.info("[规则 %d] S4 纯文本消息 %d -> 发送", rule_id, message.id)
            return await self.client.send_message(
                target_chat,
                message.text,
                formatting_entities=message.entities,
            )

        raise RuntimeError(f"不支持的消息类型 msg {message.id}")

    # ── 相册处理 ──────────────────────────────────────────────

    async def forward_album(self, messages: list, target_chat: int, rule_id: int) -> None:
        """同步模式: 直接转发完整相册, 为每条消息创建 MessageLog."""
        messages = sorted(messages, key=lambda m: m.id)
        logger.info("[规则 %d] 转发相册 (%d 条), msg_ids=%s", rule_id, len(messages), [m.id for m in messages])

        async with self._session_factory() as session:
            logs = []
            for msg in messages:
                log = MessageLog(
                    rule_id=rule_id,
                    source_msg_id=msg.id,
                    content_type=ContentType.ALBUM,
                    status=MessageStatus.PENDING,
                    text_preview=(msg.text or "")[:200] or None,
                )
                session.add(log)
                logs.append(log)

            try:
                results = await self._try_forward_album(messages, target_chat, rule_id=rule_id)
                first = results[0] if isinstance(results, list) and results else results
                target_msg_id = first.id if first else None
                for log in logs:
                    log.target_msg_id = target_msg_id
                    log.status = MessageStatus.SUCCESS
                logger.info("[规则 %d] 相册 (%d 条) -> 转发成功", rule_id, len(messages))
                await event_bus.publish({
                    "type": "forward_result",
                    "rule_id": rule_id,
                    "source_msg_id": messages[0].id,
                    "target_msg_id": target_msg_id,
                    "status": "success",
                    "content_type": ContentType.ALBUM.value,
                    "error": None,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
            except Exception as e:
                for log in logs:
                    log.status = MessageStatus.FAILED
                    log.error = str(e)[:500]
                logger.error("[规则 %d] 相册转发失败: %s", rule_id, e)
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
                raise

            await session.commit()

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
                text_preview=(messages[0].text or "")[:200] or None,
            )
            session.add(log)

            try:
                results = await self._try_forward_album(messages, target_chat, rule_id=rule_id)
                first = results[0] if isinstance(results, list) and results else results
                log.target_msg_id = first.id if first else None
                log.status = MessageStatus.SUCCESS
                logger.info("[规则 %d] 相册 (%d 条) -> 转发成功", rule_id, len(messages))
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
                logger.error("[规则 %d] 相册转发失败: %s", rule_id, e)
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
        # S1: 直接转发
        try:
            result = await self.client.forward_messages(target_chat, messages)
            logger.info("[规则 %d] S1 直接转发相册 (%d 条) -> 成功", rule_id, len(messages))
            return result
        except Exception as e:
            logger.info("[规则 %d] S1 相册失败: %s, 尝试 S2...", rule_id, e)

        # S2: 原始 MTProto 协议
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
                logger.info("[规则 %d] S2 原始协议相册 (%d 条) -> 成功", rule_id, len(messages))
                return result
            except Exception as e:
                logger.info("[规则 %d] S2 相册失败: %s, 尝试 S3...", rule_id, e)

        # S3: 下载 → 重传 (保留视频元数据和缩略图)
        target = await self.client.get_input_entity(target_chat)
        multi_media = []

        for msg in messages:
            if not msg.media:
                continue
            data = await parallel_download_media(self.client, msg)
            if not data:
                continue

            media_attrs = _extract_media_attrs(msg)
            file_name = media_attrs.get("file_name", _guess_upload_name(msg))
            is_video = bool(msg.video or msg.video_note)

            uploaded = await parallel_upload_file(self.client, data, file_name)

            if msg.photo and len(data) <= PHOTO_SIZE_LIMIT:
                input_media = InputMediaUploadedPhoto(file=uploaded)
            else:
                attributes = [DocumentAttributeFilename(file_name=file_name)]
                mime_type = "application/octet-stream"
                thumb_uploaded = None

                if is_video:
                    attributes.append(DocumentAttributeVideo(
                        duration=int(media_attrs.get("duration", 0)),
                        w=media_attrs.get("w", 0),
                        h=media_attrs.get("h", 0),
                        supports_streaming=True,
                    ))
                    mime_type = "video/mp4"
                    thumb_data = await _download_thumb(self.client, msg)
                    if thumb_data:
                        thumb_uploaded = await self.client.upload_file(
                            _named_bytes_io(thumb_data, "thumb.jpg")
                        )
                elif msg.photo:
                    mime_type = "image/jpeg"
                elif hasattr(msg.media, "document") and msg.media.document:
                    mime_type = msg.media.document.mime_type or mime_type

                input_media = InputMediaUploadedDocument(
                    file=uploaded,
                    mime_type=mime_type,
                    attributes=attributes,
                    thumb=thumb_uploaded,
                )

            multi_media.append(InputSingleMedia(
                media=input_media,
                message=msg.text or "",
                random_id=helpers.generate_random_long(),
                entities=msg.entities,
            ))

        if multi_media:
            logger.info("[规则 %d] S3 相册下载重传 (%d 个文件) -> 发送中", rule_id, len(multi_media))
            result = await self.client(SendMultiMediaRequest(
                peer=target,
                multi_media=multi_media,
            ))
            return result

        raise RuntimeError("相册转发失败: 无媒体内容")
