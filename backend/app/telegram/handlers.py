import logging

from telethon import TelegramClient, events

from app.telegram.forwarder import MessageForwarder

logger = logging.getLogger(__name__)


def register_handlers(
    client: TelegramClient,
    rule_map: dict[int, list[tuple[int, int]]],
    forwarder: MessageForwarder,
) -> None:
    source_chats = list(rule_map.keys())
    if not source_chats:
        logger.warning("No source chats to monitor")
        return

    @client.on(events.NewMessage(chats=source_chats))
    async def on_new_message(event):
        message = event.message
        chat_id = event.chat_id
        targets = rule_map.get(chat_id, [])

        for target_chat_id, rule_id in targets:
            try:
                await forwarder.forward(message, target_chat_id, rule_id)
            except Exception as e:
                logger.error("Forward failed for rule %d: %s", rule_id, e)

    logger.info("Monitoring %d source channels", len(source_chats))
