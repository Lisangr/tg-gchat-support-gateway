from typing import Any, Dict, Optional
from src.state_db import StateDB


class GatewayRouter:
    def __init__(
        self,
        db: StateDB,
        tg_client: Any,
        gchat_client: Any,
        gchat_space_id: str = "",
        target_tg_chat_id: Optional[int] = None,
    ):
        self.db = db
        self.tg = tg_client
        self.gchat = gchat_client
        self.gchat_space_id = gchat_space_id
        self.target_tg_chat_id = target_tg_chat_id

    def handle_telegram_update(self, update: Dict[str, Any]) -> str:
        update_id = update.get("update_id")
        msg = update.get("message")
        if not msg:
            return "ignored_non_message"

        sender = msg.get("from", {})
        if sender.get("is_bot"):
            return "ignored_bot"

        tg_chat_id = msg["chat"]["id"]
        if self.target_tg_chat_id is not None and tg_chat_id != self.target_tg_chat_id:
            return "ignored_wrong_chat"

        msg_uid = f"tg:{update_id}"
        if self.db.is_processed(msg_uid):
            return "ignored_duplicate"

        username = sender.get("username") or sender.get("first_name") or str(tg_chat_id)
        text = msg.get("text") or "[Вложение / медиафайл]"

        if self.gchat_space_id:
            self.db.bind_space(self.gchat_space_id, tg_chat_id)

        # Пишем напрямую в общий чат Google Chat без треда
        self.gchat.send_message(text=f"@{username}: {text}")
        self.db.mark_processed(msg_uid)
        return "forwarded_to_gchat"

    def handle_gchat_event(self, event: Dict[str, Any]) -> str:
        chat_payload = event.get("chat", {})
        if "messagePayload" in chat_payload:
            payload_obj = chat_payload["messagePayload"]
            message = payload_obj.get("message", {})
            space_name = (
                payload_obj.get("space", {}).get("name")
                or message.get("space", {}).get("name")
            )
        else:
            message = event.get("message", event)
            space_name = (
                event.get("space", {}).get("name")
                or message.get("space", {}).get("name")
            )

        msg_name = message.get("name", "")
        sender_type = message.get("sender", {}).get("type", "")

        # Anti-Echo: игнорируем сообщения от самого бота
        if sender_type == "BOT":
            return "ignored_anti_echo"

        if msg_name and self.db.is_processed(f"gc:{msg_name}"):
            return "ignored_duplicate"

        # argumentText содержит чистый текст без "@Support Gateway Bot"
        if "argumentText" in message:
            text = (message.get("argumentText") or "").strip()
        else:
            text = (message.get("text") or "").strip()

        if not text:
            return "ignored_empty"

        if msg_name:
            self.db.mark_processed(f"gc:{msg_name}")

        # Сообщения, начинающиеся с '!', считаются внутренними заметками
        if text.startswith("!"):
            return "ignored_internal_note"

        tg_chat_id = self.target_tg_chat_id
        if tg_chat_id is None:
            lookup_space = space_name or self.gchat_space_id
            if lookup_space:
                tg_chat_id = self.db.get_tg_by_space(lookup_space)

        if tg_chat_id is None:
            return "ignored_unknown_chat"

        self.tg.send_message(tg_chat_id, text)
        return "forwarded_to_telegram"