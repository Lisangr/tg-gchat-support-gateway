import os
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Config:
    tg_bot_token: str
    gchat_space_id: str
    pubsub_subscription: str
    google_sa_path: str
    db_path: str
    tg_chat_id: Optional[int] = None
    tg_poll_timeout: int = 20
    pubsub_poll_interval: int = 2


def load_config() -> Config:
    raw_tg_chat_id = os.environ.get("TG_CHAT_ID", "").strip()
    tg_chat_id = int(raw_tg_chat_id) if raw_tg_chat_id else None
    return Config(
        tg_bot_token=os.environ.get("TG_BOT_TOKEN", ""),
        gchat_space_id=os.environ.get("GCHAT_SPACE_ID", ""),
        pubsub_subscription=os.environ.get("PUBSUB_SUBSCRIPTION", ""),
        google_sa_path=os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "/app/secrets/google-sa.json"),
        db_path=os.environ.get("DB_PATH", "/app/data/gateway.db"),
        tg_chat_id=tg_chat_id,
    )