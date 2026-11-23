import os
from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class Config:
    tg_bot_token: str
    gchat_space_id: str
    pubsub_subscription: str
    google_sa_path: str
    db_path: str
    tg_chat_id: Optional[int] = None
    routing_mode: str = "thread"
    gchat_customer: str = "customers/my_customer"
    gchat_operator_emails: Tuple[str, ...] = ()
    log_level: str = "INFO"
    metrics_port: int = 9090
    tg_poll_timeout: int = 20
    pubsub_pull_timeout: int = 95
    pubsub_poll_interval: int = 1
    worker_max_staleness: int = 150


def load_config() -> Config:
    raw_emails = os.environ.get("GCHAT_OPERATOR_EMAILS", "")
    emails = tuple(e.strip() for e in raw_emails.split(",") if e.strip())

    raw_tg_chat_id = os.environ.get("TG_CHAT_ID", "").strip()
    tg_chat_id = int(raw_tg_chat_id) if raw_tg_chat_id else None

    routing_mode = os.environ.get("ROUTING_MODE", "thread").strip().lower()
    if routing_mode not in ("thread", "space", "bridge"):
        routing_mode = "thread"

    return Config(
        tg_bot_token=os.environ.get("TG_BOT_TOKEN", ""),
        gchat_space_id=os.environ.get("GCHAT_SPACE_ID", ""),
        pubsub_subscription=os.environ.get("PUBSUB_SUBSCRIPTION", ""),
        google_sa_path=os.environ.get(
            "GOOGLE_APPLICATION_CREDENTIALS", "/app/secrets/google-sa.json"
        ),
        db_path=os.environ.get("DB_PATH", "/app/data/gateway.db"),
        tg_chat_id=tg_chat_id,
        routing_mode=routing_mode,
        gchat_customer=os.environ.get("GCHAT_CUSTOMER", "customers/my_customer"),
        gchat_operator_emails=emails,
        log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        metrics_port=int(os.environ.get("METRICS_PORT", "9090")),
    )
