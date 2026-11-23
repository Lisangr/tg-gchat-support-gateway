import os
import sqlite3
import threading
from typing import Optional


class StateDB:
    def __init__(self, db_path: str):
        self.db_path = db_path
        if db_path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS space_bindings (
                    gchat_space_id TEXT PRIMARY KEY,
                    tg_chat_id INTEGER NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS processed_messages (
                    msg_id TEXT PRIMARY KEY,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            self._conn.commit()

    def bind_space(self, gchat_space_id: str, tg_chat_id: int) -> None:
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                """
                INSERT INTO space_bindings (gchat_space_id, tg_chat_id, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(gchat_space_id) DO UPDATE SET
                    tg_chat_id = excluded.tg_chat_id,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (gchat_space_id, tg_chat_id),
            )
            self._conn.commit()

    def get_tg_by_space(self, gchat_space_id: str) -> Optional[int]:
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT tg_chat_id FROM space_bindings WHERE gchat_space_id = ?",
                (gchat_space_id,),
            )
            row = cur.fetchone()
            return row[0] if row else None

    def is_processed(self, msg_id: str) -> bool:
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("SELECT 1 FROM processed_messages WHERE msg_id = ?", (msg_id,))
            return cur.fetchone() is not None

    def mark_processed(self, msg_id: str) -> None:
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                "INSERT OR IGNORE INTO processed_messages (msg_id) VALUES (?)",
                (msg_id,),
            )
            self._conn.commit()