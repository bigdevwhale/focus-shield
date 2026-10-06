# -*- coding: utf-8 -*-
"""Работа с окнами во время фокуса (только ctypes/winapi, без psutil):

* FocusAppsWatcher — принудительно разворачивает свёрнутые фокус-приложения;
* TabGuard — закрывает вкладку браузера с YouTube (и др.) по заголовку окна.
  В отличие от hosts, работает через любой прокси/VPN/DoH: SOCKS-прокси
  резолвит имена сам, и hosts его не касается, а заголовок окна — касается.
"""
import ctypes
import logging
import os
import re
import time
from ctypes import wintypes

log = logging.getLogger("focus.apps")

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

SW_RESTORE = 9
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
FLASHW_ALL = 0x3
FLASHW_TIMERNOFG = 0xC

_WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def _exe_of_pid(pid: int) -> str:
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(len(buf))
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return buf.value.rsplit("\\", 1)[-1].lower()
    finally:
        kernel32.CloseHandle(h)
    return ""


def _title_of(hwnd) -> str:
    n = user32.GetWindowTextLengthW(hwnd)
    if n <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x80
GW_OWNER = 4
DWMWA_CLOAKED = 14


def _is_app_window(hwnd) -> bool:
    """Окно «как в Alt+Tab»: видимое, не tool-окно, без владельца и не
    скрытое DWM (cloaked — фоновые UWP-окна вроде TextInputHost)."""
    if not user32.IsWindowVisible(hwnd):
        return False
    if user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW:
        return False
    if user32.GetWindow(hwnd, GW_OWNER):
        return False
    cloaked = ctypes.c_int(0)
    ctypes.windll.dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked),
                                               ctypes.sizeof(cloaked))
    return not cloaked.value


def class_of(hwnd) -> str:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def list_windows() -> list:
    """Окна приложений с заголовком: [{hwnd, pid, exe, title, minimized}]."""
    out = []

    def cb(hwnd, _lparam):
        if not _is_app_window(hwnd):
            return True
        title = _title_of(hwnd)
        if not title:
            return True
        pid = wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        exe = _exe_of_pid(pid.value)
        if not exe:
            return True
        out.append({
            "hwnd": hwnd,
            "pid": pid.value,
            "exe": exe,
            "title": title,
            "minimized": bool(user32.IsIconic(hwnd)),
        })
        return True

    user32.EnumWindows(_WNDENUMPROC(cb), 0)
    return out


def force_foreground(hwnd) -> bool:
    """Развернуть и поднять окно на передний план.
    SetForegroundWindow из фонового процесса обычно блокируется foreground
    lock'ом — используем трюк AttachThreadInput. Возвращает True, если окно
    реально стало передним."""
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)

    fg = user32.GetForegroundWindow()
    if fg == hwnd:
        return True
    our_tid = kernel32.GetCurrentThreadId()
    fg_tid = user32.GetWindowThreadProcessId(fg, None) if fg else 0
    attached = False
    if fg_tid and fg_tid != our_tid:
        attached = bool(user32.AttachThreadInput(our_tid, fg_tid, True))
    try:
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    finally:
        if attached:
            user32.AttachThreadInput(our_tid, fg_tid, False)

    ok = user32.GetForegroundWindow() == hwnd
    if not ok:
        # Fallback: мигание в панели задач — лучше, чем ничего.
        class FLASHWINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.UINT), ("hwnd", wintypes.HWND),
                        ("dwFlags", wintypes.DWORD), ("uCount", wintypes.UINT),
                        ("dwTimeout", wintypes.DWORD)]
        info = FLASHWINFO(ctypes.sizeof(FLASHWINFO), hwnd,
                          FLASHW_ALL | FLASHW_TIMERNOFG, 4, 0)
        user32.FlashWindowEx(ctypes.byref(info))
    return ok


TRIGGERS = ("minimized", "background", "both")


