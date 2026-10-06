# -*- coding: utf-8 -*-
"""Установка FocusShield из исходников (запускать один раз):

    python install.py

(Готовому FocusShield.exe установка не нужна — он сам прописывает
автозапуск при первом запуске.)

Что делает:
  1. сам запрашивает права администратора (UAC);
  2. ставит зависимости из requirements.txt;
  3. регистрирует задачу планировщика: автозапуск при входе в систему,
     максимальные права, без лимита времени выполнения, рестарт при падении;
  4. предлагает запустить сразу.
"""
import ctypes
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
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


def pythonw() -> str:
    exe = Path(sys.executable)
    candidate = exe.with_name("pythonw.exe")
    return str(candidate if candidate.exists() else exe)


def register_task() -> None:
    import autostart
    if not autostart.register(pythonw(), f'"{BASE_DIR / "main.py"}"', BASE_DIR):
        print("Не удалось зарегистрировать задачу планировщика (подробности в логе).")
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
