import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker
from telethon import TelegramClient
from telethon.errors import FloodWaitError

from app.core.events import event_bus
from app.models.message import (
    ContentType,
    ForwardRule,
    MessageLog,
    MessageStatus,
    SyncStatus,
)
from app.telegram.forwarder import MessageForwarder, detect_content_type

logger = logging.getLogger(__name__)

BATCH_SIZE = 100
SEND_DELAY = 1.5


class HistorySyncer:
    def __init__(
        self,
        client: TelegramClient,
        forwarder: MessageForwarder,
        session_factory: async_sessionmaker,
    ):
        self.client = client
        self.forwarder = forwarder
        self._session_factory = session_factory
        self._running_tasks: dict[int, asyncio.Task] = {}

    def is_syncing(self, rule_id: int) -> bool:
        task = self._running_tasks.get(rule_id)
        return task is not None and not task.done()

    def start_sync(self, rule_id: int) -> bool:
        if self.is_syncing(rule_id):
            return False
        self._running_tasks[rule_id] = asyncio.create_task(self._sync(rule_id))
        return True

    def stop_sync(self, rule_id: int) -> bool:
        task = self._running_tasks.pop(rule_id, None)
        if task and not task.done():
            task.cancel()
            return True
        return False

    async def _set_sync_status(self, rule_id: int, status: SyncStatus, count: int | None = None):
        async with self._session_factory() as session:
            rule = await session.get(ForwardRule, rule_id)
            if not rule:
                return
            rule.sync_status = status
            if count is not None:
                rule.synced_msg_count = count
            await session.commit()

    async def _get_synced_msg_ids(self, rule_id: int) -> set[int]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(MessageLog.source_msg_id).where(
                    MessageLog.rule_id == rule_id,
                    MessageLog.status == MessageStatus.SUCCESS,
                )
            )
            return set(result.scalars().all())

    async def _sync(self, rule_id: int) -> None:
        await self._set_sync_status(rule_id, SyncStatus.SYNCING, 0)

        async with self._session_factory() as session:
            rule = await session.get(ForwardRule, rule_id)
            if not rule:
                logger.error("[同步] 规则 %d 不存在", rule_id)
                return
            source_chat_id = rule.source_chat_id
            target_chat_id = rule.target_chat_id

        logger.info("[同步] 规则 %d: 开始 (源=%d -> 目标=%d)", rule_id, source_chat_id, target_chat_id)
        synced_ids = await self._get_synced_msg_ids(rule_id)
        synced_count = 0
        skip_count = 0

        try:
            async for message in self.client.iter_messages(source_chat_id, reverse=True):
                if message.id in synced_ids:
                    skip_count += 1
                    continue

                try:
                    await self.forwarder.forward(message, target_chat_id, rule_id)
                    synced_count += 1
                    logger.info("[同步] 规则 %d: 已转发 %d 条消息", rule_id, synced_count)
                except FloodWaitError as e:
                    logger.warning("[同步] 规则 %d: 限流等待 %d 秒 (消息 %d)", rule_id, e.seconds, message.id)
                    await asyncio.sleep(e.seconds + 1)
                    try:
                        await self.forwarder.forward(message, target_chat_id, rule_id)
                        synced_count += 1
                    except Exception as retry_err:
                        logger.error("[同步] 规则 %d: 消息 %d 失败: %s", rule_id, message.id, retry_err)
                except Exception as e:
                    logger.error("[同步] 规则 %d: 消息 %d 失败: %s", rule_id, message.id, e)

                if synced_count % 10 == 0:
                    await self._set_sync_status(rule_id, SyncStatus.SYNCING, synced_count)
                    await event_bus.publish({
                        "type": "sync_progress",
                        "rule_id": rule_id,
                        "synced_count": synced_count,
                    })

                await asyncio.sleep(SEND_DELAY)

        except asyncio.CancelledError:
            logger.info("[同步] 规则 %d: 已取消, 已转发 %d 条", rule_id, synced_count)
            await self._set_sync_status(rule_id, SyncStatus.IDLE, synced_count)
            return
        except Exception as e:
            logger.error("[同步] 规则 %d 异常: %s", rule_id, e)
            await self._set_sync_status(rule_id, SyncStatus.IDLE, synced_count)
            return
        finally:
            self._running_tasks.pop(rule_id, None)

        await self._set_sync_status(rule_id, SyncStatus.DONE, synced_count)
        await event_bus.publish({
            "type": "sync_complete",
            "rule_id": rule_id,
            "synced_count": synced_count,
        })
        logger.info("[同步] 规则 %d: 完成! 转发 %d 条, 跳过 %d 条", rule_id, synced_count, skip_count)
