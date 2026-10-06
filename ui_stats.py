# -*- coding: utf-8 -*-
"""Окно статистики: обзор (плитки, график недели, намерения) и фото по дням.

Фото берутся прямо из папок photos\\ГГГГ-ММ-ДД — каждую можно открыть в
Проводнике кнопкой или двойным кликом по дню.
"""
import os
import time
import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageTk

import i18n
import theme
import webcam
from i18n import T
from theme import F, ICON, P, px
from ui_dialogs import pop_to_front

OUTCOME_LABELS = {"done": "✓ сделано", "partial": "◐ частично", "no": "✕ не вышло",
                  "stopped_early": "⏹ прервано"}
KIND_LABELS = {"camera": "камера", "screen": "экран"}

THUMB = 132


def human_day(day: str, full: bool = False) -> str:
    """‘2026-10-06’ → ‘6 октября, вторник’ / ‘6 окт, вт’; сегодня/вчера — словами."""
    t = time.strptime(day, "%Y-%m-%d")
    today = time.strftime("%Y-%m-%d")
    yesterday = time.strftime("%Y-%m-%d", time.localtime(time.time() - 86400))
    if day == today:
        prefix = T("Сегодня")
    elif day == yesterday:
        prefix = T("Вчера")
    else:
        prefix = None
    month = i18n.months_genitive()[t.tm_mon - 1]
    if full:
        wd = i18n.weekdays_full()[t.tm_wday]
    else:
        month, wd = month[:3], i18n.weekdays_short()[t.tm_wday]
    base = (f"{t.tm_mday} {month}, {wd}" if i18n.language() == "ru"
            else f"{wd}, {month} {t.tm_mday}")
    return f"{prefix} · {base}" if prefix else base


