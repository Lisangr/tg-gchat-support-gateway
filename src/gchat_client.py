import base64
import json
import requests
from typing import Any, Dict, List, Optional, Tuple
from google.oauth2 import service_account
from google.auth.transport.requests import Request as GoogleAuthRequest


SCOPES = [
    "https://www.googleapis.com/auth/chat.bot",
    "https://www.googleapis.com/auth/pubsub",
]


class GChatClient:
    def __init__(self, sa_key_path: str, space_id: str, subscription: str):
        self.space_id = space_id
        self.subscription = subscription
        self.credentials = service_account.Credentials.from_service_account_file(
            sa_key_path, scopes=SCOPES
        )
        self.session = requests.Session()

    def _get_headers(self) -> Dict[str, str]:
        if not self.credentials.valid:
            self.credentials.refresh(GoogleAuthRequest())
        return {
            "Authorization": f"Bearer {self.credentials.token}",
            "Content-Type": "application/json",
        }

    def send_message(
        self, text: str, thread_name: Optional[str] = None, thread_key: Optional[str] = None
    ) -> Dict[str, Any]:
        url = f"https://chat.googleapis.com/v1/{self.space_id}/messages"
        params: Dict[str, str] = {}
        payload: Dict[str, Any] = {"text": text}

        if thread_name:
            payload["thread"] = {"name": thread_name}
            params["messageReplyOption"] = "REPLY_MESSAGE_FALLBACK_TO_NEW_THREAD"
        elif thread_key:
            payload["thread"] = {"threadKey": thread_key}
            params["messageReplyOption"] = "REPLY_MESSAGE_FALLBACK_TO_NEW_THREAD"

        resp = self.session.post(
            url, headers=self._get_headers(), params=params, json=payload, timeout=15
        )
        resp.raise_for_status()
        return resp.json()

    def pull_pubsub_events(self, max_messages: int = 10) -> List[Tuple[str, Dict[str, Any]]]:
        if not self.subscription:
            return []
        url = f"https://pubsub.googleapis.com/v1/{self.subscription}:pull"
        resp = self.session.post(
            url, headers=self._get_headers(), json={"maxMessages": max_messages}, timeout=40
        )
        resp.raise_for_status()
        received = resp.json().get("receivedMessages", [])
        events: List[Tuple[str, Dict[str, Any]]] = []
        for item in received:
            ack_id = item.get("ackId")
            raw_data = item.get("message", {}).get("data", "")
            if ack_id and raw_data:
                decoded = json.loads(base64.b64decode(raw_data).decode("utf-8"))
                events.append((ack_id, decoded))
        return events

    def ack_pubsub_messages(self, ack_ids: List[str]) -> None:
        if not ack_ids or not self.subscription:
            return
        url = f"https://pubsub.googleapis.com/v1/{self.subscription}:acknowledge"
        resp = self.session.post(
            url, headers=self._get_headers(), json={"ackIds": ack_ids}, timeout=15
        )
        resp.raise_for_status()