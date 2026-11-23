from unittest.mock import MagicMock
from src.router import GatewayRouter
from src.state_db import StateDB


def make_router(target_tg_chat_id=None):
    db = StateDB(":memory:")
    tg = MagicMock()
    gchat = MagicMock()
    router = GatewayRouter(
        db,
        tg,
        gchat,
        gchat_space_id="spaces/AAA",
        target_tg_chat_id=target_tg_chat_id,
    )
    return router, db, tg, gchat


def test_telegram_forwards_directly_without_thread():
    router, db, tg, gchat = make_router()

    upd1 = {
        "update_id": 100,
        "message": {"chat": {"id": 777}, "from": {"username": "client1"}, "text": "Привет!"},
    }
    assert router.handle_telegram_update(upd1) == "forwarded_to_gchat"
    assert db.get_tg_by_space("spaces/AAA") == 777
    gchat.send_message.assert_called_once_with(text="@client1: Привет!")


def test_telegram_ignores_wrong_chat_when_pinned():
    router, _, _, gchat = make_router(target_tg_chat_id=-1003793510067)
    upd = {
        "update_id": 101,
        "message": {"chat": {"id": 999}, "from": {"username": "stranger"}, "text": "Спам"},
    }
    assert router.handle_telegram_update(upd) == "ignored_wrong_chat"
    gchat.send_message.assert_not_called()


def test_telegram_deduplication():
    router, _, _, gchat = make_router()
    upd = {
        "update_id": 200,
        "message": {"chat": {"id": 555}, "from": {"first_name": "Ivan"}, "text": "Help"},
    }
    assert router.handle_telegram_update(upd) == "forwarded_to_gchat"
    assert router.handle_telegram_update(upd) == "ignored_duplicate"
    assert gchat.send_message.call_count == 1


def test_gchat_anti_echo_ignores_bot():
    router, _, tg, _ = make_router(target_tg_chat_id=777)
    event = {
        "message": {
            "name": "spaces/AAA/messages/M1",
            "sender": {"type": "BOT"},
            "text": "Эхо от самого бота",
        }
    }
    assert router.handle_gchat_event(event) == "ignored_anti_echo"
    tg.send_message.assert_not_called()


def test_gchat_internal_note_not_sent_to_telegram():
    router, _, tg, _ = make_router(target_tg_chat_id=777)
    event = {
        "message": {
            "name": "spaces/AAA/messages/M2",
            "sender": {"type": "HUMAN"},
            "argumentText": " !Внутренняя заметка",
            "text": "@Bot !Внутренняя заметка",
        }
    }
    assert router.handle_gchat_event(event) == "ignored_internal_note"
    tg.send_message.assert_not_called()


def test_gchat_workspace_addon_payload_forwards_to_telegram():
    router, db, tg, _ = make_router()
    db.bind_space("spaces/AAA", -1003793510067)

    event = {
        "chat": {
            "messagePayload": {
                "space": {"name": "spaces/AAA"},
                "message": {
                    "name": "spaces/AAA/messages/M3",
                    "sender": {"type": "HUMAN"},
                    "text": "@Support Gateway Bot Привет из Google Chat!",
                    "argumentText": " Привет из Google Chat!",
                },
            }
        }
    }
    assert router.handle_gchat_event(event) == "forwarded_to_telegram"
    tg.send_message.assert_called_once_with(-1003793510067, "Привет из Google Chat!")