class StatsWindow:
    def __init__(self, parent, stats, cfg):
        self.stats = stats
        self.cfg = cfg
        self._thumbs = []  # держим ссылки на ImageTk, иначе их съест GC
        self._day = None

        self.win = tk.Toplevel(parent)
        self.win.withdraw()
        self.win.title(T("Статистика") + " — FocusShield")
        theme.style_window(self.win, resizable=True)
        self.win.minsize(px(640), px(520))

        root = ttk.Frame(self.win, padding=(px(24), px(18), px(24), px(18)))
        root.pack(fill="both", expand=True)
        head = ttk.Frame(root)
        head.pack(fill="x", pady=(0, px(12)))
        ttk.Label(head, text=T("Статистика"), style="Title.TLabel").pack(side="left")
        ttk.Label(head, text=human_day(time.strftime("%Y-%m-%d"), full=True).split(" · ")[-1],
                  style="Muted.TLabel").pack(side="left", padx=px(12), pady=(px(8), 0))

        self.nb = ttk.Notebook(root)
        self.nb.pack(fill="both", expand=True)
        self.tab_overview = ttk.Frame(self.nb, padding=(0, px(14), 0, 0))
        self.tab_photos = ttk.Frame(self.nb, padding=(0, px(14), 0, 0))
        self.nb.add(self.tab_overview, text="  " + T("Обзор") + "  ")
        self.nb.add(self.tab_photos, text="  " + T("Фото по дням") + "  ")

        self._build_overview(self.tab_overview)
        self._build_photos(self.tab_photos)
        self.refresh()

        theme.center_on_screen(self.win, px(780), px(660), y_ratio=5)
        self.win.deiconify()
        pop_to_front(self.win)

    def show_photos_tab(self):
        self.nb.select(self.tab_photos)

    # ================================================================ обзор

    def _build_overview(self, parent):
        tiles = ttk.Frame(parent)
        tiles.pack(fill="x")
        self.tile_vars = {}
        for i, (key, caption) in enumerate((("today", "минут в фокусе сегодня"),
                                            ("sessions", "сессий сегодня"),
                                            ("streak", "дней подряд"),
                                            ("distr", "отвлечений сегодня"))):
            card = ttk.Frame(tiles, style="Card.TFrame", padding=(px(16), px(12)))
            card.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else px(10), 0))
            tiles.columnconfigure(i, weight=1, uniform="tile")
            var = tk.StringVar(value="—")
            self.tile_vars[key] = var
            ttk.Label(card, textvariable=var, style="Stat.TLabel").pack(anchor="w")
            ttk.Label(card, text=T(caption), style="Caption.TLabel").pack(anchor="w")

        chart_card = ttk.Frame(parent, style="Card.TFrame", padding=(px(16), px(12)))
        chart_card.pack(fill="x", pady=(px(12), 0))
        ttk.Label(chart_card, text=T("Последние 7 дней"), style="Strong.TLabel").pack(anchor="w")
        self.chart = theme.canvas(chart_card, height=px(170))
        self.chart.pack(fill="x", pady=(px(6), 0))
        self.chart.bind("<Configure>", lambda e: self._draw_chart())

        list_card = ttk.Frame(parent, style="Card.TFrame", padding=(px(16), px(12)))
        list_card.pack(fill="both", expand=True, pady=(px(12), 0))
        ttk.Label(list_card, text=T("Намерения"), style="Strong.TLabel").pack(anchor="w",
                                                                         pady=(0, px(6)))
        cols = ("time", "plan", "outcome", "intention")
        self.tree = ttk.Treeview(list_card, columns=cols, show="headings", height=6)
        for col, text, w, stretch in (("time", "Когда", 110, False), ("plan", "Мин", 60, False),
                                      ("outcome", "Итог", 110, False),
                                      ("intention", "Намерение", 300, True)):
            self.tree.heading(col, text=T(text), anchor="w")
            self.tree.column(col, width=px(w), anchor="w", stretch=stretch)
        self.tree.pack(fill="both", expand=True)

    def refresh(self):
        s = self.stats
        self.tile_vars["today"].set(f"{s.today_minutes():.0f}")
        self.tile_vars["sessions"].set(str(s.today_sessions()))
        self.tile_vars["streak"].set(str(s.streak()))
        self.tile_vars["distr"].set(str(s.distractions_today()))
        self._week = s.last7_minutes()
        self._draw_chart()

        self.tree.delete(*self.tree.get_children())
        for r in s.recent_intentions(30):
            t = time.strftime("%d.%m %H:%M", time.localtime(r["started_at"]))
            mins = r["actual_min"] if r["actual_min"] is not None else r["planned_min"]
            self.tree.insert("", "end", values=(
                t, f"{mins or 0:.0f}", T(OUTCOME_LABELS[r["outcome"]]) if r["outcome"] in OUTCOME_LABELS else "—",
                (r["intention"] or "").replace("\n", " ")[:160]))
        self._refresh_days()

    def _draw_chart(self):
        c = self.chart
        data = getattr(self, "_week", None)
        if not data:
            return
        c.delete("all")
        w, h = max(px(300), c.winfo_width()), c.winfo_height()
        top, bottom = px(22), h - px(26)
        top_val = max([m for _, m in data] + [60])
        slot = w / len(data)
        bw = min(px(44), slot * 0.56)
        today = time.strftime("%Y-%m-%d")

        for frac in (0.5, 1.0):  # лёгкая сетка
            y = bottom - (bottom - top) * frac
            c.create_line(0, y, w, y, fill=P["track"], dash=(2, 4))
        for i, (day, minutes) in enumerate(data):
            x0 = slot * i + (slot - bw) / 2
            hgt = (bottom - top) * minutes / top_val
            is_today = day == today
            color = P["focus"] if is_today else theme.mix(P["focus"], P["bg"], 0.45)
            if minutes > 0:
                theme.rounded_rect(c, x0, bottom - max(hgt, px(6)), x0 + bw, bottom, px(6),
                                   fill=color, outline="")
                c.create_text(x0 + bw / 2, bottom - max(hgt, px(6)) - px(9),
                              text=f"{minutes:.0f}", fill=P["text"] if is_today else P["muted"],
                              font=F["caption"])
            else:
                c.create_line(x0, bottom - 1, x0 + bw, bottom - 1, fill=P["track"], width=px(3))
            wd = i18n.weekdays_short()[time.strptime(day, "%Y-%m-%d").tm_wday]
            c.create_text(x0 + bw / 2, h - px(10), text=T("сегодня") if is_today else wd,
                          fill=P["text"] if is_today else P["muted"],
                          font=F["body_strong"] if is_today else F["caption"])

    # ================================================================ фото

    def _build_photos(self, parent):
        parent.columnconfigure(1, weight=1)
        parent.rowconfigure(0, weight=1)

        left = ttk.Frame(parent)
        left.grid(row=0, column=0, sticky="ns", padx=(0, px(14)))
        self.days = ttk.Treeview(left, columns=("day", "n"), show="headings",
                                 selectmode="browse", height=12)
        self.days.heading("day", text=T("День"), anchor="w")
        self.days.heading("n", text=T("Фото"), anchor="e")
        self.days.column("day", width=px(170), anchor="w")
        self.days.column("n", width=px(68), anchor="e")
        self.days.pack(fill="y", expand=True)
        self.days.bind("<<TreeviewSelect>>", lambda e: self._select_day())
        self.days.bind("<Double-1>", lambda e: self._open_day())
        ttk.Button(left, text=f"{ICON['folder']}  " + T("Все фото"),
                   command=lambda: webcam.open_folder()).pack(fill="x", pady=(px(10), 0))

        right = ttk.Frame(parent)
        right.grid(row=0, column=1, sticky="nsew")
        bar = ttk.Frame(right)
        bar.pack(fill="x", pady=(0, px(10)))
        self.day_title = ttk.Label(bar, text="", style="Subtitle.TLabel")
        self.day_title.pack(side="left")
        self.open_btn = ttk.Button(bar, text=f"{ICON['folder']}  " + T("Открыть папку дня"),
                                   style="Accent.TButton", command=self._open_day)
        self.open_btn.pack(side="right")

        self.gallery = theme.ScrollFrame(right)
        self.gallery.pack(fill="both", expand=True)
        self.gallery.canvas.bind("<Configure>", self._on_gallery_resize, add="+")
        ttk.Label(right, style="Caption.TLabel", justify="left",
                  text=T("Снимки делаются только во время фокус-сессий и хранятся только "
                         "на этом компьютере. Удаляются автоматически через {n} дн.",
                         n=self.cfg.get("webcam_retention_days", 14)),
                  wraplength=px(480)).pack(anchor="w", pady=(px(8), 0))

    def _gallery_cols(self) -> int:
        """Сколько миниатюр влезает в строку при текущей ширине галереи."""
        avail = self.gallery.canvas.winfo_width()
        if avail <= 1:
            avail = px(480)
        return max(1, avail // (px(THUMB) + px(10)))

    def _on_gallery_resize(self, _e=None):
        if self._day and self._gallery_cols() != getattr(self, "_cols", None):
            if getattr(self, "_resize_job", None):
                self.win.after_cancel(self._resize_job)
            self._resize_job = self.win.after(150, self._render_gallery)

    def _refresh_days(self):
        self.days.delete(*self.days.get_children())
        days = webcam.list_photo_days()
        for day, n in days:
            self.days.insert("", "end", iid=day, values=(human_day(day), n))
        if days:
            pick = self._day if self._day in dict(days) else days[0][0]
            self.days.selection_set(pick)
            self.days.see(pick)
        else:
            self._day = None
            self._render_gallery()

    def _select_day(self):
        sel = self.days.selection()
        self._day = sel[0] if sel else None
        self._render_gallery()

    def _open_day(self):
        webcam.open_folder(self._day)

    def _render_gallery(self):
        inner = self.gallery.inner
        for w in inner.winfo_children():
            w.destroy()
        self._thumbs.clear()
        self.gallery.to_top()

        if not self._day:
            self.day_title.config(text=T("Фото пока нет"))
            self.open_btn.state(["disabled"])
            ttk.Label(inner, style="Muted.TLabel", justify="left", wraplength=px(420),
                      text=T("Снимки появятся во время фокус-сессий, если камера или "
                             "скриншоты включены в настройках.")).pack(anchor="w", pady=px(20))
            return
        self.open_btn.state(["!disabled"])
        photos = webcam.photos_for_day(self._day)
        self.day_title.config(text=f"{human_day(self._day, full=True)} · "
                                    + T("{n} фото", n=len(photos)))

        size = px(THUMB)
        cols = self._cols = self._gallery_cols()
        for i, (path, hhmm, kind) in enumerate(photos):
            cell = ttk.Frame(inner, padding=(0, 0, px(10), px(12)))
            cell.grid(row=i // cols, column=i % cols, sticky="nw")
            try:
                img = Image.open(path)
                img.thumbnail((size, size))
                thumb = ImageTk.PhotoImage(img)
                self._thumbs.append(thumb)
                lbl = tk.Label(cell, image=thumb, cursor="hand2", bd=0,
                               bg=P["bg"], highlightthickness=1,
                               highlightbackground=P["stroke"])
                lbl.bind("<Button-1>", lambda e, p=path: os.startfile(p))
            except Exception:
                lbl = ttk.Label(cell, text=T("файл повреждён"), style="Caption.TLabel")
            lbl.pack()
            ttk.Label(cell, text=f"{hhmm} · {T(KIND_LABELS[kind])}", style="Caption.TLabel").pack(
                anchor="w", pady=(px(3), 0))
