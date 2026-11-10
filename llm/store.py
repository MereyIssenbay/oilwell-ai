"""Restart-safe bounded cache and conservative lifetime call reservation."""
from __future__ import annotations

from pathlib import Path
import sqlite3
import threading
import time


class ExplanationStore:
    def __init__(self, path: Path | None = None):
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(path) if path else ":memory:", timeout=2, check_same_thread=False)
        self.lock = threading.RLock()
        with self.connection:
            self.connection.execute("CREATE TABLE IF NOT EXISTS budget (id INTEGER PRIMARY KEY CHECK(id=1), calls INTEGER NOT NULL)")
            self.connection.execute("INSERT OR IGNORE INTO budget VALUES(1,0)")
            self.connection.execute("CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, created REAL NOT NULL, value TEXT NOT NULL)")

    def get(self, key: str) -> str | None:
        with self.lock:
            row = self.connection.execute("SELECT value FROM cache WHERE key=? AND created>?", (key, time.time() - 3600)).fetchone()
        return row[0] if row else None

    def put(self, key: str, value: str) -> None:
        with self.lock, self.connection:
            self.connection.execute("INSERT OR REPLACE INTO cache VALUES(?,?,?)", (key, time.time(), value))
            self.connection.execute("DELETE FROM cache WHERE key NOT IN (SELECT key FROM cache ORDER BY created DESC, key LIMIT 128)")

    def reserve(self, limit: int) -> bool:
        with self.lock:
            self.connection.execute("BEGIN IMMEDIATE")
            try:
                count = self.connection.execute("SELECT calls FROM budget WHERE id=1").fetchone()[0]
                if count >= limit:
                    self.connection.rollback()
                    return False
                self.connection.execute("UPDATE budget SET calls=calls+1 WHERE id=1")
                self.connection.commit()
                return True
            except BaseException:
                self.connection.rollback()
                raise

    def used_calls(self) -> int:
        with self.lock:
            return self.connection.execute("SELECT calls FROM budget WHERE id=1").fetchone()[0]
