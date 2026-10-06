# -*- coding: utf-8 -*-
"""Запрет приложений и папок на время фокуса.

* Приложения: процессы из blocked_apps завершаются (опрос раз в ~2 с).
  Системные процессы и сам FocusShield заблокировать нельзя.
* Папки: на папку ставится NTFS-запрет чтения (Deny RX) для текущего
  пользователя — открыть её не сможет ни Проводник, ни любое приложение.
  Запрет только на саму папку, без наследования: мгновенно даже для
  огромных деревьев. Уже открытые окна Проводника с этой папкой
  закрываются по заголовку.

Отказоустойчивость как у hosts: перед установкой запрета путь пишется в
denied_folders.json, при старте приложения и в конце сессии все запреты
снимаются (allow_all), а при возобновлении фокуса ставятся заново.

CLI для аварийной разблокировки:  python blocker.py --unblock
"""
import ctypes
import json
import logging
import os
import subprocess
import sys
from ctypes import wintypes
from pathlib import Path

import config
from i18n import T

log = logging.getLogger("focus.blocker")

kernel32 = ctypes.windll.kernel32
user32 = ctypes.windll.user32
CREATE_NO_WINDOW = 0x08000000
DENY_STATE = config.DATA_DIR / "denied_folders.json"

# Процессы, которые запрещать нельзя: без них ломается Windows или сам FocusShield.
PROTECTED_APPS = {
    "explorer.exe", "dwm.exe", "csrss.exe", "winlogon.exe", "wininit.exe",
    "services.exe", "lsass.exe", "smss.exe", "svchost.exe", "system",
    "fontdrvhost.exe", "sihost.exe", "ctfmon.exe", "conhost.exe",
    "taskhostw.exe", "runtimebroker.exe", "searchhost.exe",
    "startmenuexperiencehost.exe", "shellexperiencehost.exe", "textinputhost.exe",
    "applicationframehost.exe", "securityhealthsystray.exe", "msmpeng.exe",
    "python.exe", "pythonw.exe", "powershell.exe", "cmd.exe",
}


# ================================================================ приложения

class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_void_p),
                ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long),
                ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_wchar * 260)]


kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


def _processes():
    """[(pid, exe_lower)] всех процессов."""
    TH32CS_SNAPPROCESS = 0x2
    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if not snap or snap == INVALID_HANDLE_VALUE:
        return []
    out = []
    try:
        e = PROCESSENTRY32W()
        e.dwSize = ctypes.sizeof(e)
        ok = kernel32.Process32FirstW(snap, ctypes.byref(e))
        while ok:
            out.append((e.th32ProcessID, e.szExeFile.lower()))
            ok = kernel32.Process32NextW(snap, ctypes.byref(e))
    finally:
        kernel32.CloseHandle(snap)
    return out


def sanitize_apps(apps) -> list:
    out = []
    for a in apps:
        a = str(a).strip().lower().rsplit("\\", 1)[-1]
        if a and not a.endswith(".exe"):
            a += ".exe"
        if a and a not in PROTECTED_APPS and a not in out:
            out.append(a)
    return out


def kill_blocked_apps(apps) -> list:
    """Завершает процессы из списка. Возвращает [exe] реально закрытых."""
    wanted = set(sanitize_apps(apps))
    if not wanted:
        return []
    PROCESS_TERMINATE = 0x1
    me = os.getpid()
    killed = []
    for pid, exe in _processes():
        if exe not in wanted or pid == me:
            continue
        h = kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
        if not h:
            continue
        try:
            if kernel32.TerminateProcess(h, 1):
                killed.append(exe)
        finally:
            kernel32.CloseHandle(h)
    if killed:
        log.info("закрыты запрещённые приложения: %s", ", ".join(sorted(set(killed))))
    return sorted(set(killed))


# ================================================================ папки

_sid_cache = None


def _user_sid() -> str:
    """SID текущего пользователя (‘S-1-5-21-…’) — не зависит от языка системы."""
    global _sid_cache
    if _sid_cache is None:
        r = subprocess.run(["whoami", "/user", "/fo", "csv", "/nh"], capture_output=True,
                           text=True, creationflags=CREATE_NO_WINDOW, timeout=15)
        _sid_cache = r.stdout.strip().rsplit(",", 1)[-1].strip().strip('"')
    return _sid_cache


