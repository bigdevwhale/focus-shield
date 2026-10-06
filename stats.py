# -*- coding: utf-8 -*-
"""SQLite-статистика: сессии, отвлечения, снимки, стрики.

Одна connection, трогается только из Tk-потока (check_same_thread=False на
всякий случай), WAL. День — по локальной полночи (SQL-модификатор localtime).
"""
import logging
import sqlite3
import time
from pathlib import Path

log = logging.getLogger("focus.stats")

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at REAL NOT NULL,
    ended_at REAL,
    planned_min REAL,
    actual_min REAL,
    intention TEXT DEFAULT '',
    outcome TEXT,
    kind TEXT DEFAULT 'focus'
);
CREATE TABLE IF NOT EXISTS distractions (
    ts REAL NOT NULL,
    exe TEXT
);
CREATE TABLE IF NOT EXISTS photos (
    ts REAL NOT NULL,
    session_id INTEGER,
    path TEXT
);
CREATE INDEX IF NOT EXISTS idx_sessions_start ON sessions(started_at);
CREATE INDEX IF NOT EXISTS idx_photos_ts ON photos(ts);
"""


class Stats:
    def __init__(self, path):
        self.path = Path(path)
        self.conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # ---------- запись ----------

    def new_session(self, started_at: float, planned_min: float, intention: str,
                    kind: str = "focus") -> int:
        cur = self.conn.execute(
            "INSERT INTO sessions(started_at, planned_min, intention, kind) VALUES (?,?,?,?)",
            (started_at, planned_min, intention, kind))
        self.conn.commit()
        return cur.lastrowid

    def finish_session(self, sid, ended_at: float, actual_min: float, outcome: str) -> None:
        self.conn.execute(
            "UPDATE sessions SET ended_at=?, actual_min=?, outcome=? WHERE id=?",
            (ended_at, actual_min, outcome, sid))
        self.conn.commit()

    def add_distraction(self, exe: str) -> None:
        self.conn.execute("INSERT INTO distractions(ts, exe) VALUES (?,?)",
                          (time.time(), exe))
        self.conn.commit()

    def add_photo(self, session_id, path: str) -> None:
        self.conn.execute("INSERT INTO photos(ts, session_id, path) VALUES (?,?,?)",
                          (time.time(), session_id, path))
        self.conn.commit()

    def delete_photos(self, paths: list) -> None:
        if not paths:
            return
        self.conn.executemany("DELETE FROM photos WHERE path=?", [(p,) for p in paths])
        self.conn.commit()

    # ---------- чтение ----------

    def today_minutes(self) -> float:
        row = self.conn.execute(
            "SELECT COALESCE(SUM(actual_min),0) m FROM sessions "
            "WHERE kind='focus' AND ended_at IS NOT NULL "
            "AND date(started_at,'unixepoch','localtime')=date('now','localtime')"
        ).fetchone()
        return row["m"] or 0.0

    def today_sessions(self) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) c FROM sessions "
            "WHERE kind='focus' AND ended_at IS NOT NULL "
            "AND date(started_at,'unixepoch','localtime')=date('now','localtime')"
        ).fetchone()
        return row["c"]

    def distractions_today(self) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) c FROM distractions "
            "WHERE date(ts,'unixepoch','localtime')=date('now','localtime')"
        ).fetchone()
        return row["c"]

    def last7_minutes(self) -> list:
        """[(date_str, minutes)] за 7 дней, старые первыми."""
        rows = self.conn.execute(
            "SELECT date(started_at,'unixepoch','localtime') d, SUM(actual_min) m "
            "FROM sessions WHERE kind='focus' AND ended_at IS NOT NULL "
            "AND started_at >= strftime('%s','now','localtime','start of day','-6 days') "
            "GROUP BY d ORDER BY d"
        ).fetchall()
        by_day = {r["d"]: (r["m"] or 0.0) for r in rows}
        out = []
        for i in range(6, -1, -1):
            day = time.strftime("%Y-%m-%d", time.localtime(time.time() - i * 86400))
            out.append((day, by_day.get(day, 0.0)))
        return out

    def streak(self) -> int:
        """Подряд идущие дни (заканчивающиеся сегодня или вчера) с >=1 фокусом."""
        rows = self.conn.execute(
            "SELECT DISTINCT date(started_at,'unixepoch','localtime') d FROM sessions "
            "WHERE kind='focus' AND ended_at IS NOT NULL ORDER BY d DESC LIMIT 400"
        ).fetchall()
        days = {r["d"] for r in rows}
        today = time.strftime("%Y-%m-%d")
        yesterday = time.strftime("%Y-%m-%d", time.localtime(time.time() - 86400))
        if today in days:
            cursor = today
        elif yesterday in days:
            cursor = yesterday
        else:
            return 0
        n = 0
        while cursor in days:
            n += 1
            cursor = time.strftime("%Y-%m-%d", time.localtime(
                time.mktime(time.strptime(cursor, "%Y-%m-%d")) - 86400))
        return n

    def recent_intentions(self, limit: int = 10) -> list:
        return self.conn.execute(
            "SELECT started_at, planned_min, actual_min, intention, outcome "
            "FROM sessions WHERE kind='focus' AND intention != '' "
            "ORDER BY started_at DESC LIMIT ?", (limit,)).fetchall()

    def close(self) -> None:
        try:
            self.conn.close()
        except Exception:
            pass
