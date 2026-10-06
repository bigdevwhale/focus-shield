# -*- coding: utf-8 -*-
"""Окно перерыва: кольцо обратного отсчёта, «дышащий» круг, микро-практики.
Тексты практик — ключи локализации, переводятся при показе (i18n.T).

Анимация крутится собственным after-циклом (~25 к/с), чтобы круг дыхания
двигался плавно; время берётся из абсолютного ends_at. Практики
сменяются раз в минуту или по кнопке.
"""
import math
import time
import tkinter as tk
from tkinter import ttk

import theme
from i18n import T
from theme import F, P, px

PRACTICES = [
    {"kind": "breath", "title": "Дыхание 4-7-8",
     "text": "Вдох носом на 4 счёта, задержка на 7, медленный выдох ртом на 8. "
             "Следи за кругом — 3–4 цикла."},
    {"kind": "eyes", "title": "Глаза 20-20-20",
     "text": "Посмотри на что-нибудь в 6 метрах, например за окно, 20 секунд. "
             "Несколько раз моргни."},
    {"kind": "move", "title": "Разминка",
     "text": "Встань, потянись вверх, покрути плечами и шеей. Пройдись по комнате."},
    {"kind": "water", "title": "Вода",
     "text": "Выпей стакан воды — обезвоживание первым бьёт по концентрации."},
]

BREATH = [("inhale", 4.0), ("hold", 7.0), ("exhale", 8.0)]
BREATH_LABELS = {"inhale": "вдох", "hold": "задержка", "exhale": "выдох"}
BREATH_CYCLE = sum(d for _, d in BREATH)
FRAME_MS = 40
SIZE = 250


def _breath_phase(t: float):
    """→ (название фазы, радиус-доля 0..1, секунд до конца фазы)."""
    t %= BREATH_CYCLE
    acc = 0.0
    for name, dur in BREATH:
        if t < acc + dur:
            local = (t - acc) / dur
            ease = local * local * (3 - 2 * local)  # smoothstep — без рывков
            frac = {"inhale": ease, "hold": 1.0, "exhale": 1 - ease}[name]
            return name, frac, acc + dur - t
        acc += dur
    return BREATH[0][0], 0.0, BREATH[0][1]


class BreakWindow:
    def __init__(self, parent, minutes: float, long: bool, on_skip):
        self.ends_at = time.time() + minutes * 60
        self.total = max(1.0, minutes * 60)
        self.on_skip = on_skip
        self.idx = 0
        self.practice_until = time.time() + 60
        self.t0 = time.time()
        self._alive = True

        self.win = tk.Toplevel(parent)
        self.win.withdraw()
        self.win.title(T("Перерыв") + " — FocusShield")
        theme.style_window(self.win)
        self.win.attributes("-topmost", True)
        self.win.protocol("WM_DELETE_WINDOW", self._skip)

        body = ttk.Frame(self.win, padding=(px(28), px(20), px(28), px(20)))
        body.pack(fill="both", expand=True)

        ttk.Label(body, text=(T("Длинный перерыв") if long else T("Перерыв")).upper(),
                  style="Accent.TLabel").pack()
        ttk.Label(body, text=T("Блокировка снята. Отойди от экрана."),
                  style="Muted.TLabel").pack(pady=(px(2), px(8)))

        self.size = px(SIZE)
        self.c = theme.canvas(body, width=self.size, height=self.size)
        self.c.pack(pady=px(4))

        card = ttk.Frame(body, style="Card.TFrame", padding=px(16))
        card.pack(fill="x", pady=(px(10), 0))
        top = ttk.Frame(card)
        top.pack(fill="x")
        self.ptitle = ttk.Label(top, text="", style="Subtitle.TLabel")
        self.ptitle.pack(side="left")
        self.dots = ttk.Label(top, text="", style="Caption.TLabel")
        self.dots.pack(side="right")
        self.ptext = ttk.Label(card, text="", style="TLabel", wraplength=px(360),
                               justify="left")
        self.ptext.pack(anchor="w", pady=(px(6), 0))

        foot = ttk.Frame(body)
        foot.pack(fill="x", pady=(px(16), 0))
        ttk.Button(foot, text=T("Другая практика"), command=self.next_practice).pack(side="left")
        ttk.Button(foot, text=T("Пропустить перерыв"), command=self._skip).pack(side="right")

        self._apply_practice()
        theme.center_on_screen(self.win)
        self.win.deiconify()
        from ui_dialogs import pop_to_front
        pop_to_front(self.win)
        self._animate()

    # ---------- управление ----------

    def _skip(self):
        if self.on_skip:
            self.on_skip()

    def close(self):
        self._alive = False
        try:
            self.win.destroy()
        except Exception:
            pass

    def next_practice(self):
        self.idx = (self.idx + 1) % len(PRACTICES)
        self.practice_until = time.time() + 60
        self.t0 = time.time()  # дыхание начинаем с вдоха
        self._apply_practice()

    def _apply_practice(self):
        p = PRACTICES[self.idx]
        self.ptitle.config(text=T(p["title"]))
        self.ptext.config(text=T(p["text"]))
        self.dots.config(text="  ".join("●" if i == self.idx else "○"
                                        for i in range(len(PRACTICES))))

    def update(self, now: float) -> None:
        """Совместимость с тиком оркестратора: смена практики раз в минуту."""
        if self._alive and now >= self.practice_until:
            self.next_practice()

    # ---------- отрисовка ----------

    def _animate(self):
        if not self._alive or not self.win.winfo_exists():
            return
        self._draw(time.time())
        self.win.after(FRAME_MS, self._animate)

    def _draw(self, now: float):
        c, s = self.c, self.size
        c.delete("all")
        cx = cy = s / 2
        ring_r = s / 2 - px(8)
        left = max(0.0, self.ends_at - now)

        # «Дышащий» круг за кольцом
        kind = PRACTICES[self.idx]["kind"]
        if kind == "breath":
            phase, frac, phase_left = _breath_phase(now - self.t0)
        else:
            phase, frac, phase_left = None, 0.55, 0
        inner = ring_r - px(14)
        r = inner * (0.45 + 0.55 * frac)
        fill = theme.mix(P["break"], P["bg"], 0.78)
        c.create_oval(cx - r, cy - r, cx + r, cy + r, fill=fill, outline="")

        # Кольцо оставшегося времени
        c.create_oval(cx - ring_r, cy - ring_r, cx + ring_r, cy + ring_r,
                      outline=P["track"], width=px(6))
        extent = -359.9 * (left / self.total)
        if abs(extent) > 0.5:
            c.create_arc(cx - ring_r, cy - ring_r, cx + ring_r, cy + ring_r, start=90,
                         extent=extent, style="arc", outline=P["break"], width=px(6))

        sec = int(left + 0.999)
        c.create_text(cx, cy - px(6), text=f"{sec // 60:02d}:{sec % 60:02d}",
                      fill=P["text"], font=F["display"])
        if phase:
            c.create_text(cx, cy + px(32),
                          text=f"{T(BREATH_LABELS[phase])} · {max(1, math.ceil(phase_left))}",
                          fill=P["muted"], font=F["body_strong"])
        else:
            c.create_text(cx, cy + px(32), text=T("осталось"), fill=P["muted"],
                          font=F["caption"])
