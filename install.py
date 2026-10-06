# -*- coding: utf-8 -*-
"""Установка FocusShield (запускать один раз):

    python install.py

Что делает:
  1. сам запрашивает права администратора (UAC);
  2. ставит зависимости из requirements.txt;
  3. регистрирует задачу планировщика: автозапуск при входе в систему,
     максимальные права, без лимита времени выполнения, рестарт при падении;
  4. предлагает запустить сразу.
"""
import base64
import ctypes
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
TASK_NAME = "FocusShield"


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def elevate_and_exit() -> None:
    params = f'"{Path(__file__).resolve()}" --elevated'
    ret = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, params, None, 1  # SW_SHOWNORMAL
    )
    if ret <= 32:
        print("Отказано в UAC — установка отменена.")
        sys.exit(1)
    sys.exit(0)


def run_ps(script: str) -> subprocess.CompletedProcess:
    enc = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    return subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-EncodedCommand", enc],
        capture_output=True, text=True, timeout=120)


def pythonw() -> str:
    exe = Path(sys.executable)
    candidate = exe.with_name("pythonw.exe")
    return str(candidate if candidate.exists() else exe)


def register_task() -> None:
    main_py = BASE_DIR / "main.py"
    work_dir = BASE_DIR
    script = f"""
$ErrorActionPreference = 'Stop'
$action = New-ScheduledTaskAction -Execute '{pythonw()}' -Argument '"{main_py}"' -WorkingDirectory '{work_dir}'
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
Register-ScheduledTask -TaskName '{TASK_NAME}' -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
Write-Output 'TASK_OK'
"""
    r = run_ps(script)
    if "TASK_OK" not in (r.stdout or ""):
        print("Не удалось зарегистрировать задачу планировщика:")
        print(r.stdout or "")
        print(r.stderr or "")
        sys.exit(1)
    print("Задача планировщика зарегистрирована (автозапуск при входе).")


def install_deps() -> None:
    print("Ставлю зависимости (pystray, Pillow, winotify, opencv-python)…")
    r = subprocess.run([sys.executable, "-m", "pip", "install", "-r",
                        str(BASE_DIR / "requirements.txt")],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout or "")
        print(r.stderr or "")
        print("pip не смог поставить зависимости.")
        sys.exit(1)


def main() -> None:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if "--elevated" not in sys.argv and not is_admin():
        print("Запрашиваю права администратора…")
        elevate_and_exit()
    assert is_admin(), "нужны права администратора"

    install_deps()
    register_task()

    print("\nГотово! FocusShield стартует при входе в Windows.")
    ans = input("Запустить сейчас? [y/N] ").strip().lower()
    if ans == "y":
        subprocess.run(["schtasks", "/Run", "/TN", TASK_NAME], capture_output=True)
        print("Запущено — ищи иконку в трее (может быть в скрытых ^).")


if __name__ == "__main__":
    main()
