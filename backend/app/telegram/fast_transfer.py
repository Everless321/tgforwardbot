# Parallel file transfer for Telethon
# Based on https://github.com/tulir/mautrix-telegram/blob/master/mautrix_telegram/util/parallel_file_transfer.py
# Copyright (C) 2021 Tulir Asokan - MIT License

import asyncio
import hashlib
import io
import logging
import math
import os
from typing import AsyncGenerator, Optional, Union

from telethon import TelegramClient, helpers, utils
from telethon.crypto import AuthKey
from telethon.network import MTProtoSender
from telethon.tl.alltlobjects import LAYER
from telethon.tl.functions import InvokeWithLayerRequest
from telethon.tl.functions.auth import (
    ExportAuthorizationRequest,
    ImportAuthorizationRequest,
)
from telethon.tl.functions.upload import (
    GetFileRequest,
    SaveBigFilePartRequest,
    SaveFilePartRequest,
)
from telethon.tl.types import (
    Document,
    InputDocumentFileLocation,
    InputFile,
    InputFileBig,
    InputFileLocation,
    InputPhotoFileLocation,
    TypeInputFile,
)

logger = logging.getLogger(__name__)

PARALLEL_SIZE_THRESHOLD = 10 * 1024 * 1024  # 10MB

TypeLocation = Union[
    Document, InputDocumentFileLocation, InputFileLocation, InputPhotoFileLocation
]


class DownloadSender:
    def __init__(
        self,
        client: TelegramClient,
        sender: MTProtoSender,
        file: TypeLocation,
        offset: int,
        limit: int,
        stride: int,
        count: int,
    ) -> None:
        self.sender = sender
        self.client = client
        self.request = GetFileRequest(file, offset=offset, limit=limit)
        self.stride = stride
        self.remaining = count

    async def next(self) -> Optional[bytes]:
        if not self.remaining:
            return None
        result = await self.client._call(self.sender, self.request)
        self.remaining -= 1
        self.request.offset += self.stride
        return result.bytes

    async def disconnect(self) -> None:
        await self.sender.disconnect()


class UploadSender:
    def __init__(
        self,
        client: TelegramClient,
        sender: MTProtoSender,
        file_id: int,
        part_count: int,
        big: bool,
        index: int,
        stride: int,
    ) -> None:
        self.client = client
        self.sender = sender
        self.part_count = part_count
        if big:
            self.request = SaveBigFilePartRequest(file_id, index, part_count, b"")
        else:
            self.request = SaveFilePartRequest(file_id, index, b"")
        self.stride = stride
        self.previous: Optional[asyncio.Task] = None

    async def next(self, data: bytes) -> None:
        if self.previous:
            await self.previous
        self.previous = asyncio.get_event_loop().create_task(self._next(data))

    async def _next(self, data: bytes) -> None:
        self.request.bytes = data
        await self.client._call(self.sender, self.request)
        self.request.file_part += self.stride

    async def disconnect(self) -> None:
        if self.previous:
            await self.previous
        await self.sender.disconnect()


