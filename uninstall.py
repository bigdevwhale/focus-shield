# -*- coding: utf-8 -*-
"""Полное удаление FocusShield:

    python uninstall.py

  1. убирает задачу планировщика (автозапуск);
  2. чистит нашу секцию в hosts (если приложение не запущено);
  3. снимает запреты на папки;
  4. данные (статистика, снимки) не трогает — их можно удалить руками из
     %LOCALAPPDATA%\\focus-shield.
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
    ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable,
                                              params, None, 1)
    if ret <= 32:
        print("Отказано в UAC — удаление отменено.")
        sys.exit(1)
    sys.exit(0)


def main() -> int:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if "--elevated" not in sys.argv and not is_admin():
        print("Запрашиваю права администратора…")
        elevate_and_exit()

    script = f"""
$ErrorActionPreference = 'SilentlyContinue'
Unregister-ScheduledTask -TaskName '{TASK_NAME}' -Confirm:$false
Write-Output 'DONE'
"""
    enc = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                    "-EncodedCommand", enc], capture_output=True, timeout=60)
    print("Задача планировщика удалена.")

    # Чистим hosts напрямую, без импорта main-модулей.
    sys.path.insert(0, str(BASE_DIR))
    import hosts  # noqa: E402

    try:
        changed = hosts.normalize()
        print("hosts очищен." if changed else "hosts уже чист.")
    except Exception as e:
        print(f"Не удалось почистить hosts: {e}")
        print("Аварийная разблокировка — выполни в консоли от администратора:")
        print("  powershell -Command \"(Get-Content C:\\Windows\\System32\\drivers\\etc\\hosts) "
              "| Where-Object {$_ -notmatch 'focus-shield'} | Set-Content "
              "C:\\Windows\\System32\\drivers\\etc\\hosts\"")
        return 1
    try:
        import blocker  # noqa: E402
        blocker.allow_all()
        print("Запреты на папки сняты.")
    except Exception as e:
        print(f"Не удалось снять запреты на папки: {e}")
        print("Вручную (от администратора): python blocker.py --unblock")
        return 1
    print("\nFocusShield удалён. Данные лежат в %LOCALAPPDATA%\\focus-shield (можно удалить).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
