# -*- coding: utf-8 -*-
"""Плавающий таймер: компактная «пилюля» поверх всех окон.

Безрамочное окно со скруглёнными углами Windows 11. Слева кольцо прогресса
с номером цикла, в центре время и намерение, справа кнопка главного
действия (старт / стоп / пропустить перерыв) и меню «⋯». Перетаскивается
мышью за любое место, позиция сохраняется. Обновляется из секундного тика.
"""
import ctypes
import tkinter as tk
import tkinter.font as tkfont

import theme
from theme import ICON, P, px

W, H = 330, 76


class TimerWidget:
    def __init__(self, root, on_primary, on_menu, on_moved):
        """on_primary() — главная кнопка; on_menu(event) — открыть меню;
        on_moved(x, y) — окно перетащили (сохранить позицию)."""
        self.root = root
        self.on_primary = on_primary
        self.on_menu = on_menu
        self.on_moved = on_moved
        self.visible = False
        self._data = None
        self._drag = None
        self._hover = None
        self._ticks = 0

        self.win = tk.Toplevel(root)
        self.win.withdraw()
        self.win.overrideredirect(True)        # без рамки и без панели задач
        self.win.attributes("-topmost", True)
        self.w, self.h = px(W), px(H)
        self.c = theme.canvas(self.win, width=self.w, height=self.h, bg=P["surface"])
        self.c.pack(fill="both", expand=True)

        self._fonts = {
            "time": tkfont.Font(family=theme.DISPLAY, size=20, weight="bold"),
            "sub": tkfont.Font(family=theme.SMALL, size=9),
            "ring": tkfont.Font(family=theme.SMALL, size=8, weight="bold"),
            "icon": tkfont.Font(family=theme.ICONS, size=11),
            "icon_s": tkfont.Font(family=theme.ICONS, size=9),
        }

        self.c.bind("<ButtonPress-1>", self._press)
        self.c.bind("<B1-Motion>", self._motion)
        self.c.bind("<ButtonRelease-1>", self._release)
        self.c.bind("<Button-3>", lambda e: self.on_menu(e))
        self.c.bind("<Motion>", self._hover_check)
        self.c.bind("<Leave>", lambda e: self._set_hover(None))

    # ---------- позиция ----------

    def place(self, x=None, y=None) -> None:
        vx, vy, vw, vh = _virtual_screen()
        if x is None or y is None or not (vx <= x <= vx + vw - 40 and vy <= y <= vy + vh - 40):
            x = self.root.winfo_screenwidth() - self.w - px(24)
            y = px(24)
        self.win.geometry(f"{self.w}x{self.h}+{x}+{y}")

    def show(self) -> None:
        if self.visible:
            return
        self.visible = True
        self.win.deiconify()
        theme.round_corners(self.win)
        self.win.attributes("-topmost", True)
        self._redraw()

    def hide(self) -> None:
        if not self.visible:
            return
        self.visible = False
        self.win.withdraw()

    def retheme(self) -> None:
        self.c.configure(bg=P["surface"])
        self._redraw()

    # ---------- данные ----------

    def update(self, data: dict) -> None:
        """data: state, remaining, total, title, subtitle, cycle, cycles, camera."""
        self._data = data
        self._ticks += 1
        if self.visible:
            if self._ticks % 10 == 0:  # некоторые полноэкранные окна сбивают topmost
                self.win.attributes("-topmost", True)
            self._redraw()

    # ---------- отрисовка ----------

    def _redraw(self) -> None:
        d = self._data
        if not d:
            return
        c = self.c
        c.delete("all")
        color = theme.state_color(d["state"])
        # В простое главное действие — «начать фокус», поэтому цвет фокуса.
        btn_color = P["focus"] if d["state"] == "idle" else color

        # Кольцо прогресса
        cx, cy, r = px(38), self.h // 2, px(22)
        c.create_oval(cx - r, cy - r, cx + r, cy + r, outline=P["track"], width=px(4))
        if d["total"] > 0:
            done = 1 - d["remaining"] / d["total"]
            extent = -359.9 * max(0.0, min(1.0, done))
            if d["state"] == "focus":
                extent = -359.9 * (d["remaining"] / d["total"])  # тает к нулю
            if abs(extent) > 0.5:
                c.create_arc(cx - r, cy - r, cx + r, cy + r, start=90, extent=extent,
                             style="arc", outline=color, width=px(4))
        if d.get("cycles"):
            c.create_text(cx, cy, text=f"{d['cycle']}/{d['cycles']}", fill=P["muted"],
                          font=self._fonts["ring"])

        # Время и подпись
        tx = px(76)
        c.create_text(tx, px(28), text=d["title"], anchor="w", fill=P["text"],
                      font=self._fonts["time"])
        if d.get("camera"):
            tw = self._fonts["time"].measure(d["title"])
            c.create_text(tx + tw + px(8), px(30), text=ICON["camera"], anchor="w",
                          fill=P["faint"], font=self._fonts["icon_s"])
        primary_x = self.w - px(64)
        max_sub = primary_x - px(16) - px(10) - tx
        c.create_text(tx, px(53), text=_ellipsize(d["subtitle"], self._fonts["sub"], max_sub),
                      anchor="w", fill=P["muted"], font=self._fonts["sub"])

        # Кнопки
        glyph = {"focus": ICON["stop"], "break": ICON["next"],
                 "long_break": ICON["next"]}.get(d["state"], ICON["play"])
        self._button("primary", primary_x, glyph, filled=True, color=btn_color)
        self._button("more", self.w - px(24), ICON["more"], r=px(13))

    def _button(self, tag, x, glyph, filled=False, color=None, r=None) -> None:
        c, cy, r = self.c, self.h // 2, r or px(16)
        hover = self._hover == tag
        if filled:
            fill = color
            fg = "#ffffff" if not P["dark"] or color == P["idle"] else "#0b0b0b"
            outline = ""
        else:
            fill = P["track"] if hover else P["surface"]
            fg = P["text"]
            outline = ""
        if filled and hover:
            fill = theme.mix(color, P["surface"], 0.18)
        c.create_oval(x - r, cy - r, x + r, cy + r, fill=fill, outline=outline,
                      tags=(tag, "btn"))
        c.create_text(x, cy, text=glyph, fill=fg, font=self._fonts["icon"], tags=(tag, "btn"))

    def _hit(self, x, y):
        for item in self.c.find_overlapping(x, y, x, y):
            tags = self.c.gettags(item)
            if "btn" in tags:
                return tags[0]
        return None

    def _set_hover(self, tag) -> None:
        if tag != self._hover:
            self._hover = tag
            self.c.configure(cursor="hand2" if tag else "fleur")
            self._redraw()

    def _hover_check(self, e) -> None:
        self._set_hover(self._hit(e.x, e.y))

    # ---------- мышь ----------

    def _press(self, e) -> None:
        self._drag = (e.x_root, e.y_root, self.win.winfo_x(), self.win.winfo_y(), False)

    def _motion(self, e) -> None:
        if not self._drag:
            return
        sx, sy, wx, wy, _ = self._drag
        dx, dy = e.x_root - sx, e.y_root - sy
        if abs(dx) + abs(dy) > 3:
            self._drag = (sx, sy, wx, wy, True)
            self.win.geometry(f"+{wx + dx}+{wy + dy}")

    def _release(self, e) -> None:
        drag, self._drag = self._drag, None
        if drag and drag[4]:
            self.on_moved(self.win.winfo_x(), self.win.winfo_y())
            return
        tag = self._hit(e.x, e.y)
        if tag == "primary":
            self.on_primary()
        elif tag == "more":
            self.on_menu(e)


def _ellipsize(text: str, font, max_w: int) -> str:
    if font.measure(text) <= max_w:
        return text
    while text and font.measure(text + "…") > max_w:
        text = text[:-1]
    return text.rstrip() + "…"


def _virtual_screen():
    m = ctypes.windll.user32.GetSystemMetrics
    return m(76), m(77), m(78), m(79)  # SM_X/Y/CX/CYVIRTUALSCREEN
