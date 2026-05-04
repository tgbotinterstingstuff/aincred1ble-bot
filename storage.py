"""Хранилище уже опубликованного, чтобы не дублировать посты."""
import sqlite3
import hashlib
from pathlib import Path
from datetime import datetime, timezone

DB_PATH = Path(__file__).parent / "published.db"


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS published (
            url_hash TEXT PRIMARY KEY,
            url TEXT NOT NULL,
            title TEXT,
            source TEXT,
            published_at TEXT NOT NULL
        )"""
    )
    return conn


def _hash(url: str) -> str:
    return hashlib.sha256(url.strip().lower().encode()).hexdigest()


def is_published(url: str) -> bool:
    with _conn() as c:
        cur = c.execute("SELECT 1 FROM published WHERE url_hash = ?", (_hash(url),))
        return cur.fetchone() is not None


def mark_published(url: str, title: str = "", source: str = "") -> None:
    with _conn() as c:
        c.execute(
            "INSERT OR IGNORE INTO published (url_hash, url, title, source, published_at) VALUES (?, ?, ?, ?, ?)",
            (_hash(url), url, title, source, datetime.now(timezone.utc).isoformat()),
        )
        c.commit()


def filter_unpublished(items: list) -> list:
    """Из списка кандидатов оставляет только те, что ещё не публиковались."""
    return [i for i in items if not is_published(i["url"])]


def stats() -> dict:
    with _conn() as c:
        total = c.execute("SELECT COUNT(*) FROM published").fetchone()[0]
        return {"total_published": total}
