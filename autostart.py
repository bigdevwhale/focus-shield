# -*- coding: utf-8 -*-
"""Автозапуск через Планировщик задач: при входе в Windows, с наивысшими
правами (без UAC-окна на каждый запуск), без лимита времени, с рестартом
при падении. Используется и exe (сам себя регистрирует), и install.py.

Регистрация/удаление задачи требуют прав администратора.
"""
import base64
import logging
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

log = logging.getLogger("focus.autostart")

TASK_NAME = "FocusShield"
CREATE_NO_WINDOW = 0x08000000


def _ps(script: str) -> subprocess.CompletedProcess:
    # -EncodedCommand (UTF-16LE base64) — пробелы и кириллица в путях без проблем.
    enc = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    return subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                           "-EncodedCommand", enc], capture_output=True, text=True,
                          timeout=120, creationflags=CREATE_NO_WINDOW)


def _q(s) -> str:
    """Строка в одинарных кавычках PowerShell."""
    return "'" + str(s).replace("'", "''") + "'"


def registered_command():
    """(путь к exe, аргументы) зарегистрированной задачи или None."""
    r = subprocess.run(["schtasks", "/Query", "/TN", TASK_NAME, "/XML"], capture_output=True,
                       text=True, creationflags=CREATE_NO_WINDOW, timeout=30)
    if r.returncode != 0 or not r.stdout.strip():
        return None
    try:
        root = ET.fromstring(r.stdout.strip().lstrip("﻿"))
    except ET.ParseError:
        return None
    ns = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
    cmd = root.find(".//t:Exec/t:Command", ns)
    args = root.find(".//t:Exec/t:Arguments", ns)
    if cmd is None:
        return None
    return cmd.text.strip().strip('"'), (args.text or "").strip() if args is not None else ""


def is_registered_for(executable) -> bool:
    cur = registered_command()
    if not cur:
        return False
    try:
        return Path(cur[0]).resolve() == Path(executable).resolve()
    except OSError:
        return False


def register(executable, arguments: str = "", workdir=None) -> bool:
    workdir = workdir or Path(executable).parent
    action = f"New-ScheduledTaskAction -Execute {_q(executable)} -WorkingDirectory {_q(workdir)}"
    if arguments:
        action += f" -Argument {_q(arguments)}"
    r = _ps(f"""
$ErrorActionPreference = 'Stop'
$action = {action}
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName {_q(TASK_NAME)} -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
Write-Output 'TASK_OK'
""")
    ok = "TASK_OK" in (r.stdout or "")
    if ok:
        log.info("автозапуск зарегистрирован: %s %s", executable, arguments)
    else:
        log.error("не удалось зарегистрировать автозапуск: %s %s",
                  (r.stdout or "").strip()[-300:], (r.stderr or "").strip()[-300:])
    return ok


def unregister() -> None:
    _ps(f"Unregister-ScheduledTask -TaskName {_q(TASK_NAME)} -Confirm:$false "
        f"-ErrorAction SilentlyContinue")
    log.info("автозапуск удалён")


def run_now() -> None:
    subprocess.run(["schtasks", "/Run", "/TN", TASK_NAME], capture_output=True,
                   creationflags=CREATE_NO_WINDOW, timeout=30)
