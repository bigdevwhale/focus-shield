# -*- coding: utf-8 -*-
"""Машина состояний помодоро + атомарный state.json.

Состояния: idle | focus | outcome_pending | break | long_break.

Все таймеры — абсолютные timestamp'ы (ends_at), поэтому сон машины и лаги
не сдвигают сессию. Гард отката часов: если системное время прыгнуло назад
сильнее чем на 60 с — продлеваем ends_at на величину прыжка.
"""
import json
import logging
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path

log = logging.getLogger("focus.session")

IDLE = "idle"
FOCUS = "focus"
OUTCOME_PENDING = "outcome_pending"  # фокус закончился, ждём самоотчёт
BREAK = "break"
LONG_BREAK = "long_break"

STATE_VERSION = 1
CLOCK_TOLERANCE = 60.0  # сек; откаты меньше этого считаем шумом


@dataclass
class SessionState:
    state: str = IDLE
    ends_at: float = 0.0
    started_at: float = 0.0
    cycle: int = 0            # сколько фокусов завершено в текущей серии
    work_min: int = 25
    intention: str = ""
    session_db_id: int | None = None
    last_seen: float = 0.0
    version: int = STATE_VERSION


class SessionManager:
    def __init__(self, path):
        self.path = Path(path)
        self.s = SessionState()
        self.load()

    # ---------- персист ----------

    def load(self) -> None:
        try:
            if self.path.exists():
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                if raw.get("version") == STATE_VERSION:
                    known = {f for f in SessionState.__dataclass_fields__}
                    self.s = SessionState(**{k: v for k, v in raw.items() if k in known})
                    log.info("state.json загружен: %s", self.s.state)
                    return
        except Exception:
            log.exception("state.json повреждён, начинаю с idle")
        self.s = SessionState()

    def save(self, now: float = None) -> None:
        self.s.last_seen = time.time() if now is None else now
        tmp = self.path.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(asdict(self.s), f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        tmp.replace(self.path)

    # ---------- гард часов ----------

    def clock_guard(self, now: float) -> None:
        ls = self.s.last_seen
        if ls and now < ls - CLOCK_TOLERANCE:
            delta = ls - now
            if self.s.ends_at:
                self.s.ends_at += delta
            log.warning("часы откатились на %.1f с — сессия продлена", delta)

    # ---------- запросы ----------

    @property
    def state(self) -> str:
        return self.s.state

    def is_active(self) -> bool:
        return self.s.state in (FOCUS, OUTCOME_PENDING, BREAK, LONG_BREAK)

    def remaining(self, now: float = None) -> float:
        if now is None:
            now = time.time()
        return max(0.0, self.s.ends_at - now)

    def remaining_str(self, now: float = None) -> str:
        sec = int(self.remaining(now))
        return f"{sec // 60:02d}:{sec % 60:02d}"

    # ---------- команды ----------

    def start_focus(self, minutes: int, intention: str, db_id, now: float = None) -> None:
        now = time.time() if now is None else now
        self.s = SessionState(
            state=FOCUS,
            started_at=now,
            ends_at=now + minutes * 60,
            work_min=minutes,
            intention=intention,
            session_db_id=db_id,
        )
        self.save()

    def start_break(self, minutes: int, long: bool, now: float = None) -> None:
        now = time.time() if now is None else now
        prev = self.s
        self.s = SessionState(
            state=LONG_BREAK if long else BREAK,
            started_at=now,
            ends_at=now + minutes * 60,
            work_min=prev.work_min,
            intention=prev.intention,      # пригодится для авто-продолжения
            cycle=prev.cycle,
            last_seen=now,
        )
        self.save()

    def to_outcome_pending(self, now: float = None) -> None:
        now = time.time() if now is None else now
        self.s.state = OUTCOME_PENDING
        self.s.ends_at = 0.0
        self.s.last_seen = now
        self.save()

    def to_idle(self, now: float = None) -> None:
        now = time.time() if now is None else now
        self.s = SessionState(last_seen=now)
        self.save()

    # ---------- тик ----------

    def tick(self, now: float = None) -> list:
        """Вызывать раз в секунду. Возвращает список событий для оркестратора."""
        now = time.time() if now is None else now
        self.clock_guard(now)
        events = []
        if self.s.state == FOCUS and now >= self.s.ends_at:
            self.to_outcome_pending(now)
            events.append("focus_end")
        elif self.s.state in (BREAK, LONG_BREAK) and now >= self.s.ends_at:
            finished = self.s.state
            self.to_idle(now)
            events.append("break_end:" + finished)
        if now - self.s.last_seen > 5.0:
            self.save(now)  # обновляем last_seen не каждый тик
        return events
