import base64
import json
import logging
import threading
from typing import Any, Dict, List, Optional, Tuple

import requests
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import service_account

BASE_SCOPES = [
    "https://www.googleapis.com/auth/chat.bot",
    "https://www.googleapis.com/auth/pubsub",
]

SPACE_SCOPES = [
    "https://www.googleapis.com/auth/chat.app.spaces.create",
    "https://www.googleapis.com/auth/chat.app.memberships",
]

logger = logging.getLogger("support-gateway")


class GChatClient:
    def __init__(
        self,
        sa_key_path: str,
        space_id: str,
        subscription: str,
        pull_timeout: int = 95,
        routing_mode: str = "thread",
        customer: str = "customers/my_customer",
    ):
        self.space_id = space_id
        self.subscription = subscription
        self.pull_timeout = pull_timeout
        self.customer = customer

        scopes = list(BASE_SCOPES)
        if routing_mode == "space":
            scopes.extend(SPACE_SCOPES)

        self.credentials = service_account.Credentials.from_service_account_file(
            sa_key_path, scopes=scopes
        )
        self._auth_lock = threading.Lock()
        self._local = threading.local()

    def _get_session(self) -> requests.Session:
        if not hasattr(self._local, "session"):
            self._local.session = requests.Session()
        return self._local.session

    def _get_headers(self) -> Dict[str, str]:
        with self._auth_lock:
            if not self.credentials.valid:
                self.credentials.refresh(GoogleAuthRequest())
            token = self.credentials.token
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def create_space(
        self, display_name: str, operator_emails: Tuple[str, ...] = ()
    ) -> str:
        url = "https://chat.googleapis.com/v1/spaces"
        payload = {
            "spaceType": "SPACE",
            "displayName": display_name[:128],
            "customer": self.customer,
        }
        resp = self._get_session().post(
            url, headers=self._get_headers(), json=payload, timeout=15
        )
        resp.raise_for_status()
        space_name = resp.json()["name"]

        for email in operator_emails:
            try:
                self.add_member(space_name, email)
            except Exception as exc:
                logger.warning("Failed to add operator %s to %s: %s", email, space_name, exc)

        return space_name

    def add_member(self, space_name: str, user_email: str) -> Dict[str, Any]:
        url = f"https://chat.googleapis.com/v1/{space_name}/members"
        payload = {
            "member": {
                "name": f"users/{user_email}",
                "type": "HUMAN",
            }
        }
        resp = self._get_session().post(
            url, headers=self._get_headers(), json=payload, timeout=15
        )
        resp.raise_for_status()
        return resp.json()

    def send_message(
        self,
        text: str,
        space_name: Optional[str] = None,
        thread_name: Optional[str] = None,
        thread_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        target_space = space_name or self.space_id
        url = f"https://chat.googleapis.com/v1/{target_space}/messages"
        params: Dict[str, str] = {}
        payload: Dict[str, Any] = {"text": text}

        if thread_name:
            payload["thread"] = {"name": thread_name}
            params["messageReplyOption"] = "REPLY_MESSAGE_FALLBACK_TO_NEW_THREAD"
        elif thread_key:
            payload["thread"] = {"threadKey": thread_key}
            params["messageReplyOption"] = "REPLY_MESSAGE_FALLBACK_TO_NEW_THREAD"

        resp = self._get_session().post(
            url, headers=self._get_headers(), params=params, json=payload, timeout=15
        )
        resp.raise_for_status()
        return resp.json()

    def pull_pubsub_events(self, max_messages: int = 10) -> List[Tuple[str, Dict[str, Any]]]:
        if not self.subscription:
            return []
        url = f"https://pubsub.googleapis.com/v1/{self.subscription}:pull"
        try:
            resp = self._get_session().post(
                url,
                headers=self._get_headers(),
                json={"maxMessages": max_messages},
                timeout=self.pull_timeout,
            )
            resp.raise_for_status()
        except requests.exceptions.ReadTimeout:
            return []

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
        resp = self._get_session().post(
            url, headers=self._get_headers(), json={"ackIds": ack_ids}, timeout=15
        )
        resp.raise_for_status()
