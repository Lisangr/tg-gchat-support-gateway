import logging
import signal
import sys
import threading
import time
from pathlib import Path
import requests

from src.config import load_config
from src.gchat_client import GChatClient
from src.router import GatewayRouter
from src.state_db import StateDB
from src.telegram_client import TelegramClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("support-gateway")

HEARTBEAT_FILE = Path("/tmp/gateway_alive")
stop_event = threading.Event()


def touch_heartbeat() -> None:
    try:
        HEARTBEAT_FILE.touch()
    except OSError:
        pass


def tg_polling_loop(tg_client: TelegramClient, router: GatewayRouter, timeout: int) -> None:
    offset = 0
    logger.info("Telegram polling worker started.")
    while not stop_event.is_set():
        try:
            touch_heartbeat()
            updates = tg_client.get_updates(offset=offset, timeout=timeout)
            for upd in updates:
                offset = max(offset, upd["update_id"] + 1)
                res = router.handle_telegram_update(upd)
                logger.info("TG update %s -> %s", upd.get("update_id"), res)
        except requests.exceptions.ReadTimeout:
            continue
        except Exception as exc:
            logger.error("Error in TG polling loop: %s", exc)
            time.sleep(5)


def gchat_polling_loop(gchat_client: GChatClient, router: GatewayRouter, interval: int) -> None:
    logger.info("Google Chat Pub/Sub pull worker started.")
    while not stop_event.is_set():
        try:
            touch_heartbeat()
            events = gchat_client.pull_pubsub_events()
            ack_ids = []
            for ack_id, payload in events:
                res = router.handle_gchat_event(payload)
                logger.info("GChat event -> %s", res)
                ack_ids.append(ack_id)
            if ack_ids:
                gchat_client.ack_pubsub_messages(ack_ids)
        except requests.exceptions.ReadTimeout:
            logger.debug("Pub/Sub pull timed out (no new messages), retrying...")
        except Exception as exc:
            logger.error("Error in GChat Pub/Sub loop: %s", exc)
            time.sleep(5)
        time.sleep(interval)


def handle_shutdown(signum, frame) -> None:
    logger.info("Received signal %s, shutting down gracefully...", signum)
    stop_event.set()


def main() -> None:
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    cfg = load_config()
    if not cfg.tg_bot_token or not cfg.gchat_space_id:
        logger.error("Missing required env vars: TG_BOT_TOKEN or GCHAT_SPACE_ID")
        sys.exit(1)

    db = StateDB(cfg.db_path)
    tg_client = TelegramClient(cfg.tg_bot_token)
    gchat_client = GChatClient(cfg.google_sa_path, cfg.gchat_space_id, cfg.pubsub_subscription)
    router = GatewayRouter(
        db,
        tg_client,
        gchat_client,
        gchat_space_id=cfg.gchat_space_id,
        target_tg_chat_id=cfg.tg_chat_id,
    )

    t1 = threading.Thread(
        target=tg_polling_loop, args=(tg_client, router, cfg.tg_poll_timeout), daemon=True
    )
    t2 = threading.Thread(
        target=gchat_polling_loop, args=(gchat_client, router, cfg.pubsub_poll_interval), daemon=True
    )

    t1.start()
    t2.start()

    while not stop_event.is_set():
        touch_heartbeat()
        time.sleep(2)


if __name__ == "__main__":
    main()