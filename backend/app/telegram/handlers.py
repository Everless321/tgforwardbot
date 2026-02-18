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
        logger.info("Removed previous event handler")

    source_chats = list(rule_map.keys())
    if not source_chats:
        logger.warning("No source chats to monitor")
        return

    async def on_new_message(event):
        message = event.message
        chat_id = event.chat_id
        logger.info("New message in chat %d (msg_id=%d)", chat_id, message.id)
        targets = rule_map.get(chat_id, [])
        if not targets:
            return

        for target_chat_id, rule_id in targets:
            try:
                await forwarder.forward(message, target_chat_id, rule_id)
            except Exception as e:
                logger.error("Forward failed for rule %d: %s", rule_id, e)

    client.add_event_handler(on_new_message, events.NewMessage(chats=source_chats))
    _current_handler = on_new_message
    logger.info("Handler registered for chats: %s", source_chats)
    logger.info("Monitoring %d source channels", len(source_chats))
