"""SQLite persistence: every request, every correction, daily usage. One file, no server."""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS requests (
    id          TEXT PRIMARY KEY,
    created_at  TEXT NOT NULL,
    input_text  TEXT NOT NULL,
    output_text TEXT,
    provider    TEXT,
    ok          INTEGER NOT NULL,
    detail      TEXT
);
CREATE TABLE IF NOT EXISTS corrections (
    id             TEXT PRIMARY KEY,
    request_id     TEXT NOT NULL REFERENCES requests(id),
    created_at     TEXT NOT NULL,
    corrected_text TEXT NOT NULL,
    note           TEXT
);
CREATE INDEX IF NOT EXISTS ix_corrections_created ON corrections(created_at);
CREATE TABLE IF NOT EXISTS usage (
    day   TEXT PRIMARY KEY,
    chars INTEGER NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: str):
        self.path = path
        self.conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(SCHEMA)

    # requests -------------------------------------------------------------------------------
    def save_request(self, input_text: str, output_text: str | None, provider: str | None,
                     ok: bool, detail: str = "") -> str:
        rid = uuid.uuid4().hex
        self.conn.execute(
            "INSERT INTO requests(id, created_at, input_text, output_text, provider, ok, detail) VALUES (?,?,?,?,?,?,?)",
            (rid, _now(), input_text, output_text, provider, int(ok), detail),
        )
        return rid

    def get_request(self, rid: str):
        row = self.conn.execute("SELECT * FROM requests WHERE id=?", (rid,)).fetchone()
        if row is None:
            return None
        cols = [c[0] for c in self.conn.execute("SELECT * FROM requests LIMIT 0").description]
        return dict(zip(cols, row))

    # corrections ----------------------------------------------------------------------------
    def save_correction(self, request_id: str, corrected_text: str, note: str | None) -> str:
        cid = uuid.uuid4().hex
        self.conn.execute(
            "INSERT INTO corrections(id, request_id, created_at, corrected_text, note) VALUES (?,?,?,?,?)",
            (cid, request_id, _now(), corrected_text, note),
        )
        return cid

    def list_corrections(self, since: str | None = None, limit: int = 100) -> list[dict]:
        sql = ("SELECT c.id, c.request_id, c.created_at, r.input_text, r.output_text AS model_text, "
               "c.corrected_text, c.note FROM corrections c JOIN requests r ON r.id = c.request_id ")
        args: list = []
        if since:
            sql += "WHERE c.created_at >= ? "
            args.append(since)
        sql += "ORDER BY c.created_at ASC LIMIT ?"
        args.append(limit)
        cur = self.conn.execute(sql, args)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    # usage ----------------------------------------------------------------------------------
    def chars_today(self) -> int:
        day = _now()[:10]
        row = self.conn.execute("SELECT chars FROM usage WHERE day=?", (day,)).fetchone()
        return row[0] if row else 0

    def add_chars(self, n: int) -> None:
        day = _now()[:10]
        self.conn.execute(
            "INSERT INTO usage(day, chars) VALUES (?, ?) ON CONFLICT(day) DO UPDATE SET chars = chars + excluded.chars",
            (day, n),
        )
