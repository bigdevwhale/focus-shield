# -*- coding: utf-8 -*-
"""Сборка FocusShield.exe (один файл, без консоли, с запросом прав админа):

    python build.py            → dist/FocusShield.exe (+ .sha256)

Ставит зависимости и PyInstaller, генерирует иконку и ресурс версии.
Тот же скрипт запускает GitHub Actions при публикации тега v*.
"""
import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BUILD = ROOT / "build"
DIST = ROOT / "dist"
sys.path.insert(0, str(ROOT))


def run(*cmd):
    print("$", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], check=True, cwd=ROOT)


def make_icon() -> Path:
    from tray import state_icon
    ico = BUILD / "FocusShield.ico"
    big = state_icon("focus").resize((256, 256))
    big.save(ico, sizes=[(s, s) for s in (16, 20, 24, 32, 40, 48, 64, 128, 256)])
    return ico


def make_version_file(version: str) -> Path:
    nums = (version.split(".") + ["0", "0", "0", "0"])[:4]
    tup = ", ".join(str(int(n)) for n in nums)
    text = f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers=({tup}), prodvers=({tup}), mask=0x3f, flags=0x0,
                    OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'FocusShield'),
      StringStruct('FileDescription', 'FocusShield — focus timer and distraction blocker'),
      StringStruct('FileVersion', '{version}'),
      StringStruct('InternalName', 'FocusShield'),
      StringStruct('OriginalFilename', 'FocusShield.exe'),
      StringStruct('ProductName', 'FocusShield'),
      StringStruct('ProductVersion', '{version}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""
    path = BUILD / "version_info.txt"
    path.write_text(text, encoding="utf-8")
    return path


def main() -> int:
    from version import __version__
    BUILD.mkdir(exist_ok=True)
    if "--no-deps" not in sys.argv:
        run(sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "-q",
            "-r", ROOT / "requirements.txt", "pyinstaller>=6.0")

    ico = make_icon()
    ver = make_version_file(__version__)
    run(sys.executable, "-m", "PyInstaller", ROOT / "main.py",
        "--name", "FocusShield",
        "--onefile", "--windowed",
        "--uac-admin",                      # блокировкам нужны права администратора
        "--icon", ico, "--version-file", ver,
        "--collect-data", "sv_ttk",         # .tcl и спрайты темы
        "--hidden-import", "pystray._win32",
        "--exclude-module", "unittest", "--exclude-module", "pydoc",
        "--distpath", DIST, "--workpath", BUILD / "pyi", "--specpath", BUILD,
        "--noconfirm", "--clean")

    exe = DIST / "FocusShield.exe"
    digest = hashlib.sha256(exe.read_bytes()).hexdigest()
    (DIST / "FocusShield.exe.sha256").write_text(f"{digest}  FocusShield.exe\n", encoding="ascii")
    print(f"\nOK: {exe}  ({exe.stat().st_size / 1e6:.1f} MB)\nsha256 {digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
