import threading
from typing import Any, Dict, List

import requests


class TelegramClient:
    def __init__(self, bot_token: str):
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
        self._local = threading.local()

    def _get_session(self) -> requests.Session:
        if not hasattr(self._local, "session"):
            self._local.session = requests.Session()
        return self._local.session

    def get_updates(self, offset: int = 0, timeout: int = 20) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/getUpdates"
        resp = self._get_session().get(
            url,
            params={"offset": offset, "timeout": timeout},
            timeout=timeout + 5,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("result", []) if data.get("ok") else []

    def send_message(self, chat_id: int, text: str) -> Dict[str, Any]:
        url = f"{self.base_url}/sendMessage"
        resp = self._get_session().post(
            url,
            json={"chat_id": chat_id, "text": text},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()
