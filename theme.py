# -*- coding: utf-8 -*-
"""Единый дизайн FocusShield: тема Sun Valley (Windows 11 Fluent для ttk),
палитра, шрифты, вспомогательные функции для окон и не-ttk виджетов.

Всё оформление берётся отсюда: P — цвета, F — шрифты, px() — пиксели с
учётом DPI. apply() вызывается один раз на root до создания окон.
"""
import ctypes
import logging
import tkinter as tk
from tkinter import ttk

log = logging.getLogger("focus.theme")

try:
    import sv_ttk
except ImportError:  # без темы всё работает, просто выглядит по-старому
    sv_ttk = None
    log.warning("sv-ttk не установлен — стандартная тема tkinter")

PALETTES = {
    "dark": {
        "bg": "#1c1c1c", "surface": "#262626", "field": "#2b2b2b",
        "stroke": "#3a3a3a", "track": "#333333",
        "text": "#fafafa", "muted": "#a3a3a3", "faint": "#6e6e6e",
        "accent": "#57c8ff", "on_accent": "#000000",
        "focus": "#3dd68c", "break": "#57c8ff", "idle": "#8a8a8a",
        "warn": "#ffb454", "danger": "#ff6b6b", "select": "#2f60d8",
    },
    "light": {
        "bg": "#fafafa", "surface": "#ffffff", "field": "#ffffff",
        "stroke": "#e1e1e1", "track": "#e8e8e8",
        "text": "#1c1c1c", "muted": "#5f5f5f", "faint": "#9a9a9a",
        "accent": "#005fb8", "on_accent": "#ffffff",
        "focus": "#0f9d58", "break": "#005fb8", "idle": "#8a8a8a",
        "warn": "#b85c00", "danger": "#c42b1c", "select": "#2f60d8",
    },
}

DISPLAY = "Segoe UI Variable Display"
TEXT = "Segoe UI Variable Text"
SMALL = "Segoe UI Variable Small"
ICONS = "Segoe Fluent Icons"

F = {
    "display": (DISPLAY, 30, "bold"),
    "title": (DISPLAY, 18, "bold"),
    "subtitle": (DISPLAY, 13, "bold"),
    "stat": (DISPLAY, 22, "bold"),
    "body": (TEXT, 10),
    "body_strong": (TEXT, 10, "bold"),
    "body_large": (TEXT, 12),
    "caption": (SMALL, 9),
    "icon": (ICONS, 11),
    "icon_large": (ICONS, 16),
}

# Глифы Segoe Fluent Icons
ICON = {
    "play": "", "stop": "", "next": "", "more": "",
    "close": "", "settings": "", "folder": "",
    "camera": "", "chart": "", "check": "",
    "refresh": "", "eye": "", "shield": "",
}

P = dict(PALETTES["dark"])
P["dark"] = True
_scale = 1.0
_icon_img = None


def system_is_dark() -> bool:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
            return winreg.QueryValueEx(k, "AppsUseLightTheme")[0] == 0
    except OSError:
        return True


def px(n: float) -> int:
    """Пиксели с учётом DPI (шрифты в пунктах масштабирует сам Tk)."""
    return int(round(n * _scale))


def apply(root, mode: str = "system") -> None:
    global _scale
    dark = system_is_dark() if mode == "system" else mode == "dark"
    name = "dark" if dark else "light"
    P.clear()
    P.update(PALETTES[name])
    P["dark"] = dark
    try:
        _scale = max(1.0, root.winfo_fpixels("1i") / 96)
    except tk.TclError:
        _scale = 1.0

    if sv_ttk is not None:
        sv_ttk.set_theme(name, root)
        # sv-ttk красит фон в обработчике <<ThemeChanged>> на root. Root у нас
        # скрыт, и событие до создания окон не обрабатывается — без явного
        # вызова фреймы и подписи остаются стандартными серыми.
        try:
            root.tk.call("configure_colors")
        except tk.TclError:
            log.warning("sv-ttk: configure_colors недоступен", exc_info=True)
    root.configure(bg=P["bg"])

    s = ttk.Style(root)
    s.configure("TLabel", font=F["body"])
    s.configure("Title.TLabel", font=F["title"])
    s.configure("Subtitle.TLabel", font=F["subtitle"])
    s.configure("Display.TLabel", font=F["display"])
    s.configure("Stat.TLabel", font=F["stat"])
    s.configure("Strong.TLabel", font=F["body_strong"])
    s.configure("Large.TLabel", font=F["body_large"])
    s.configure("Muted.TLabel", font=F["body"], foreground=P["muted"])
    s.configure("Caption.TLabel", font=F["caption"], foreground=P["muted"])
    s.configure("Accent.TLabel", font=F["body_strong"], foreground=P["accent"])
    s.configure("Danger.TLabel", font=F["body_strong"], foreground=P["danger"])
    s.configure("Icon.TLabel", font=F["icon_large"], foreground=P["accent"])
    s.configure("Treeview", rowheight=px(30))