def _forbidden_reason(path: Path):
    """Почему эту папку блокировать нельзя (или None)."""
    p = path.resolve()
    if not p.is_dir():
        return T("папка не найдена")
    if p.parent == p:
        return T("это корень диска")
    windir = Path(os.environ.get("WINDIR", r"C:\Windows")).resolve()
    critical = [windir, Path(sys.prefix).resolve(), config.BASE_DIR.resolve(),
                config.DATA_DIR.resolve(), Path.home().resolve()]
    for env in ("ProgramFiles", "ProgramFiles(x86)", "ProgramData", "APPDATA", "LOCALAPPDATA"):
        if os.environ.get(env):
            critical.append(Path(os.environ[env]).resolve())
    for c in critical:
        if p == c or c.is_relative_to(p) or (c != Path.home().resolve() and p.is_relative_to(c)):
            return T("системная или служебная папка ({path})", path=c)
    return None


def check_folder(path: str):
    """Для UI: None если папку можно блокировать, иначе причина."""
    try:
        return _forbidden_reason(Path(path))
    except OSError as e:
        return str(e)


def _icacls(args) -> bool:
    r = subprocess.run(["icacls", *args], capture_output=True, text=True,
                       creationflags=CREATE_NO_WINDOW, timeout=30)
    if r.returncode != 0:
        log.warning("icacls %s → %s %s", args, r.returncode, (r.stdout + r.stderr).strip()[:300])
    return r.returncode == 0


def _load_denied() -> list:
    try:
        return json.loads(DENY_STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _save_denied(paths) -> None:
    tmp = DENY_STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(sorted(set(paths)), ensure_ascii=False), encoding="utf-8")
    tmp.replace(DENY_STATE)


def sync_folders(wanted) -> list:
    """Привести запреты к списку wanted: снять лишние, поставить недостающие.
    Возвращает список реально заблокированных папок."""
    sid = _user_sid()
    applied = set(_load_denied())
    target = set()
    for raw in wanted:
        p = Path(str(raw).strip().strip('"'))
        reason = check_folder(str(p))
        if reason:
            log.warning("папку %s не блокирую: %s", p, reason)
            continue
        target.add(str(p.resolve()))

    for path in sorted(applied - target):
        if not Path(path).exists() or _icacls([path, "/remove:d", f"*{sid}"]):
            applied.discard(path)
    _save_denied(applied)

    for path in sorted(target - applied):
        applied.add(path)
        _save_denied(applied)  # write-ahead: сначала запомнить, потом запретить
        if not _icacls([path, "/deny", f"*{sid}:(RX)"]):
            applied.discard(path)
            _save_denied(applied)
    if target:
        log.info("папки заблокированы: %s", ", ".join(sorted(applied)))
    return sorted(applied)


def allow_all() -> None:
    """Снять все наши запреты на папки (конец сессии, старт, аварийно)."""
    if _load_denied():
        sync_folders([])


def close_folder_windows(folders) -> list:
    """Закрыть окна Проводника, в заголовке которых имя заблокированной папки
    («Имя - File Explorer» / «Имя - Проводник»). Возвращает их заголовки."""
    from focus_apps import class_of, list_windows, title_matches
    names = {Path(str(f).strip().strip('"')).name.casefold() for f in folders}
    names |= {str(Path(str(f).strip().strip('"'))).casefold() for f in folders}
    names.discard("")
    if not names:
        return []
    closed = []
    WM_CLOSE = 0x0010
    for w in list_windows():
        if w["exe"] == "explorer.exe" and class_of(w["hwnd"]) == "CabinetWClass" \
                and title_matches(w["title"], names):
            user32.PostMessageW(w["hwnd"], WM_CLOSE, 0, 0)
            closed.append(w["title"])
    if closed:
        log.info("закрыты окна Проводника: %s", closed)
    return closed


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if "--unblock" in sys.argv:
        allow_all()
        print("folders unblocked")
    else:
        print("usage: python blocker.py --unblock")
