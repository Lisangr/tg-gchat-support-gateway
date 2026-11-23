import logging
import signal
import sys
import threading
import time
from typing import Any, Dict, Tuple

from src.config import load_config
from src.gchat_client import GChatClient
from src.logger import setup_logging
from src.metrics import WORKER_ERRORS_TOTAL, WORKER_HEARTBEAT, start_observability_server
from src.router import GatewayRouter
from src.state_db import StateDB
from src.telegram_client import TelegramClient

logger = logging.getLogger("support-gateway")
stop_event = threading.Event()


def update_heartbeat(
    heartbeats: Dict[str, float], lock: threading.Lock, worker: str
) -> None:
    now_mono = time.monotonic()
    with lock:
        heartbeats[worker] = now_mono
    WORKER_HEARTBEAT.labels(worker=worker).set(time.time())


def tg_polling_loop(
    db: StateDB,
    tg_client: TelegramClient,
    router: GatewayRouter,
    timeout: int,
    heartbeats: Dict[str, float],
    hb_lock: threading.Lock,
) -> None:
    offset = db.get_tg_offset()
    logger.info("Telegram polling worker started with offset=%s", offset)
    while not stop_event.is_set():
        update_heartbeat(heartbeats, hb_lock, "tg")
        try:
            updates = tg_client.get_updates(offset=offset, timeout=timeout)
            for upd in updates:
                res = router.handle_telegram_update(upd)
                offset = max(offset, upd["update_id"] + 1)
                db.set_tg_offset(offset)
                logger.info("Processed TG update %s -> %s", upd.get("update_id"), res)
        except Exception as exc:
            WORKER_ERRORS_TOTAL.labels(worker="tg").inc()
            logger.error("Error in TG polling loop: %s", exc)
            stop_event.wait(5)
        update_heartbeat(heartbeats, hb_lock, "tg")


def gchat_polling_loop(
    gchat_client: GChatClient,
    router: GatewayRouter,
    interval: int,
    heartbeats: Dict[str, float],
    hb_lock: threading.Lock,
) -> None:
    logger.info("Google Chat Pub/Sub pull worker started.")
    while not stop_event.is_set():
        update_heartbeat(heartbeats, hb_lock, "gchat")
        try:
            events = gchat_client.pull_pubsub_events()
            ack_ids = []
            for ack_id, payload in events:
                res = router.handle_gchat_event(payload)
                if res == "ignored_empty":
                    logger.info(
                        "Processed GChat event -> %s (keys=%s)",
                        res,
                        list(payload.keys()),
                    )
                else:
                    logger.info("Processed GChat event -> %s", res)
                ack_ids.append(ack_id)
            if ack_ids:
                gchat_client.ack_pubsub_messages(ack_ids)
        except Exception as exc:
            WORKER_ERRORS_TOTAL.labels(worker="gchat").inc()
            logger.error("Error in GChat Pub/Sub loop: %s", exc)
            stop_event.wait(5)
        update_heartbeat(heartbeats, hb_lock, "gchat")
        stop_event.wait(interval)


def handle_shutdown(signum: int, frame: Any) -> None:
    logger.info("Received signal %s, shutting down gracefully...", signum)
    stop_event.set()


def main() -> None:
    cfg = load_config()
    setup_logging(cfg.log_level)

    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    if not cfg.tg_bot_token:
        logger.error("Missing required env var: TG_BOT_TOKEN")
        sys.exit(1)
    if cfg.routing_mode in ("thread", "bridge") and not cfg.gchat_space_id:
        logger.error("Missing required env var: GCHAT_SPACE_ID")
        sys.exit(1)
    if cfg.routing_mode == "bridge" and cfg.tg_chat_id is None:
        logger.error("Missing required env var for bridge mode: TG_CHAT_ID")
        sys.exit(1)

    db = StateDB(cfg.db_path)
    tg_client = TelegramClient(cfg.tg_bot_token)
    gchat_client = GChatClient(
        cfg.google_sa_path,
        cfg.gchat_space_id,
        cfg.pubsub_subscription,
        pull_timeout=cfg.pubsub_pull_timeout,
        routing_mode=cfg.routing_mode,
        customer=cfg.gchat_customer,
    )
    router = GatewayRouter(
        db,
        tg_client,
        gchat_client,
        routing_mode=cfg.routing_mode,
        operator_emails=cfg.gchat_operator_emails,
        tg_chat_id=cfg.tg_chat_id,
        gchat_space_id=cfg.gchat_space_id,
    )

    hb_lock = threading.Lock()
    now_mono = time.monotonic()
    heartbeats: Dict[str, float] = {"tg": now_mono, "gchat": now_mono}

    t1 = threading.Thread(
        target=tg_polling_loop,
        args=(db, tg_client, router, cfg.tg_poll_timeout, heartbeats, hb_lock),
        name="tg-worker",
        daemon=True,
    )
    t2 = threading.Thread(
        target=gchat_polling_loop,
        args=(gchat_client, router, cfg.pubsub_poll_interval, heartbeats, hb_lock),
        name="gchat-worker",
        daemon=True,
    )

    def check_health() -> Tuple[bool, Dict[str, Any]]:
        current = time.monotonic()
        with hb_lock:
            tg_age = round(current - heartbeats["tg"], 2)
            gchat_age = round(current - heartbeats["gchat"], 2)
        tg_alive = t1.is_alive() and tg_age < cfg.worker_max_staleness
        gchat_alive = t2.is_alive() and gchat_age < cfg.worker_max_staleness
        healthy = tg_alive and gchat_alive
        return healthy, {
            "routing_mode": cfg.routing_mode,
            "workers": {
                "tg": {"alive": t1.is_alive(), "heartbeat_age_sec": tg_age},
                "gchat": {"alive": t2.is_alive(), "heartbeat_age_sec": gchat_age},
            },
        }

    http_server = start_observability_server(cfg.metrics_port, check_health)
    http_thread = threading.Thread(
        target=http_server.serve_forever, name="metrics-server", daemon=True
    )

    http_thread.start()
    logger.info(
        "Observability server started on port %s (routing_mode=%s)",
        cfg.metrics_port,
        cfg.routing_mode,
    )
    t1.start()
    t2.start()

    last_cleanup = time.monotonic()
    while not stop_event.is_set():
        if time.monotonic() - last_cleanup > 3600:
            removed = db.cleanup_processed_messages(retention_days=7)
            if removed:
                logger.info("Cleaned up %s expired deduplication records", removed)
            last_cleanup = time.monotonic()
        stop_event.wait(2)

    t1.join(timeout=5)
    t2.join(timeout=5)
    http_server.shutdown()
    db.close()
    logger.info("Gateway stopped cleanly.")


if __name__ == "__main__":
    main()
