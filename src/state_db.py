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
            if self.db_path != ":memory:":
                cur.execute("PRAGMA journal_mode=WAL;")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS threads (
                    tg_chat_id INTEGER PRIMARY KEY,
                    gchat_thread_name TEXT UNIQUE NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open',
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
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS kv_store (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            self._conn.commit()

    def get_thread_by_tg(self, tg_chat_id: int) -> Optional[str]:
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT gchat_thread_name FROM threads WHERE tg_chat_id = ? AND status = 'open'",
                (tg_chat_id,),
            )
            row = cur.fetchone()
            return row[0] if row else None

    def get_tg_by_thread(self, gchat_thread_name: str) -> Optional[int]:
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT tg_chat_id FROM threads WHERE gchat_thread_name = ?",
                (gchat_thread_name,),
            )
            row = cur.fetchone()
            return row[0] if row else None

    def upsert_thread(self, tg_chat_id: int, gchat_thread_name: str) -> None:
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                """
                INSERT INTO threads (tg_chat_id, gchat_thread_name, status, updated_at)
                VALUES (?, ?, 'open', CURRENT_TIMESTAMP)
                ON CONFLICT(tg_chat_id) DO UPDATE SET
                    gchat_thread_name = excluded.gchat_thread_name,
                    status = 'open',
                    updated_at = CURRENT_TIMESTAMP
                """,
                (tg_chat_id, gchat_thread_name),
            )
            self._conn.commit()

    def close_thread(self, gchat_thread_name: str) -> None:
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                "UPDATE threads SET status = 'closed', updated_at = CURRENT_TIMESTAMP "
                "WHERE gchat_thread_name = ?",
                (gchat_thread_name,),
            )
            self._conn.commit()

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

    def cleanup_processed_messages(self, retention_days: int = 7) -> int:
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                "DELETE FROM processed_messages WHERE created_at < datetime('now', ?)",
                (f"-{retention_days} days",),
            )
            deleted = cur.rowcount
            self._conn.commit()
            return deleted

    def get_tg_offset(self) -> int:
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("SELECT value FROM kv_store WHERE key = 'tg_offset'")
            row = cur.fetchone()
            return int(row[0]) if row else 0

    def set_tg_offset(self, offset: int) -> None:
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                """
                INSERT INTO kv_store (key, value, updated_at)
                VALUES ('tg_offset', ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (str(offset),),
            )
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()
