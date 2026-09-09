"""SQLite persistence.

A job hunt is a longitudinal thing: the useful questions are "what keeps coming
up that I don't have?" and "which of these did I actually apply to?", and
neither can be answered from a single run. Schema changes are handled with
SQLite's ``user_version`` pragma so an existing database upgrades in place
instead of asking the user to delete it.
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

SCHEMA_VERSION = 2


class Status(str, Enum):
    SAVED = "saved"
    APPLIED = "applied"
    SCREENING = "screening"
    INTERVIEW = "interview"
    OFFER = "offer"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"

    @classmethod
    def parse(cls, value: str) -> Status:
        try:
            return cls(value.strip().lower())
        except ValueError:
            options = ", ".join(s.value for s in cls)
            raise ValueError(f"unknown status {value!r}; expected one of: {options}") from None


@dataclass
class Posting:
    id: int
    title: str
    company: str
    url: str
    text: str
    created_at: str


@dataclass
class Application:
    id: int
    posting_id: int
    title: str
    company: str
    url: str
    status: Status
    score: float
    gaps: list[str]
    notes: str
    updated_at: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    """Thin, explicit data-access layer. No ORM: the schema is four tables."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._migrate()

    # ------------------------------------------------------------- lifecycle

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        try:
            with self._conn:
                yield self._conn
        except sqlite3.IntegrityError as exc:
            raise ValueError(str(exc)) from exc

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> Store:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def _migrate(self) -> None:
        version = self._conn.execute("PRAGMA user_version").fetchone()[0]
        if version < 1:
            with self._conn:
                self._conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS postings (
                        id         INTEGER PRIMARY KEY AUTOINCREMENT,
                        title      TEXT NOT NULL,
                        company    TEXT NOT NULL DEFAULT '',
                        url        TEXT NOT NULL DEFAULT '',
                        text       TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS applications (
                        id         INTEGER PRIMARY KEY AUTOINCREMENT,
                        posting_id INTEGER NOT NULL UNIQUE
                                   REFERENCES postings(id) ON DELETE CASCADE,
                        status     TEXT NOT NULL DEFAULT 'saved',
                        score      REAL NOT NULL DEFAULT 0,
                        gaps       TEXT NOT NULL DEFAULT '[]',
                        notes      TEXT NOT NULL DEFAULT '',
                        updated_at TEXT NOT NULL
                    );
                    """
                )
                self._conn.execute("PRAGMA user_version = 1")
            version = 1
        if version < 2:
            with self._conn:
                self._conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_app_status ON applications(status)"
                )
                self._conn.execute("PRAGMA user_version = 2")

    # -------------------------------------------------------------- postings

    def add_posting(self, title: str, text: str, company: str = "", url: str = "") -> int:
        if not title.strip():
            raise ValueError("a posting needs a title")
        if not text.strip():
            raise ValueError("a posting needs some text")
        with self._tx() as conn:
            cursor = conn.execute(
                "INSERT INTO postings (title, company, url, text, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (title.strip(), company.strip(), url.strip(), text, _now()),
            )
        return int(cursor.lastrowid)

    def get_posting(self, posting_id: int) -> Posting | None:
        row = self._conn.execute(
            "SELECT * FROM postings WHERE id = ?", (posting_id,)
        ).fetchone()
        return Posting(**dict(row)) if row else None

    def all_posting_texts(self) -> list[str]:
        return [r["text"] for r in self._conn.execute("SELECT text FROM postings")]

    # ---------------------------------------------------------- applications

    def record_match(
        self,
        posting_id: int,
        score: float,
        gaps: list[str],
        status: Status = Status.SAVED,
        notes: str = "",
    ) -> None:
        """Insert or refresh the application row attached to a posting.

        Re-scoring an existing posting must not reset a status the user has
        already moved on — hence the explicit ``DO UPDATE`` that leaves
        ``status`` and ``notes`` alone.
        """
        with self._tx() as conn:
            conn.execute(
                """
                INSERT INTO applications (posting_id, status, score, gaps, notes, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(posting_id) DO UPDATE SET
                    score = excluded.score,
                    gaps = excluded.gaps,
                    updated_at = excluded.updated_at
                """,
                (posting_id, status.value, score, json.dumps(gaps), notes, _now()),
            )

    def set_status(self, posting_id: int, status: Status, notes: str | None = None) -> bool:
        with self._tx() as conn:
            if notes is None:
                cursor = conn.execute(
                    "UPDATE applications SET status = ?, updated_at = ? WHERE posting_id = ?",
                    (status.value, _now(), posting_id),
                )
            else:
                cursor = conn.execute(
                    "UPDATE applications SET status = ?, notes = ?, updated_at = ?"
                    " WHERE posting_id = ?",
                    (status.value, notes, _now(), posting_id),
                )
        return cursor.rowcount > 0

    def list_applications(self, status: Status | None = None) -> list[Application]:
        sql = """
            SELECT a.id, a.posting_id, p.title, p.company, p.url,
                   a.status, a.score, a.gaps, a.notes, a.updated_at
            FROM applications a JOIN postings p ON p.id = a.posting_id
        """
        params: tuple = ()
        if status is not None:
            sql += " WHERE a.status = ?"
            params = (status.value,)
        sql += " ORDER BY a.score DESC, p.title"
        return [
            Application(
                id=r["id"],
                posting_id=r["posting_id"],
                title=r["title"],
                company=r["company"],
                url=r["url"],
                status=Status(r["status"]),
                score=r["score"],
                gaps=json.loads(r["gaps"]),
                notes=r["notes"],
                updated_at=r["updated_at"],
            )
            for r in self._conn.execute(sql, params)
        ]

    def delete_posting(self, posting_id: int) -> bool:
        with self._tx() as conn:
            cursor = conn.execute("DELETE FROM postings WHERE id = ?", (posting_id,))
        return cursor.rowcount > 0

    # ----------------------------------------------------------- aggregates

    def recurring_gaps(self, limit: int = 10) -> list[tuple[str, int]]:
        """Skills missing across the most postings — i.e. what to learn next.

        This is the report that actually changes behaviour: one missing skill
        is noise, the same one missing from eleven postings is a plan.
        """
        counts: Counter = Counter()
        for row in self._conn.execute("SELECT gaps FROM applications"):
            counts.update(json.loads(row["gaps"]))
        return counts.most_common(limit)

    def status_counts(self) -> dict[str, int]:
        rows = self._conn.execute(
            "SELECT status, COUNT(*) AS n FROM applications GROUP BY status"
        )
        return {r["status"]: r["n"] for r in rows}
