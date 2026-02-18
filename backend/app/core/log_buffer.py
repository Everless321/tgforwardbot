import logging
from collections import deque
from datetime import datetime, timezone


class LogRecord:
    __slots__ = ('timestamp', 'level', 'logger_name', 'message')

    def __init__(self, timestamp: str, level: str, logger_name: str, message: str):
        self.timestamp = timestamp
        self.level = level
        self.logger_name = logger_name
        self.message = message

    def to_dict(self) -> dict:
        return {
            'timestamp': self.timestamp,
            'level': self.level,
            'logger': self.logger_name,
            'message': self.message,
        }


class BufferHandler(logging.Handler):
    def __init__(self, maxlen: int = 500):
        super().__init__()
        self.buffer: deque[LogRecord] = deque(maxlen=maxlen)

    def emit(self, record: logging.LogRecord) -> None:
        entry = LogRecord(
            timestamp=datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            level=record.levelname,
            logger_name=record.name,
            message=self.format(record),
        )
        self.buffer.append(entry)

    def get_entries(self, limit: int = 200, level: str | None = None) -> list[dict]:
        entries = list(self.buffer)
        if level:
            entries = [e for e in entries if e.level == level.upper()]
        return [e.to_dict() for e in entries[-limit:]]


log_buffer = BufferHandler(maxlen=500)
log_buffer.setLevel(logging.INFO)
log_buffer.setFormatter(logging.Formatter("%(message)s"))