class ParallelTransferrer:
    def __init__(
        self, client: TelegramClient, dc_id: Optional[int] = None
    ) -> None:
        self.client = client
        self.dc_id = dc_id or self.client.session.dc_id
        self.auth_key = (
            None
            if dc_id and self.client.session.dc_id != dc_id
            else self.client.session.auth_key
        )
        self.senders: Optional[list] = None
        self.upload_ticker = 0

    async def _cleanup(self) -> None:
        if self.senders:
            await asyncio.gather(*[s.disconnect() for s in self.senders])
            self.senders = None

    @staticmethod
    def _get_connection_count(
        file_size: int, max_count: int = 20, full_size: int = 100 * 1024 * 1024
    ) -> int:
        if file_size > full_size:
            return max_count
        return math.ceil((file_size / full_size) * max_count)

    async def _create_sender(self) -> MTProtoSender:
        dc = await self.client._get_dc(self.dc_id)
        sender = MTProtoSender(self.auth_key, loggers=self.client._log)
        await sender.connect(
            self.client._connection(
                dc.ip_address,
                dc.port,
                dc.id,
                loggers=self.client._log,
                proxy=self.client._proxy,
            )
        )
        if not self.auth_key:
            logger.debug("Exporting auth to DC %d", self.dc_id)
            auth = await self.client(ExportAuthorizationRequest(self.dc_id))
            self.client._init_request.query = ImportAuthorizationRequest(
                id=auth.id, bytes=auth.bytes
            )
            req = InvokeWithLayerRequest(LAYER, self.client._init_request)
            await sender.send(req)
            self.auth_key = sender.auth_key
        return sender

    # ── Download ──

    async def _create_download_sender(
        self,
        file: TypeLocation,
        index: int,
        part_size: int,
        stride: int,
        part_count: int,
    ) -> DownloadSender:
        return DownloadSender(
            self.client,
            await self._create_sender(),
            file,
            index * part_size,
            part_size,
            stride,
            part_count,
        )

    async def _init_download(
        self, connections: int, file: TypeLocation, part_count: int, part_size: int
    ) -> None:
        minimum, remainder = divmod(part_count, connections)

        def get_part_count() -> int:
            nonlocal remainder
            if remainder > 0:
                remainder -= 1
                return minimum + 1
            return minimum

        self.senders = [
            await self._create_download_sender(
                file, 0, part_size, connections * part_size, get_part_count()
            ),
            *await asyncio.gather(
                *[
                    self._create_download_sender(
                        file, i, part_size, connections * part_size, get_part_count()
                    )
                    for i in range(1, connections)
                ]
            ),
        ]

    async def download(
        self,
        file: TypeLocation,
        file_size: int,
        part_size_kb: Optional[float] = None,
        connection_count: Optional[int] = None,
    ) -> AsyncGenerator[bytes, None]:
        connection_count = connection_count or self._get_connection_count(file_size)
        part_size = int(
            (part_size_kb or utils.get_appropriated_part_size(file_size)) * 1024
        )
        part_count = math.ceil(file_size / part_size)
        logger.info(
            "并行下载: %d 连接, part_size=%dKB, parts=%d, size=%dMB",
            connection_count,
            part_size // 1024,
            part_count,
            file_size // (1024 * 1024),
        )
        await self._init_download(connection_count, file, part_count, part_size)

        part = 0
        loop = asyncio.get_event_loop()
        while part < part_count:
            tasks = [loop.create_task(sender.next()) for sender in self.senders]
            for task in tasks:
                data = await task
                if not data:
                    break
                yield data
                part += 1

        logger.info("并行下载完成, 清理连接")
        await self._cleanup()

    # ── Upload ──

    async def _create_upload_sender(
        self,
        file_id: int,
        part_count: int,
        big: bool,
        index: int,
        stride: int,
    ) -> UploadSender:
        return UploadSender(
            self.client,
            await self._create_sender(),
            file_id,
            part_count,
            big,
            index,
            stride,
        )

    async def _init_upload(
        self, connections: int, file_id: int, part_count: int, big: bool
    ) -> None:
        self.senders = [
            await self._create_upload_sender(file_id, part_count, big, 0, connections),
            *await asyncio.gather(
                *[
                    self._create_upload_sender(
                        file_id, part_count, big, i, connections
                    )
                    for i in range(1, connections)
                ]
            ),
        ]

    async def init_upload(
        self,
        file_id: int,
        file_size: int,
        part_size_kb: Optional[float] = None,
        connection_count: Optional[int] = None,
    ) -> tuple[int, int, bool]:
        connection_count = connection_count or self._get_connection_count(file_size)
        part_size = int(
            (part_size_kb or utils.get_appropriated_part_size(file_size)) * 1024
        )
        part_count = (file_size + part_size - 1) // part_size
        is_large = file_size > 10 * 1024 * 1024
        logger.info(
            "并行上传: %d 连接, part_size=%dKB, parts=%d, size=%dMB",
            connection_count,
            part_size // 1024,
            part_count,
            file_size // (1024 * 1024),
        )
        await self._init_upload(connection_count, file_id, part_count, is_large)
        return part_size, part_count, is_large

    async def upload(self, part: bytes) -> None:
        await self.senders[self.upload_ticker].next(part)
        self.upload_ticker = (self.upload_ticker + 1) % len(self.senders)

    async def finish_upload(self) -> None:
        await self._cleanup()


# ── Public API ──


async def parallel_download_media(
    client: TelegramClient, message
) -> Optional[bytes]:
    """下载消息媒体文件。大文件使用并行下载，小文件/照片使用默认下载。"""
    doc = getattr(getattr(message, "media", None), "document", None)

    if not doc or not getattr(doc, "size", None) or doc.size < PARALLEL_SIZE_THRESHOLD:
        return await client.download_media(message, bytes)

    try:
        dc_id, location = utils.get_input_location(doc)
        downloader = ParallelTransferrer(client, dc_id)
        chunks = []
        async for chunk in downloader.download(location, doc.size):
            chunks.append(chunk)
        return b"".join(chunks)
    except Exception as e:
        logger.warning("并行下载失败 (%s), 回退到单连接下载", e)
        return await client.download_media(message, bytes)


async def parallel_upload_file(
    client: TelegramClient, data: bytes, filename: str
) -> TypeInputFile:
    """上传文件。大文件使用并行上传，小文件使用默认上传。"""
    if len(data) < PARALLEL_SIZE_THRESHOLD:
        bio = io.BytesIO(data)
        bio.name = filename
        return await client.upload_file(bio)

    try:
        file_id = helpers.generate_random_long()
        file_size = len(data)

        uploader = ParallelTransferrer(client)
        part_size, part_count, is_large = await uploader.init_upload(
            file_id, file_size
        )

        hash_md5 = hashlib.md5()
        offset = 0
        while offset < file_size:
            chunk = data[offset : offset + part_size]
            if not is_large:
                hash_md5.update(chunk)
            await uploader.upload(chunk)
            offset += part_size

        await uploader.finish_upload()

        if is_large:
            return InputFileBig(file_id, part_count, filename)
        else:
            return InputFile(file_id, part_count, filename, hash_md5.hexdigest())
    except Exception as e:
        logger.warning("并行上传失败 (%s), 回退到单连接上传", e)
        bio = io.BytesIO(data)
        bio.name = filename
        return await client.upload_file(bio)
