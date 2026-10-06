# -*- coding: utf-8 -*-
"""Модальные диалоги: новая сессия, самоотчёт, выход из фокуса.

Все окна — Toplevel над скрытым root, только из Tk-потока. Во время
открытого диалога вложенный event loop продолжает крутить after-тики,
поэтому таймеры не останавливаются.
"""
import random
import tkinter as tk
from tkinter import ttk

import i18n
import theme
from i18n import T
from theme import ICON, P, px

PRESETS = (15, 25, 50, 90)


def pop_to_front(win) -> None:
    """Принудительно вынести окно на передний план.

    FocusShield работает повышенным и фоновым процессом — Windows таким не
    отдаёт foreground, и новые окна открываются ПОЗАДИ всех. Топмост на
    миг + lift + focus_force решают это надёжно.
    """
    try:
        win.attributes("-topmost", True)
        win.lift()
        win.focus_force()
        win.after(400, lambda: win.attributes("-topmost", False))
    except Exception:
        pass


def _dialog(parent, title: str):
    win = tk.Toplevel(parent)
    win.withdraw()
    win.title(title)
    theme.style_window(win)
    body = ttk.Frame(win, padding=(px(28), px(24), px(28), px(20)))
    body.pack(fill="both", expand=True)
    return win, body


def _show_modal(win, parent) -> None:
    # НЕ win.transient(parent): root у нас скрыт (withdraw), а transient-окно
    # со скрытым хозяином Tk на Windows тоже держит скрытым — диалог невидим.
    theme.center_on_screen(win)
    win.deiconify()
    pop_to_front(win)
    try:
        win.wait_visibility()
        win.grab_set()  # модальность — только после показа, иначе TclError
    except tk.TclError:
        pass
    parent.wait_window(win)


def _footer(body):
    ttk.Separator(body).pack(fill="x", pady=(px(20), px(14)))
    row = ttk.Frame(body)
    row.pack(fill="x")
    return row


# ---------------------------------------------------------------- новая сессия

def ask_start(parent, default_minutes: int = 25):
    """Длительность + намерение. Возвращает (minutes, intention) или None."""
    win, body = _dialog(parent, T("Новая фокус-сессия"))
    result = {"v": None}

    ttk.Label(body, text=T("Новая фокус-сессия"), style="Title.TLabel").pack(anchor="w")
    ttk.Label(body, text=T("Пока идёт сессия, сайты из списка блокировки недоступны."),
              style="Muted.TLabel").pack(anchor="w", pady=(px(2), px(18)))

    ttk.Label(body, text=T("Длительность"), style="Strong.TLabel").pack(anchor="w")
    minutes = tk.IntVar(value=default_minutes)
    row = ttk.Frame(body)
    row.pack(anchor="w", pady=(px(6), px(18)))
    for m in PRESETS:
        ttk.Radiobutton(row, text=T("{n} мин", n=m), value=m, variable=minutes,
                        style="Toggle.TButton", width=7).pack(side="left", padx=(0, px(6)))
    ttk.Label(row, text=T("или"), style="Muted.TLabel").pack(side="left", padx=(px(6), px(6)))
    spin = ttk.Spinbox(row, from_=1, to=240, width=4, textvariable=minutes,
                       font=theme.F["body"])
    spin.pack(side="left")
    ttk.Label(row, text=T("мин"), style="Muted.TLabel").pack(side="left", padx=(px(6), 0))

    ttk.Label(body, text=T("Намерение"), style="Strong.TLabel").pack(anchor="w")
    ttk.Label(body, text=T("Что конкретно будет готово к концу сессии?"),
              style="Muted.TLabel").pack(anchor="w", pady=(px(2), px(6)))
    txt = theme.text_widget(body, height=3, width=48)
    txt.pack(fill="x")
    ttk.Label(body, text=T("Хорошо: «дописать README и отправить PR». Плохо: «поработать»."),
              style="Caption.TLabel").pack(anchor="w", pady=(px(6), 0))

    def ok(_e=None):
        try:
            m = int(minutes.get())
        except (tk.TclError, ValueError):
            m = 0
        if not 1 <= m <= 240:
            spin.focus_set()
            return "break"
        result["v"] = (m, txt.get("1.0", "end").strip())
        win.destroy()
        return "break"

    def cancel(_e=None):
        win.destroy()

    foot = _footer(body)
    ttk.Button(foot, text=f"{ICON['play']}  " + T("Начать фокус"), style="Accent.TButton",
               command=ok).pack(side="right")
    ttk.Button(foot, text=T("Отмена"), command=cancel).pack(side="right", padx=(0, px(8)))
    ttk.Label(foot, text=T("Enter — начать · Shift+Enter — новая строка"),
              style="Caption.TLabel").pack(side="left")

    txt.bind("<Return>", ok)
    txt.bind("<Shift-Return>", lambda e: None)  # обычный перевод строки
    win.bind("<Escape>", cancel)
    win.protocol("WM_DELETE_WINDOW", cancel)
    win.after(50, txt.focus_set)
    _show_modal(win, parent)
    return result["v"]


# ---------------------------------------------------------------- самоотчёт

