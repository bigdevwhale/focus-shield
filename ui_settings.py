# -*- coding: utf-8 -*-
"""Окно настроек: секции-карточки в прокручиваемой области, футер с
«Отмена / Сохранить». on_save(changes) получает только изменяемые здесь
ключи — позиция таймера и прочее состояние не затираются.

Подписи передаются в хелперы (_section, _spin, _switch, _radios) русским
исходником и переводятся внутри них через i18n.T.
"""
import tkinter as tk
from pathlib import Path
from tkinter import ttk

import blocker
import focus_apps
import i18n
import theme
import webcam
from config import DEFAULT_BLOCKLIST
from i18n import T
from theme import ICON, px
from ui_dialogs import pop_to_front


class SettingsWindow:
    def __init__(self, parent, cfg, on_save):
        self.cfg = dict(cfg)
        self.on_save = on_save
        self.app_vars = {}  # exe -> BooleanVar (галочки по запущенным окнам)

        self.win = tk.Toplevel(parent)
        self.win.withdraw()
        self.win.title(T("Настройки") + " — FocusShield")
        theme.style_window(self.win, resizable=True)
        self.win.minsize(px(560), px(480))

        head = ttk.Frame(self.win, padding=(px(24), px(18), px(24), px(8)))
        head.pack(fill="x")
        ttk.Label(head, text=T("Настройки"), style="Title.TLabel").pack(anchor="w")

        foot = ttk.Frame(self.win, padding=(px(24), px(12), px(24), px(16)))
        foot.pack(side="bottom", fill="x")
        ttk.Button(foot, text=T("Сохранить"), style="Accent.TButton",
                   command=self._save).pack(side="right")
        ttk.Button(foot, text=T("Отмена"), command=self.win.destroy).pack(side="right",
                                                                          padx=(0, px(8)))
        ttk.Separator(self.win).pack(side="bottom", fill="x")

        self.scroll = theme.ScrollFrame(self.win)
        self.scroll.pack(fill="both", expand=True, padx=(px(24), px(8)))
        self.body = self.scroll.inner

        self._build()
        self.win.bind("<Escape>", lambda e: self.win.destroy())
        theme.center_on_screen(self.win, px(640), px(760), y_ratio=6)
        self.win.deiconify()
        pop_to_front(self.win)

    # ---------- строительные блоки ----------

    def _section(self, title: str, subtitle: str = None):
        card = ttk.Frame(self.body, style="Card.TFrame", padding=(px(18), px(14)))
        card.pack(fill="x", pady=(0, px(12)), padx=(0, px(12)))
        ttk.Label(card, text=T(title), style="Subtitle.TLabel").pack(anchor="w")
        if subtitle:
            ttk.Label(card, text=T(subtitle), style="Caption.TLabel", wraplength=px(520),
                      justify="left").pack(anchor="w", pady=(px(2), 0))
        inner = ttk.Frame(card)
        inner.pack(fill="x", pady=(px(10), 0))
        return inner

    def _spin(self, parent, row: int, label: str, value: int, lo: int, hi: int, unit: str):
        ttk.Label(parent, text=T(label)).grid(row=row, column=0, sticky="w", pady=px(4))
        var = tk.StringVar(value=str(value))
        ttk.Spinbox(parent, from_=lo, to=hi, width=6, textvariable=var,
                    font=theme.F["body"]).grid(row=row, column=1, sticky="w", padx=px(12))
        ttk.Label(parent, text=T(unit), style="Muted.TLabel").grid(row=row, column=2, sticky="w")
        return var

    def _switch(self, parent, text: str, value: bool, caption: str = None):
        var = tk.BooleanVar(value=value)
        ttk.Checkbutton(parent, text=T(text), variable=var,
                        style="Switch.TCheckbutton").pack(anchor="w", pady=(px(4), 0))
        if caption:
            ttk.Label(parent, text=T(caption), style="Caption.TLabel", wraplength=px(500),
                      justify="left").pack(anchor="w", padx=(px(46), 0))
        return var

    def _radios(self, parent, value: str, options, translate: bool = True):
        var = tk.StringVar(value=value)
        for key, text in options:
            ttk.Radiobutton(parent, text=T(text) if translate else text, value=key,
                            variable=var).pack(anchor="w", pady=px(2))
        return var

    def _label(self, parent, text: str, style: str = "Strong.TLabel", **pack):
        ttk.Label(parent, text=T(text), style=style).pack(anchor="w", **pack)

    def _list_text(self, parent, items, height: int):
        t = theme.text_widget(parent, height=height, width=40)
        t.configure(font=("Consolas", 10))
        t.insert("1.0", "\n".join(items))
        t.pack(fill="x", pady=(px(4), 0))
        return t

    # ---------- секции ----------

    def _build(self):
        c = self.cfg

        s = self._section("Язык", "Применится к окнам, открытым после сохранения.")
        self.v_lang = self._radios(s, c["language"], i18n.LANGUAGES, translate=False)

        s = self._section("Таймер на экране",
                          "Плавающее окно поверх всех окон: время, намерение и кнопки. "
                          "Перетаскивается мышью, правый клик — меню.")
        self.v_widget = self._radios(s, c["timer_widget"], (
            ("always", "Всегда"),
            ("session", "Только во время сессии и перерыва"),
            ("off", "Не показывать")))

        s = self._section("Помодоро")
        grid = ttk.Frame(s)
        grid.pack(anchor="w")
        self.v_work = self._spin(grid, 0, "Фокус", c["work_min"], 1, 240, "мин")
        self.v_short = self._spin(grid, 1, "Короткий перерыв", c["short_break_min"], 1, 60, "мин")
        self.v_long = self._spin(grid, 2, "Длинный перерыв", c["long_break_min"], 1, 120, "мин")
        self.v_cycles = self._spin(grid, 3, "Длинный перерыв после", c["cycles"], 1, 12,
                                   "фокусов")
        self.v_auto = self._switch(s, "Автопродолжение", c["auto_continue"],
                                   "Перерыв и следующий фокус начинаются сами.")
        self.v_strict = self._switch(s, "Строгий режим", c["strict"],
                                     "Выйти из фокуса досрочно можно только подождав 10 секунд "
                                     "и введя фразу.")

        s = self._section("Блокировка сайтов",
                          "Один домен в строке, действует только во время фокуса. "
                          "Поддомены пишутся отдельно: youtube.com и www.youtube.com.")
        self.t_block = self._list_text(s, c["blocklist"], 7)
        row = ttk.Frame(s)
        row.pack(fill="x", pady=(px(6), 0))
        ttk.Button(row, text=T("Вернуть стандартный список"),
                   command=self._reset_blocklist).pack(side="left")
        self.v_doh = self._switch(s, "Блокировать DoH-серверы", c["block_doh"],
                                  "Чтобы «безопасный DNS» браузера не обходил блокировку.")

        s = self._section("Страж вкладок",
                          "Блокировка через hosts не действует, если браузер ходит через "
                          "прокси или VPN (например, v2rayN). Страж смотрит на заголовок "
                          "вкладки и закрывает её, если в нём есть одно из слов ниже.")
        self.v_guard = self._switch(s, "Закрывать такие вкладки во время фокуса", c["tab_guard"])
        self._label(s, "Слова в заголовке вкладки, по одному в строке:", "Muted.TLabel",
                    pady=(px(8), 0))
        self.t_keywords = self._list_text(s, c["title_keywords"], 3)

        s = self._section("Запрет приложений и папок",
                          "Во время фокуса запрещённые приложения закрываются, а "
                          "запрещённые папки не открываются — ни в Проводнике, ни в других "
                          "программах. После сессии всё снова доступно.")
        self._label(s, "Приложения (имя exe, по одному в строке):")
        self.t_blocked_apps = self._list_text(s, c["blocked_apps"], 3)
        row = ttk.Frame(s)
        row.pack(fill="x", pady=(px(6), px(12)))
        ttk.Label(row, text=T("Из запущенных:"), style="Muted.TLabel").pack(side="left",
                                                                           padx=(0, px(8)))
        self.v_app_pick = tk.StringVar()
        self.app_pick = ttk.Combobox(row, textvariable=self.v_app_pick, state="readonly",
                                     width=34, postcommand=self._fill_app_pick)
        self.app_pick.pack(side="left")
        ttk.Button(row, text=T("Добавить"), command=self._add_blocked_app).pack(
            side="left", padx=(px(8), 0))
        self._label(s, "Папки (полный путь, по одной в строке):")
        self.t_blocked_folders = self._list_text(s, c["blocked_folders"], 3)
        row = ttk.Frame(s)
        row.pack(fill="x", pady=(px(6), 0))
        ttk.Button(row, text=f"{ICON['folder']}  " + T("Выбрать папку…"),
                   command=self._add_blocked_folder).pack(side="left")
        self.folder_err = ttk.Label(s, text="", style="Danger.TLabel", wraplength=px(500),
                                    justify="left")
        self.folder_err.pack(anchor="w", pady=(px(4), 0))

        s = self._section("Фокус-приложения",
                          "Во время фокуса FocusShield возвращает тебя к выбранным "
                          "приложениям.")
        self._label(s, "Когда возвращать:")
        self.v_trigger = self._radios(s, c["focus_trigger"], (
            ("minimized", "Приложение свёрнуто"),
            ("background", "Приложение не на переднем плане (ушёл в другое окно)"),
            ("both", "В обоих случаях")))
        grid = ttk.Frame(s)
        grid.pack(anchor="w", pady=(px(6), 0))
        self.v_restore = self._spin(grid, 0, "Через", c["restore_after_sec"], 5, 3600, "сек")

        bar = ttk.Frame(s)
        bar.pack(fill="x", pady=(px(10), px(4)))
        ttk.Label(bar, text=T("Открытые сейчас приложения:"),
                  style="Strong.TLabel").pack(side="left")
        ttk.Button(bar, text=f"{ICON['refresh']}  " + T("Обновить"),
                   command=self._fill_apps).pack(side="right")
        self.apps_box = ttk.Frame(s)
        self.apps_box.pack(fill="x")
        self._label(s, "Другие (имя exe, по одному в строке):", "Muted.TLabel",
                    pady=(px(8), 0))
        self.t_apps = self._list_text(s, [], 2)
        self._fill_apps()

        s = self._section("Снимки", "Только во время фокуса, хранятся только на этом "
                                    "компьютере, в папках по дням.")
        self.v_cam = self._switch(s, "Фото с веб-камеры", c["webcam_enabled"])
        grid = ttk.Frame(s)
        grid.pack(anchor="w", padx=(px(46), 0))
        self.v_cam_every = self._spin(grid, 0, "Раз в", max(1, c["webcam_every_sec"] // 60),
                                      1, 120, "мин")
        self.v_screen = self._switch(s, "Скриншоты экрана", c["screen_enabled"])
        grid = ttk.Frame(s)
        grid.pack(anchor="w", padx=(px(46), 0))
        self.v_screen_every = self._spin(grid, 0, "Раз в", max(1, c["screen_every_sec"] // 60),
                                         1, 120, "мин")
        grid = ttk.Frame(s)
        grid.pack(anchor="w", pady=(px(8), 0))
        self.v_cam_keep = self._spin(grid, 0, "Хранить", c["webcam_retention_days"], 1, 365,
                                     "дней")
        ttk.Button(s, text=f"{ICON['folder']}  " + T("Открыть папку с фото"),
                   command=lambda: webcam.open_folder()).pack(anchor="w", pady=(px(8), 0))

        s = self._section("Оформление")
        self.v_theme = self._radios(s, c["theme"], (
            ("system", "Как в Windows"), ("light", "Светлая"), ("dark", "Тёмная")))

    # ---------- приложения ----------

    def _fill_apps(self):
        chosen = {str(e).lower() for e in self.cfg.get("focus_apps", [])}
        chosen |= {e for e, v in self.app_vars.items() if v.get()}
        for w in self.apps_box.winfo_children():
            w.destroy()
        self.app_vars.clear()
        try:
            windows = focus_apps.list_windows()
        except Exception:
            windows = []
        seen = {}
        for w in windows:
            if w["exe"] in ("pythonw.exe", "python.exe", "explorer.exe"):
                continue
            seen.setdefault(w["exe"], w["title"])
        for exe, title in sorted(seen.items()):
            var = tk.BooleanVar(value=exe in chosen)
            self.app_vars[exe] = var
            row = ttk.Frame(self.apps_box)
            row.pack(fill="x")
            ttk.Checkbutton(row, text=exe, variable=var).pack(side="left")
            ttk.Label(row, text=title[:48], style="Caption.TLabel").pack(side="left",
                                                                         padx=px(8))
        # Выбранные, но сейчас не запущенные — в ручной список.
        manual = sorted(chosen - set(seen))
        self.t_apps.delete("1.0", "end")
        self.t_apps.insert("1.0", "\n".join(manual))

    def _fill_app_pick(self):
        try:
            exes = sorted({w["exe"] for w in focus_apps.list_windows()})
        except Exception:
            exes = []
        self.app_pick.configure(values=[e for e in exes if e in blocker.sanitize_apps([e])])

    def _add_blocked_app(self):
        exe = self.v_app_pick.get().strip()
        if exe and exe not in _lines(self.t_blocked_apps):
            self.t_blocked_apps.insert("end", ("\n" if _lines(self.t_blocked_apps) else "") + exe)
        self.v_app_pick.set("")

    def _add_blocked_folder(self):
        from tkinter import filedialog
        path = filedialog.askdirectory(parent=self.win,
                                       title=T("Папка, запрещённая во время фокуса"))
        if not path:
            return
        path = str(Path(path))
        reason = blocker.check_folder(path)
        if reason:
            self.folder_err.config(text=T("Нельзя заблокировать {path}: {reason}",
                                          path=path, reason=reason))
            return
        self.folder_err.config(text="")
        current = _paths(self.t_blocked_folders)
        if path not in current:
            self.t_blocked_folders.insert("end", ("\n" if current else "") + path)

    def _reset_blocklist(self):
        current = _lines(self.t_block)
        merged = list(dict.fromkeys(DEFAULT_BLOCKLIST + current))
        self.t_block.delete("1.0", "end")
        self.t_block.insert("1.0", "\n".join(merged))

    # ---------- сохранение ----------

    def _save(self):
        def num(var, default, lo=1):
            try:
                return max(lo, int(var.get()))
            except (ValueError, tk.TclError):
                return default

        folders = _paths(self.t_blocked_folders)
        bad = [(f, r) for f in folders if (r := blocker.check_folder(f))]
        if bad:
            self.folder_err.config(text="; ".join(
                T("Нельзя заблокировать {path}: {reason}", path=f, reason=r) for f, r in bad))
            self.folder_err.update_idletasks()
            # прокрутить к ошибке
            self.scroll.canvas.yview_moveto(
                max(0.0, self.folder_err.winfo_y() / max(1, self.body.winfo_height()) - 0.2))
            return

        picked = [e for e, v in self.app_vars.items() if v.get()]
        changes = {
            "language": self.v_lang.get(),
            "blocked_apps": blocker.sanitize_apps(_lines(self.t_blocked_apps)),
            "blocked_folders": folders,
            "timer_widget": self.v_widget.get(),
            "work_min": num(self.v_work, 25),
            "short_break_min": num(self.v_short, 5),
            "long_break_min": num(self.v_long, 15),
            "cycles": num(self.v_cycles, 4),
            "auto_continue": bool(self.v_auto.get()),
            "strict": bool(self.v_strict.get()),
            "blocklist": _lines(self.t_block),
            "block_doh": bool(self.v_doh.get()),
            "tab_guard": bool(self.v_guard.get()),
            "title_keywords": _lines(self.t_keywords),
            "focus_trigger": self.v_trigger.get(),
            "restore_after_sec": num(self.v_restore, 60, lo=5),
            "focus_apps": sorted(set(picked + _lines(self.t_apps))),
            "webcam_enabled": bool(self.v_cam.get()),
            "webcam_every_sec": num(self.v_cam_every, 5) * 60,
            "screen_enabled": bool(self.v_screen.get()),
            "screen_every_sec": num(self.v_screen_every, 5) * 60,
            "webcam_retention_days": num(self.v_cam_keep, 14),
            "theme": self.v_theme.get(),
        }
        if self.on_save:
            self.on_save(changes)
        self.win.destroy()


def _lines(text_widget) -> list:
    return [x.strip().lower() for x in text_widget.get("1.0", "end").splitlines() if x.strip()]


def _paths(text_widget) -> list:
    """Как _lines, но без смены регистра — это пути."""
    return list(dict.fromkeys(x.strip().strip('"') for x in
                              text_widget.get("1.0", "end").splitlines() if x.strip()))
