## Download

**[FocusShield.exe](https://github.com/bigdevwhale/focus-shield/releases/latest/download/FocusShield.exe)** — a single file, nothing else to install.

1. Run `FocusShield.exe` and accept the administrator prompt (blocking websites,
   apps and folders needs admin rights).
2. FocusShield adds itself to Windows startup and appears in the tray —
   drag its icon out of the `^` overflow area so it's always visible.
3. Press **▶** on the floating timer to start your first focus session.

> Windows SmartScreen may warn about an unrecognized app because the exe isn't
> code-signed. Click **More info → Run anyway**. You can verify the download
> with `FocusShield.exe.sha256`, or build it yourself with `python build.py`.

**Uninstall:** run `FocusShield.exe --uninstall` — it removes autostart and lifts
all blocks. Your stats and photos stay in `%LOCALAPPDATA%\focus-shield`.

**Something stuck blocked?** `FocusShield.exe --unblock`.