def ask_outcome(parent, intention: str, planned_min: int, actual_min: int):
    """Возврат к намерению в конце фокуса: done | partial | no | None."""
    win, body = _dialog(parent, T("Сессия завершена"))
    result = {"v": None}

    head = ttk.Frame(body)
    head.pack(fill="x")
    ttk.Label(head, text=ICON["check"], style="Icon.TLabel").pack(side="left", padx=(0, px(12)))
    titles = ttk.Frame(head)
    titles.pack(side="left")
    ttk.Label(titles, text=T("Сессия завершена"), style="Title.TLabel").pack(anchor="w")
    ttk.Label(titles, text=T("{a} из {p} мин в фокусе", a=actual_min, p=planned_min),
              style="Muted.TLabel").pack(anchor="w")

    if intention:
        card = ttk.Frame(body, style="Card.TFrame", padding=px(16))
        card.pack(fill="x", pady=(px(18), 0))
        ttk.Label(card, text=T("Намерение"), style="Caption.TLabel").pack(anchor="w")
        ttk.Label(card, text=intention, style="Large.TLabel",
                  wraplength=px(420)).pack(anchor="w", pady=(px(4), 0))

    ttk.Label(body, text=T("Получилось?"), style="Strong.TLabel").pack(anchor="w",
                                                                    pady=(px(18), px(8)))

    def pick(v):
        result["v"] = v
        win.destroy()

    row = ttk.Frame(body)
    row.pack(fill="x")
    for i, (key, text, style) in enumerate((("done", T("Да, сделал"), "Accent.TButton"),
                                            ("partial", T("Частично"), "TButton"),
                                            ("no", T("Не вышло"), "TButton"))):
        ttk.Button(row, text=f"{text}  ({i + 1})", style=style,
                   command=lambda k=key: pick(k)).pack(side="left", padx=(0, px(8)),
                                                      expand=True, fill="x")
        win.bind(str(i + 1), lambda e, k=key: pick(k))

    win.protocol("WM_DELETE_WINDOW", lambda: pick(None))
    _show_modal(win, parent)
    return result["v"]


# ---------------------------------------------------------------- выход из фокуса

def ask_friction(parent, wait_sec: int = 10) -> bool:
    """Трение для досрочного выхода: подождать и ввести фразу.
    Главная (и подсвеченная) кнопка — «Остаться в фокусе»."""
    phrase = random.choice(i18n.PHRASES[i18n.language()])
    win, body = _dialog(parent, T("Выйти из фокуса?"))
    result = {"ok": False}
    left = {"n": wait_sec}

    ttk.Label(body, text=T("Выйти из фокуса?"), style="Title.TLabel").pack(anchor="w")
    ttk.Label(body, text=T("Блокировка снимется, а сессия засчитается как прерванная."),
              style="Muted.TLabel").pack(anchor="w", pady=(px(2), px(16)))

    card = ttk.Frame(body, style="Card.TFrame", padding=px(16))
    card.pack(fill="x")
    ttk.Label(card, text=T("Чтобы выйти, введи фразу:"), style="Caption.TLabel").pack(anchor="w")
    ttk.Label(card, text=phrase, style="Subtitle.TLabel",
              foreground=P["danger"]).pack(anchor="w", pady=(px(4), px(10)))
    var = tk.StringVar()
    entry = ttk.Entry(card, textvariable=var, font=theme.F["body_large"])
    entry.pack(fill="x")

    bar = ttk.Progressbar(body, maximum=wait_sec, value=0)
    bar.pack(fill="x", pady=(px(14), px(4)))
    hint = ttk.Label(body, text="", style="Caption.TLabel")
    hint.pack(anchor="w")

    foot = _footer(body)
    stay = ttk.Button(foot, text=T("Остаться в фокусе"), style="Accent.TButton",
                      command=win.destroy)
    stay.pack(side="right")
    leave = ttk.Button(foot, text=T("Выйти"))
    leave.pack(side="right", padx=(0, px(8)))

    def ready() -> bool:
        return left["n"] <= 0 and var.get().strip().casefold() == phrase

    def refresh(*_):
        if left["n"] > 0:
            hint.config(text=T("Кнопка «Выйти» станет доступна через {n} с", n=left["n"]))
        elif var.get().strip().casefold() != phrase:
            hint.config(text=T("Введи фразу точно как написано"))
        else:
            hint.config(text=T("Можно выйти"))
        leave.state(["!disabled"] if ready() else ["disabled"])

    def countdown():
        if left["n"] > 0 and win.winfo_exists():
            left["n"] -= 1
            bar.configure(value=wait_sec - left["n"])
            refresh()
            win.after(1000, countdown)

    def confirm(_e=None):
        if ready():
            result["ok"] = True
            win.destroy()

    leave.config(command=confirm)
    var.trace_add("write", refresh)
    entry.bind("<Return>", confirm)
    win.bind("<Escape>", lambda e: win.destroy())
    win.protocol("WM_DELETE_WINDOW", win.destroy)
    refresh()
    win.after(1000, countdown)
    win.after(50, entry.focus_set)
    _show_modal(win, parent)
    return result["ok"]