def style_window(win, resizable: bool = False) -> None:
    """Фон, иконка и тёмный/светлый заголовок окна (DWM, Windows 11)."""
    global _icon_img
    win.configure(bg=P["bg"])
    win.resizable(resizable, resizable)
    try:
        if _icon_img is None:
            from PIL import ImageTk
            from tray import state_icon
            _icon_img = ImageTk.PhotoImage(state_icon("focus").resize((32, 32)))
        win.iconphoto(False, _icon_img)
    except Exception:
        pass
    try:
        win.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
        val = ctypes.c_int(1 if P["dark"] else 0)
        # DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(val), 4)
    except Exception:
        pass


def round_corners(win) -> None:
    """Скруглённые углы Windows 11 для безрамочных окон (DWMWA_WINDOW_CORNER_PREFERENCE)."""
    try:
        win.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
        val = ctypes.c_int(2)  # DWMWCP_ROUND
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(val), 4)
    except Exception:
        pass


def text_widget(parent, height: int = 3, **kw) -> tk.Text:
    """tk.Text в стиле полей ввода темы."""
    t = tk.Text(
        parent, height=height, wrap="word", font=F["body_large"],
        bg=P["field"], fg=P["text"], insertbackground=P["text"],
        selectbackground=P["select"], selectforeground="#ffffff",
        relief="flat", borderwidth=0, padx=px(10), pady=px(8),
        highlightthickness=1, highlightbackground=P["stroke"],
        highlightcolor=P["accent"], **kw)
    return t


def canvas(parent, **kw) -> tk.Canvas:
    return tk.Canvas(parent, bg=kw.pop("bg", P["bg"]), highlightthickness=0,
                     borderwidth=0, **kw)


def rounded_rect(c: tk.Canvas, x0, y0, x1, y1, r, **kw):
    """Скруглённый прямоугольник на канвасе (полигон со сглаживанием)."""
    r = max(0, min(r, (x1 - x0) / 2, (y1 - y0) / 2))
    pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1,
           x1 - r, y1, x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
    return c.create_polygon(pts, smooth=True, **kw)


class ScrollFrame(ttk.Frame):
    """Вертикально прокручиваемая область: содержимое кладётся в .inner.
    Колесо мыши перехватывается, только пока курсор над областью."""

    def __init__(self, parent, **kw):
        super().__init__(parent, **kw)
        self.canvas = canvas(self)
        self.bar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.bar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.bar.pack(side="right", fill="y")
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(
            scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(
            self._win, width=e.width))
        self.bind("<Enter>", lambda e: self.canvas.bind_all("<MouseWheel>", self._wheel))
        self.bind("<Leave>", lambda e: self.canvas.unbind_all("<MouseWheel>"))

    def _wheel(self, e):
        if self.inner.winfo_reqheight() > self.canvas.winfo_height():
            self.canvas.yview_scroll(-1 * (e.delta // 120), "units")

    def to_top(self):
        self.canvas.yview_moveto(0)


def center_on_screen(win, w: int = None, h: int = None, y_ratio: float = 3) -> None:
    win.update_idletasks()
    w = w or win.winfo_reqwidth()
    h = h or win.winfo_reqheight()
    x = (win.winfo_screenwidth() - w) // 2
    y = max(0, (win.winfo_screenheight() - h) // y_ratio)
    win.geometry(f"{w}x{h}+{x}+{y}")


def mix(c1: str, c2: str, t: float) -> str:
    """Смешать два #rrggbb цвета: t=0 → c1, t=1 → c2."""
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))


def state_color(state: str) -> str:
    if state == "focus":
        return P["focus"]
    if state in ("break", "long_break"):
        return P["break"]
    return P["idle"]
