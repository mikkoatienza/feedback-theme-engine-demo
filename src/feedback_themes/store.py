"""SQLite theme store with lifecycle history and run records."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from feedback_themes.models import STATUSES, FeedbackItem

SCHEMA = """
CREATE TABLE IF NOT EXISTS themes (
  id INTEGER PRIMARY KEY,
  key TEXT UNIQUE NOT NULL,
  label TEXT NOT NULL,
  terms TEXT NOT NULL DEFAULT '[]',
  status TEXT NOT NULL DEFAULT 'open',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  last_evidence_at TEXT
);
CREATE TABLE IF NOT EXISTS items (
  key TEXT PRIMARY KEY,
  theme_id INTEGER REFERENCES themes(id),
  transcript_id TEXT NOT NULL,
  account TEXT,
  speaker TEXT,
  kind TEXT,
  text TEXT NOT NULL,
  first_run_id INTEGER
);
CREATE TABLE IF NOT EXISTS status_history (
  id INTEGER PRIMARY KEY,
  theme_id INTEGER NOT NULL REFERENCES themes(id),
  from_status TEXT, to_status TEXT NOT NULL,
  note TEXT, actor TEXT, at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY,
  started_at TEXT NOT NULL, finished_at TEXT,
  transcripts INTEGER DEFAULT 0, items INTEGER DEFAULT 0, new_items INTEGER DEFAULT 0,
  themes INTEGER DEFAULT 0, new_themes INTEGER DEFAULT 0, reopened INTEGER DEFAULT 0,
  llm_calls INTEGER DEFAULT 0, input_tokens INTEGER DEFAULT 0, output_tokens INTEGER DEFAULT 0,
  cost_usd REAL DEFAULT 0, problems TEXT DEFAULT '[]'
);
"""


def now() -> str:
    """UTC timestamp."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Theme:
    """A stored theme with aggregate evidence counts."""

    id: int
    key: str
    label: str
    terms: list[str]
    status: str
    items: int
    accounts: int
    updated_at: str


