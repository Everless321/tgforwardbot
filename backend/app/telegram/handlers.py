import logging

from telethon import TelegramClient, events

from app.telegram.forwarder import MessageForwarder

logger = logging.getLogger(__name__)

_current_handler = None


def register_handlers(
    client: TelegramClient,
    rule_map: dict[int, list[tuple[int, int]]],
    forwarder: MessageForwarder,
) -> None:
    global _current_handler

    if _current_handler is not None:
        client.remove_event_handler(_current_handler)
        _current_handler = None
        logger.info("已移除旧事件处理器")

    source_chats = list(rule_map.keys())
    if not source_chats:
        logger.warning("没有可监控的源频道")
        return

    async def on_new_message(event):
        message = event.message
        chat_id = event.chat_id
        logger.info("频道 %d 新消息 (msg_id=%d)", chat_id, message.id)
        targets = rule_map.get(chat_id, [])
        if not targets:
            return

        for target_chat_id, rule_id in targets:
            try:
                await forwarder.forward(message, target_chat_id, rule_id)
            except Exception as e:
                logger.error("[规则 %d] 转发失败: %s", rule_id, e)

    client.add_event_handler(on_new_message, events.NewMessage(chats=source_chats))
    _current_handler = on_new_message
    logger.info("已注册事件处理器, 频道: %s", source_chats)
    logger.info("正在监控 %d 个源频道", len(source_chats))
