from unittest.mock import MagicMock

from src.router import GatewayRouter
from src.state_db import StateDB


def make_router(routing_mode="thread"):
    db = StateDB(":memory:")
    tg = MagicMock()
    gchat = MagicMock()
    gchat.send_message.return_value = {"thread": {"name": "spaces/AAA/threads/T123"}}
    gchat.create_space.return_value = "spaces/NEW_SPACE_777"
    router = GatewayRouter(
        db,
        tg,
        gchat,
        routing_mode=routing_mode,
        operator_emails=("op1@company.com",),
    )
    return router, db, tg, gchat


def test_telegram_creates_and_reuses_thread():
    router, db, _, gchat = make_router("thread")

    upd1 = {
        "update_id": 100,
        "message": {"chat": {"id": 777}, "from": {"username": "client1"}, "text": "Привет!"},
    }
    res1 = router.handle_telegram_update(upd1)
    assert res1 == "forwarded_to_gchat"
    assert db.get_thread_by_tg(777) == "spaces/AAA/threads/T123"
    gchat.send_message.assert_called_once()

    upd2 = {
        "update_id": 101,
        "message": {"chat": {"id": 777}, "from": {"username": "client1"}, "text": "Второй вопрос"},
    }
    res2 = router.handle_telegram_update(upd2)
    assert res2 == "forwarded_to_gchat"
    assert gchat.send_message.call_args.kwargs["thread_name"] == "spaces/AAA/threads/T123"


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
    router, _, tg, _ = make_router()
    event = {
        "message": {
            "name": "spaces/AAA/messages/M1",
            "sender": {"type": "BOT"},
            "thread": {"name": "spaces/AAA/threads/T123"},
            "text": "Эхо от самого бота",
        }
    }
    assert router.handle_gchat_event(event) == "ignored_anti_echo"
    tg.send_message.assert_not_called()


def test_gchat_internal_note_not_sent_to_telegram():
    router, db, tg, _ = make_router()
    db.upsert_thread(999, "spaces/AAA/threads/T999")

    event = {
        "message": {
            "name": "spaces/AAA/messages/M2",
            "sender": {"type": "HUMAN"},
            "thread": {"name": "spaces/AAA/threads/T999"},
            "text": "!Коллеги, клиент просит возврат, проверьте логи",
        }
    }
    assert router.handle_gchat_event(event) == "ignored_internal_note"
    tg.send_message.assert_not_called()


def test_gchat_addon_payload_and_close_command():
    router, db, tg, gchat = make_router("thread")
    db.upsert_thread(888, "spaces/AAA/threads/T888")

    addon_event = {
        "chat": {
            "messagePayload": {
                "space": {"name": "spaces/AAA"},
                "message": {
                    "name": "spaces/AAA/messages/M3",
                    "sender": {"type": "HUMAN"},
                    "thread": {"name": "spaces/AAA/threads/T888"},
                    "text": "@SupportBot Здравствуйте!",
                    "argumentText": " Здравствуйте!",
                },
            }
        }
    }
    assert router.handle_gchat_event(addon_event) == "forwarded_to_telegram"
    tg.send_message.assert_called_with(888, "Здравствуйте!")

    close_event = {
        "chat": {
            "messagePayload": {
                "message": {
                    "name": "spaces/AAA/messages/M4",
                    "sender": {"type": "HUMAN"},
                    "thread": {"name": "spaces/AAA/threads/T888"},
                    "argumentText": "/close",
                }
            }
        }
    }
    assert router.handle_gchat_event(close_event) == "closed"
    assert db.get_thread_by_tg(888) is None
    gchat.send_message.assert_called_with(
        text="Диалог закрыт.", thread_name="spaces/AAA/threads/T888"
    )


def test_space_per_chat_mode():
    router, db, tg, gchat = make_router("space")

    upd = {
        "update_id": 300,
        "message": {"chat": {"id": 777}, "from": {"username": "vip_user"}, "text": "Нужна помощь"},
    }
    assert router.handle_telegram_update(upd) == "forwarded_to_gchat"
    gchat.create_space.assert_called_once_with(
        display_name="TG: @vip_user (777)",
        operator_emails=("op1@company.com",),
    )
    assert db.get_thread_by_tg(777) == "spaces/NEW_SPACE_777"
    gchat.send_message.assert_called_with(
        text="[Новое обращение] @vip_user (ID: 777):\nНужна помощь",
        space_name="spaces/NEW_SPACE_777",
    )

    reply_event = {
        "chat": {
            "messagePayload": {
                "space": {"name": "spaces/NEW_SPACE_777"},
                "message": {
                    "name": "spaces/NEW_SPACE_777/messages/M10",
                    "sender": {"type": "HUMAN"},
                    "space": {"name": "spaces/NEW_SPACE_777"},
                    "argumentText": "Решаем вопрос",
                },
            }
        }
    }
    assert router.handle_gchat_event(reply_event) == "forwarded_to_telegram"
    tg.send_message.assert_called_with(777, "Решаем вопрос")
   
def test_bridge_mode_1_to_1_without_threads():
    db = StateDB(":memory:")
    tg = MagicMock()
    gchat = MagicMock()
    router = GatewayRouter(
        db,
        tg,
        gchat,
        routing_mode="bridge",
        tg_chat_id=-1003793510067,
        gchat_space_id="spaces/AAQAjjGLbFQ",
    )

    foreign_upd = {
        "update_id": 400,
        "message": {"chat": {"id": 999999}, "from": {"username": "stranger"}, "text": "Spam"},
    }
    assert router.handle_telegram_update(foreign_upd) == "ignored_foreign_chat"
    gchat.send_message.assert_not_called()

    valid_upd = {
        "update_id": 401,
        "message": {
            "chat": {"id": -1003793510067},
            "from": {"username": "operator"},
            "text": "В общий чат без треда",
        },
    }
    assert router.handle_telegram_update(valid_upd) == "forwarded_to_gchat"
    gchat.send_message.assert_called_once_with(
        text="@operator (ID: -1003793510067):\nВ общий чат без треда"
    )

    reply_event = {
        "chat": {
            "messagePayload": {
                "space": {"name": "spaces/AAQAjjGLbFQ"},
                "message": {
                    "name": "spaces/AAQAjjGLbFQ/messages/M50",
                    "sender": {"type": "HUMAN"},
                    "space": {"name": "spaces/AAQAjjGLbFQ"},
                    "argumentText": " Ответ в ТГ группу",
                },
            }
        }
    }
    assert router.handle_gchat_event(reply_event) == "forwarded_to_telegram"
    tg.send_message.assert_called_once_with(-1003793510067, "Ответ в ТГ группу")