class Store:
    """Persistent themes, evidence and history. Use ``:memory:`` for tests."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.db = sqlite3.connect(str(path))
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    def close(self) -> None:
        """Close the database connection."""
        self.db.close()

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        """Transaction context: commit on success, roll back on error."""
        try:
            yield self.db
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    # --- runs -------------------------------------------------------------
    def start_run(self) -> int:
        """Create a run record and return its id."""
        cur = self.db.execute("INSERT INTO runs(started_at) VALUES (?)", (now(),))
        self.db.commit()
        return int(cur.lastrowid or 0)

    def finish_run(self, run_id: int, **stats: Any) -> None:
        """Record run statistics."""
        if "problems" in stats:
            stats["problems"] = json.dumps(stats["problems"])
        cols = ", ".join(f"{k} = ?" for k in stats)
        self.db.execute(
            f"UPDATE runs SET finished_at = ?, {cols} WHERE id = ?",
            (now(), *stats.values(), run_id),
        )
        self.db.commit()

    def runs(self, limit: int = 20) -> list[dict[str, Any]]:
        """Most recent runs first."""
        rows = self.db.execute("SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,))
        return [dict(r) for r in rows]

    # --- themes -----------------------------------------------------------
    def themes(self, status: str | None = None) -> list[Theme]:
        """Themes with evidence counts, open first, then by breadth."""
        q = """SELECT t.*, COUNT(i.key) AS n_items, COUNT(DISTINCT i.account) AS n_accounts
               FROM themes t LEFT JOIN items i ON i.theme_id = t.id
               {where} GROUP BY t.id
               ORDER BY t.status != 'open', n_accounts DESC, n_items DESC, t.key"""
        rows = self.db.execute(
            q.format(where="WHERE t.status = ?" if status else ""), (status,) if status else ()
        )
        return [
            Theme(
                r["id"],
                r["key"],
                r["label"],
                json.loads(r["terms"]),
                r["status"],
                r["n_items"],
                r["n_accounts"],
                r["updated_at"],
            )
            for r in rows
        ]

    def theme(self, key: str) -> Theme:
        """Look up one theme by key."""
        for t in self.themes():
            if t.key == key:
                return t
        raise KeyError(key)

    def items_for(self, theme_id: int) -> list[dict[str, Any]]:
        """Evidence rows for a theme."""
        rows = self.db.execute(
            "SELECT * FROM items WHERE theme_id = ? ORDER BY transcript_id", (theme_id,)
        )
        return [dict(r) for r in rows]

    def theme_for_items(self, keys: list[str]) -> dict[int, int]:
        """Map theme id -> how many of ``keys`` it already owns."""
        if not keys:
            return {}
        marks = ",".join("?" * len(keys))
        rows = self.db.execute(
            f"SELECT theme_id, COUNT(*) c FROM items WHERE key IN ({marks}) GROUP BY theme_id",
            keys,
        )
        return {int(r["theme_id"]): int(r["c"]) for r in rows if r["theme_id"] is not None}

    def create_theme(self, key: str, label: str, terms: list[str]) -> int:
        """Insert a theme; keys get a numeric suffix if taken."""
        base, n = key, 2
        while self.db.execute("SELECT 1 FROM themes WHERE key = ?", (key,)).fetchone():
            key, n = f"{base}-{n}", n + 1
        ts = now()
        cur = self.db.execute(
            "INSERT INTO themes(key, label, terms, created_at, updated_at) VALUES (?,?,?,?,?)",
            (key, label, json.dumps(terms), ts, ts),
        )
        return int(cur.lastrowid or 0)

    def add_items(self, theme_id: int, items: list[FeedbackItem], run_id: int) -> int:
        """Attach items to a theme. Returns the number of genuinely new items."""
        new = 0
        for it in items:
            row = self.db.execute("SELECT theme_id FROM items WHERE key = ?", (it.key,)).fetchone()
            if row is None:
                self.db.execute(
                    "INSERT INTO items VALUES (?,?,?,?,?,?,?,?)",
                    (
                        it.key,
                        theme_id,
                        it.transcript_id,
                        it.account,
                        it.speaker,
                        it.kind,
                        it.text,
                        run_id,
                    ),
                )
                new += 1
            elif row["theme_id"] != theme_id:
                self.db.execute("UPDATE items SET theme_id = ? WHERE key = ?", (theme_id, it.key))
        if new:
            self.db.execute(
                "UPDATE themes SET last_evidence_at = ?, updated_at = ? WHERE id = ?",
                (now(), now(), theme_id),
            )
        return new

    def set_status(self, key: str, status: str, note: str = "", actor: str = "user") -> None:
        """Change a theme's lifecycle status and record it in history."""
        if status not in STATUSES:
            raise ValueError(f"status must be one of {STATUSES}")
        row = self.db.execute("SELECT id, status FROM themes WHERE key = ?", (key,)).fetchone()
        if row is None:
            raise KeyError(key)
        self.db.execute(
            "UPDATE themes SET status = ?, updated_at = ? WHERE id = ?", (status, now(), row["id"])
        )
        self.db.execute(
            "INSERT INTO status_history(theme_id, from_status, to_status, note, actor, at) "
            "VALUES (?,?,?,?,?,?)",
            (row["id"], row["status"], status, note, actor, now()),
        )
        self.db.commit()

    def history(self, key: str) -> list[dict[str, Any]]:
        """Status changes for a theme, oldest first."""
        rows = self.db.execute(
            "SELECT h.* FROM status_history h JOIN themes t ON t.id = h.theme_id "
            "WHERE t.key = ? ORDER BY h.id",
            (key,),
        )
        return [dict(r) for r in rows]

    def drop_empty_themes(self) -> int:
        """Delete open themes that lost all their evidence to other themes."""
        cur = self.db.execute(
            "DELETE FROM themes WHERE status = 'open' AND id NOT IN "
            "(SELECT DISTINCT theme_id FROM items WHERE theme_id IS NOT NULL)"
        )
        return cur.rowcount
