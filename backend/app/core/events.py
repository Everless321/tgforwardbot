import asyncio


class EventBus:
    def __init__(self):
        self._subscribers: list[asyncio.Queue] = []

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.remove(q)

    async def publish(self, event: dict) -> None:
        for q in self._subscribers:
            await q.put(event)


event_bus = EventBus()