class FocusAppsWatcher:
    """Возвращает внимание к фокус-приложениям. Режимы (focus_trigger):

    * minimized  — окно фокус-приложения свёрнуто дольше порога → развернуть;
    * background — передний план занят НЕ фокус-приложением дольше порога
                   (ушёл в другое окно) → вернуть последнее активное
                   фокус-приложение вперёд;
    * both       — оба правила сразу.

    Окна самого FocusShield (диалоги, таймер) уходом не считаются.
    Повторное срабатывание — не чаще раза в порог.
    """

    def __init__(self):
        self._min_since = {}     # hwnd -> ts начала непрерывной свёрнутости
        self._last_restore = {}  # hwnd -> ts последнего принудительного разворота
        self._away_since = None  # ts, с которого передний план не у фокус-приложения
        self._last_tracked_fg = None  # hwnd последнего активного фокус-окна
        self._own_pid = os.getpid()

    def reset(self) -> None:
        self._min_since.clear()
        self._away_since = None

    def update(self, now: float, tracked_exes, threshold_sec: float,
               trigger: str = "minimized") -> list:
        """Возвращает список событий-отвлечений [{exe, title, why}]."""
        tracked = {str(e).lower() for e in tracked_exes}
        if not tracked:
            self.reset()
            return []
        try:
            windows = list_windows()
        except Exception:
            log.exception("list_windows упал")
            return []

        ours = [w for w in windows if w["exe"] in tracked]
        if not ours:  # ни одно фокус-приложение не запущено — нечего возвращать
            self.reset()
            return []
        events = []
        if trigger in ("minimized", "both"):
            events += self._check_minimized(now, ours, threshold_sec)
        if trigger in ("background", "both") and not events:
            events += self._check_background(now, ours, threshold_sec)

        alive = {w["hwnd"] for w in ours}
        for d in (self._min_since, self._last_restore):
            for hwnd in [h for h in d if h not in alive]:
                d.pop(hwnd, None)
        if self._last_tracked_fg not in alive:
            self._last_tracked_fg = None
        return events

    def _restore(self, now, w, why):
        try:
            force_foreground(w["hwnd"])
        except Exception:
            log.exception("force_foreground упал")
            return None
        self._last_restore[w["hwnd"]] = now
        self._min_since.pop(w["hwnd"], None)
        self._away_since = None
        log.info("вернул фокус (%s): %s — %s", why, w["exe"], w["title"])
        return {"exe": w["exe"], "title": w["title"], "why": why}

    def _check_minimized(self, now, ours, threshold) -> list:
        events = []
        for w in ours:
            hwnd = w["hwnd"]
            if not w["minimized"]:
                self._min_since.pop(hwnd, None)
                continue
            since = self._min_since.setdefault(hwnd, now)
            last = self._last_restore.get(hwnd, 0.0)
            if now - since >= threshold and now - last >= threshold:
                ev = self._restore(now, w, "minimized")
                if ev:
                    events.append(ev)
        return events

    def _check_background(self, now, ours, threshold) -> list:
        fg = user32.GetForegroundWindow()
        by_hwnd = {w["hwnd"]: w for w in ours}
        if fg in by_hwnd:  # работаем в фокус-приложении — всё хорошо
            self._last_tracked_fg = fg
            self._away_since = None
            return []
        pid = wintypes.DWORD(0)
        if fg:
            user32.GetWindowThreadProcessId(fg, ctypes.byref(pid))
        if pid.value == self._own_pid:  # окна FocusShield не считаются уходом
            return []
        if self._away_since is None:
            self._away_since = now
            return []
        if now - self._away_since < threshold:
            return []
        target = by_hwnd.get(self._last_tracked_fg) or ours[0]
        if now - self._last_restore.get(target["hwnd"], 0.0) < threshold:
            return []
        ev = self._restore(now, target, "background")
        return [ev] if ev else []


# ---------------------------------------------------------------- TabGuard

BROWSERS = {
    "chrome.exe", "msedge.exe", "firefox.exe", "opera.exe", "brave.exe",
    "vivaldi.exe", "browser.exe", "arc.exe", "chromium.exe", "librewolf.exe",
    "waterfox.exe", "floorp.exe", "zen.exe", "thorium.exe",
}

# Заголовок вкладки: «(3) Видео - YouTube - Opera», «YouTube — Mozilla Firefox».
# Сравниваем СЕГМЕНТЫ целиком, поэтому «как заблокировать youtube - Google
# Поиск» и «youtube.py - Visual Studio Code» не совпадут.
_SEP = re.compile(r"\s[-\u2013\u2014|]\s")
_COUNTER = re.compile(r"^\(\d+\+?\)\s*")

VK_CONTROL = 0x11
VK_W = 0x57
KEYEVENTF_KEYUP = 0x2
SW_MINIMIZE = 6


def title_matches(title: str, keywords) -> bool:
    for seg in _SEP.split(title):
        if _COUNTER.sub("", seg).strip().casefold() in keywords:
            return True
    return False


def close_tab(hwnd, still_matches) -> str:
    """Закрывает активную вкладку окна (Ctrl+W). Перед нажатием ещё раз
    проверяет, что окно на переднем плане и заголовок всё ещё совпадает —
    чтобы не закрыть чужую вкладку. Если окно не вышло вперёд — сворачивает."""
    if not force_foreground(hwnd):
        user32.ShowWindow(hwnd, SW_MINIMIZE)
        return "minimized"
    time.sleep(0.08)
    if user32.GetForegroundWindow() != hwnd or not still_matches(_title_of(hwnd)):
        return "skipped"
    user32.keybd_event(VK_CONTROL, 0, 0, 0)
    user32.keybd_event(VK_W, 0, 0, 0)
    user32.keybd_event(VK_W, 0, KEYEVENTF_KEYUP, 0)
    user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
    return "closed"


class TabGuard:
    COOLDOWN = 3.0  # сек между попытками на одно окно

    def __init__(self):
        self._last = {}

    def update(self, now: float, keywords) -> list:
        kws = {str(k).strip().casefold() for k in keywords if str(k).strip()}
        if not kws:
            return []
        events = []
        try:
            windows = list_windows()
        except Exception:
            log.exception("list_windows упал")
            return events
        for w in windows:
            if w["exe"] not in BROWSERS or not title_matches(w["title"], kws):
                continue
            if now - self._last.get(w["hwnd"], 0.0) < self.COOLDOWN:
                continue
            self._last[w["hwnd"]] = now
            try:
                result = close_tab(w["hwnd"], lambda t: title_matches(t, kws))
            except Exception:
                log.exception("close_tab упал")
                continue
            if result != "skipped":
                log.info("страж вкладок: %s %s — %s", result, w["exe"], w["title"])
                events.append({"exe": w["exe"], "title": w["title"], "result": result})
        return events