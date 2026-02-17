from pathlib import Path

from pydantic_settings import BaseSettings

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent


class Settings(BaseSettings):
    api_id: int
    api_hash: str
    session_name: str = "forwarder"
    database_url: str
    redis_url: str = "redis://localhost:6379/0"
    log_level: str = "INFO"
    media_cache_dir: str = "media_cache"

    model_config = {
        "env_file": str(PROJECT_ROOT / ".env"),
        "env_file_encoding": "utf-8",
    }


settings = Settings()
