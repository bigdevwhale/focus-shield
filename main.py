# -*- coding: utf-8 -*-
"""FocusShield — оркестратор.

Потоковая модель (единственная точка пересечения — queue):
  * главный поток: скрытый Tk root + mainloop; ВСЕ вызовы Tk — отсюда;
  * pystray: icon.run_detached() (собственный поток с message loop),
    колбэки меню только кладут события в очередь;
  * таймеров-потоков нет: root.after(1000, tick) сравнивает time.time()
    с ends_at и гонит переходы состояний.

Запуск: pythonw main.py (через задачу планировщика, повышенным).
Восстановление: при старте hosts всегда нормализуется, затем активная
сессия из state.json возобновляется (блокировка включается заново).
"""
import ctypes
import logging
import os
import queue
import sys
import time
import tkinter as tk
from pathlib import Path

import blocker
import config
import hosts
import i18n
import session as ses
import theme
from focus_apps import FocusAppsWatcher, TabGuard
from i18n import T
from notify import Notifier
from stats import Stats
from tray import Tray
from ui_break import BreakWindow
from ui_dialogs import ask_friction, ask_outcome, ask_start, pop_to_front
from ui_settings import SettingsWindow
from ui_stats import StatsWindow
from ui_widget import TimerWidget
from webcam import ScreenShooter, Webcam, purge_old_photos

log = logging.getLogger("focus.main")

ERROR_ALREADY_EXISTS = 183


def setup_logging() -> None:
    config.ensure_dirs()
    from logging.handlers import RotatingFileHandler
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    fh = RotatingFileHandler(config.LOG_PATH, maxBytes=1_000_000, backupCount=3,
                             encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)
    if sys.stdout is not None:  # консольный запуск — добавляем и консоль
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        root.addHandler(sh)


SHOW_EVENT = "Local\\focus-shield-show"
EVENT_MODIFY_STATE = 0x0002


def single_instance() -> bool:
    """Named mutex: второй инстанс не трогает hosts, а будит первый (событие
    SHOW_EVENT — первый покажет таймер или начнёт сессию) и выходит.
    Local\\ — общая для задачи планировщика и ручного запуска в рамках
    одной логон-сессии, и не требует привилегий. Хэндлы живут до выхода."""
    global _mutex, _show_event
    k32 = ctypes.windll.kernel32
    _mutex = k32.CreateMutexW(None, False, "Local\\focus-shield")
    if k32.GetLastError() == ERROR_ALREADY_EXISTS:
        ev = k32.OpenEventW(EVENT_MODIFY_STATE, False, SHOW_EVENT)
        if ev:
            k32.SetEvent(ev)
            k32.CloseHandle(ev)
        return False
    _show_event = k32.CreateEventW(None, False, False, SHOW_EVENT)  # auto-reset
    return True


def show_requested() -> bool:
    """Второй экземпляр просил показаться? (неблокирующая проверка)"""
    ev = globals().get("_show_event")
    return bool(ev) and ctypes.windll.kernel32.WaitForSingleObject(ev, 0) == 0


def message_box(text: str, error: bool = False) -> None:
    """У exe нет консоли — результат CLI-команд показываем окном."""
    ctypes.windll.user32.MessageBoxW(None, text, "FocusShield", 0x10 if error else 0x40)


def ensure_autostart() -> None:
    """Собранный exe сам прописывает себе автозапуск (и перепрописывает, если
    его переместили). Нужны права администратора — exe их запрашивает."""
    if not config.FROZEN or not is_admin():
        return
    import autostart
    try:
        if not autostart.is_registered_for(sys.executable):
            autostart.register(sys.executable)
    except Exception:
        log.exception("регистрация автозапуска упала")


def run_cli(args) -> int:
    """Служебные команды exe: --uninstall, --unblock. None — запускать приложение."""
    if "--unblock" in args or "--uninstall" in args:
        errors = []
        if "--uninstall" in args and config.FROZEN:
            # Остановить работающий экземпляр, иначе он вернёт блокировки на месте.
            blocker.kill_blocked_apps([Path(sys.executable).name])
        for name, fn in (("hosts", hosts.normalize), ("folders", blocker.allow_all)):
            try:
                fn()
            except Exception as e:
                errors.append(f"{name}: {e}")
        if "--uninstall" in args:
            import autostart
            try:
                autostart.unregister()
            except Exception as e:
                errors.append(f"autostart: {e}")
        if errors:
            message_box("Some steps failed (run as administrator):\n\n" + "\n".join(errors),
                        error=True)
            return 1
        message_box("FocusShield removed from autostart and all blocks lifted.\n\n"
                    f"Your data is kept in {config.DATA_DIR}"
                    if "--uninstall" in args else "All blocks lifted.")
        return 0
    return None


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


class View:
    """Провайдер состояния для callable-текстов трея (потокобезопасно читается
    только то, что пишется в Tk-потоке)."""

    def __init__(self, app):
        self.app = app

    @property
    def state(self):
        return self.app.sm.state

    @property
    def widget_enabled(self):
        return self.app.cfg.get("timer_widget") != "off"

    def status_line(self):
        sm = self.app.sm
        if sm.state == ses.FOCUS:
            return "🎯 " + T("Фокус — {left}  ({n} мин)", left=sm.remaining_str(), n=sm.s.work_min)
        if sm.state == ses.OUTCOME_PENDING:
            return T("Фокус завершён — самоотчёт…")
        if sm.state in (ses.BREAK, ses.LONG_BREAK):
            name = T("Длинный перерыв") if sm.state == ses.LONG_BREAK else T("Перерыв")
            return f"☕ {name} — {sm.remaining_str()}"
        return "FocusShield — " + T("готов к фокусу")

    def menu_status_line(self):
        """Статичная строка для меню: время окончания вместо тикающего
        отсчёта — меню не нужно перестраивать каждую секунду."""
        sm = self.app.sm
        until = time.strftime("%H:%M", time.localtime(sm.s.ends_at)) if sm.s.ends_at else ""
        if sm.state == ses.FOCUS:
            return "🎯 " + T("Фокус до {until}  ({n} мин)", until=until, n=sm.s.work_min)
        if sm.state == ses.OUTCOME_PENDING:
            return T("Фокус завершён — самоотчёт…")
        if sm.state in (ses.BREAK, ses.LONG_BREAK):
            name = T("Длинный перерыв") if sm.state == ses.LONG_BREAK else T("Перерыв")
            return "☕ " + T("{name} до {until}", name=name, until=until)
        return "FocusShield — " + T("готов к фокусу")


class App:
    def __init__(self):
        self.cfg = config.load_config()
        self.stats = Stats(config.DB_PATH)
        self.sm = ses.SessionManager(config.STATE_PATH)
        self.queue = queue.Queue()
        self.watcher = FocusAppsWatcher()
        self.guard = TabGuard()
        self.emit_photo = lambda path, sid: self.queue.put(("photo", {"path": path, "sid": sid}))
        self.webcam = Webcam(self.emit_photo)
        self.screens = ScreenShooter(self.emit_photo)
        self.break_win = None
        self.stats_win = None
        self.settings_win = None
        self._tick_n = 0
        self._in_transition = False  # защита от повторного входа в focus_end

        self.root = tk.Tk()
        self.root.withdraw()
        i18n.set_language(self.cfg["language"])
        theme.apply(self.root, self.cfg["theme"])
        self.view = View(self)
        self.tray = Tray(self.view, self.emit)
        self.notifier = Notifier(self.tray.icon)
        self.widget = TimerWidget(self.root, on_primary=self._widget_primary,
                                  on_menu=self._widget_menu, on_moved=self._widget_moved,
                                  mascot=self.cfg.get("mascot"))
        self.widget.place(self.cfg.get("widget_x"), self.cfg.get("widget_y"))

    # ---------- события трея (кладутся из потока pystray) ----------

    def emit(self, event, **kw):
        self.queue.put((event, kw))

    # ---------- запуск ----------

    def start(self):
        self._startup_recovery()
        self.tray.start()
        self.root.after(100, self._poll)
        self.root.after(200, self._tick)  # первый тик нарисует иконку, тайтл и таймер
        from version import __version__
        log.info("FocusShield %s запущен (admin=%s, exe=%s)", __version__, is_admin(),
                 config.FROZEN)
        if not is_admin():
            self.notifier.toast(
                "FocusShield: " + T("нет прав администратора"),
                T("Блокировка сайтов, папок и приложений не будет работать. Запусти FocusShield от имени администратора."))
        self.root.mainloop()

    def _startup_recovery(self):
        # 0. Чистим старые снимки.
        removed = purge_old_photos(self.cfg.get("webcam_retention_days", 14))
        if removed:
            self.stats.delete_photos(removed)
        # 1. hosts и запреты папок всегда снимаем — от прошлых сессий/падений.
        try:
            hosts.normalize()
        except PermissionError:
            log.error("нет прав на hosts — запуск без повышения?")
        except Exception:
            log.exception("normalize hosts при старте упал")
        try:
            blocker.allow_all()
        except Exception:
            log.exception("снятие запретов папок при старте упало")
        # 2. Возобновляем активную сессию, если была.
        s = self.sm.s
        now = time.time()
        if s.state == ses.FOCUS and s.ends_at > now:
            self._apply_block()
            self._webcam_start()
            self.notifier.toast(T("Фокус восстановлен"),
                                T("Осталось {left}", left=self.sm.remaining_str()))
        elif s.state == ses.FOCUS:  # истёк, пока приложение было мертво
            self._finish_focus(recovered=True)
        elif s.state in (ses.BREAK, ses.LONG_BREAK):
            if s.ends_at > now:
                self._open_break()
            else:
                self.sm.to_idle()
        elif s.state == ses.OUTCOME_PENDING:
            self._finish_focus(recovered=True)

    # ---------- эффекты ----------

    def _apply_block(self):
        """Включить все блокировки фокуса: сайты (hosts) и папки (NTFS).
        Идемпотентно — вызывается и при смене настроек посреди сессии."""
        doms = hosts.domains_for(self.cfg)
        try:
            if doms:
                hosts.apply_block(doms)
            else:
                hosts.normalize()
        except PermissionError:
            log.error("нет прав на hosts — блокировка не включилась")
            self.notifier.toast("FocusShield: " + T("не удалось заблокировать"),
                                T("Нет прав на hosts-файл"))
        except Exception:
            log.exception("apply_block упал")
        try:
            blocker.sync_folders(self.cfg.get("blocked_folders", []))
            self._enforce_apps()
        except Exception:
            log.exception("блокировка папок/приложений упала")

    def _unblock(self):
        try:
            hosts.normalize()
        except Exception:
            log.exception("normalize hosts упал")
        try:
            blocker.allow_all()
        except Exception:
            log.exception("снятие запретов папок упало")

    def _enforce_apps(self):
        """Закрыть запрещённые приложения и окна Проводника с запрещёнными папками."""
        killed = blocker.kill_blocked_apps(self.cfg.get("blocked_apps", []))
        closed = blocker.close_folder_windows(self.cfg.get("blocked_folders", []))
        for exe in killed:
            self.stats.add_distraction(exe)
        if killed or closed:
            what = ", ".join(killed + closed)
            self.notifier.toast(T("Закрыто — ты в фокусе") + " 🛡", what[:100])

    def _webcam_start(self):
        """Запустить периодические снимки (камера и/или экран) по настройкам."""
        sid = self.sm.s.session_db_id
        if self.cfg.get("webcam_enabled"):
            self.webcam.start(sid, self.cfg.get("webcam_every_sec", 300))
        if self.cfg.get("screen_enabled"):
            self.screens.start(sid, self.cfg.get("screen_every_sec", 300))

    def _webcam_stop(self):
        self.webcam.stop()
        self.screens.stop()

    def _open_break(self):
        long = self.sm.state == ses.LONG_BREAK
        minutes = (self.cfg.get("long_break_min", 15) if long
                   else self.cfg.get("short_break_min", 5))
        left = self.sm.remaining() / 60
        self.break_win = BreakWindow(
            self.root, min(minutes, left if left > 0.2 else minutes), long,
            on_skip=lambda: self.emit("skip_break"))

    # ---------- плавающий таймер ----------

    def _widget_data(self) -> dict:
        sm, s = self.sm, self.sm.s
        total = max(1.0, s.ends_at - s.started_at) if s.ends_at else 0
        cycles = self.cfg.get("cycles", 4)
        camera = (self.cfg.get("webcam_enabled") and not self.webcam.disabled)
        # Рост маскота-ростка: доля серии помидоров до длинного перерыва.
        # Внутри фокуса растёт плавно, к длинному перерыву — 1.0 (цветок).
        if sm.state == ses.FOCUS:
            done = 1 - sm.remaining() / total if total else 0
            return {"state": "focus", "remaining": sm.remaining(), "total": total,
                    "title": sm.remaining_str(), "subtitle": s.intention or T("Фокус"),
                    "cycle": s.cycle + 1, "cycles": cycles, "camera": camera,
                    "growth": (s.cycle + max(0.0, min(1.0, done))) / cycles}
        if sm.state in (ses.BREAK, ses.LONG_BREAK):
            name = T("Длинный перерыв") if sm.state == ses.LONG_BREAK else T("Перерыв")
            return {"state": sm.state, "remaining": sm.remaining(), "total": total,
                    "title": sm.remaining_str(),
                    "subtitle": f"{name} · " + T("отойди от экрана"),
                    "cycle": s.cycle or cycles, "cycles": cycles, "camera": False,
                    "growth": (s.cycle or cycles) / cycles}
        if sm.state == ses.OUTCOME_PENDING:
            return {"state": "idle", "remaining": 0, "total": 0, "title": T("Готово"),
                    "subtitle": T("Самоотчёт по сессии…"), "cycle": 0, "cycles": None,
                    "camera": False, "growth": min(1.0, (s.cycle + 1) / cycles)}
        return {"state": "idle", "remaining": 0, "total": 0,
                "title": f"{self.cfg.get('work_min', 25)}:00",
                "subtitle": T("Готов к фокусу — нажми ▶"), "cycle": 0, "cycles": None,
                "camera": False,
                # серия «остыла» — следующий фокус начнёт её заново
                "growth": 0.0 if time.time() - s.started_at > ses.SERIES_TIMEOUT
                else s.cycle / cycles}

    def _sync_widget(self) -> None:
        mode = self.cfg.get("timer_widget", "always")
        # При ручном запуске следующего фокуса таймер остаётся и в простое —
        # иначе после перерыва он исчезнет, и стартовать придётся из трея.
        want = (mode == "always"
                or (mode == "session"
                    and (self.sm.is_active() or not self.cfg.get("auto_next_focus"))))
        self.widget.update(self._widget_data())
        if want:
            self.widget.show()
        else:
            self.widget.hide()

    def _widget_primary(self):
        state = self.sm.state
        if state == ses.FOCUS:
            self.emit("stop_early")
        elif state in (ses.BREAK, ses.LONG_BREAK):
            self.emit("skip_break")
        elif state == ses.IDLE:
            self.emit("start")

    def _widget_menu(self, e):
        m = tk.Menu(self.root, tearoff=0)
        m.add_command(label=T("Статистика"), command=lambda: self.emit("open_stats"))
        m.add_command(label=T("Фото по дням"), command=lambda: self.emit("open_photos"))
        m.add_command(label=T("Настройки"), command=lambda: self.emit("open_settings"))
        m.add_separator()
        m.add_command(label=T("Скрыть таймер"), command=lambda: self.emit("toggle_widget"))
        try:
            m.tk_popup(e.x_root, e.y_root)
        finally:
            m.grab_release()

    def _widget_moved(self, x, y):
        self.cfg["widget_x"], self.cfg["widget_y"] = x, y
        config.save_config(self.cfg)

    # ---------- команды (из очереди) ----------

    def _cmd_start(self):
        if self.sm.state != ses.IDLE:
            return
        res = ask_start(self.root, self.cfg.get("work_min", 25))
        if res is None:
            return
        minutes, intention = res
        sid = self.stats.new_session(time.time(), minutes, intention)
        self.sm.start_focus(minutes, intention, sid)
        self.watcher.reset()
        self._apply_block()
        self._webcam_start()
        self.notifier.toast(T("Фокус: {n} мин", n=minutes), intention or T("Погнали"))
        self.tray.refresh(self.sm.state)
        self._sync_widget()

    def _cmd_tray_click(self):
        if self.sm.state == ses.IDLE:
            self._cmd_start()
        else:
            self.widget.show()
            pop_to_front(self.widget.win)
            self.widget.win.attributes("-topmost", True)

    def _cmd_stop_early(self):
        if self.sm.state != ses.FOCUS:
            return
        if self.cfg.get("strict", True) and not ask_friction(self.root):
            return
        self._finish_focus(outcome="stopped_early", ask=False)
        self.notifier.toast(T("Фокус прерван"), T("Блокировка снята"))

    def _cmd_skip_break(self):
        if self.sm.state not in (ses.BREAK, ses.LONG_BREAK):
            return
        if self.break_win:
            self.break_win.close()
            self.break_win = None
        if self.cfg.get("auto_next_focus"):
            self._start_next_focus()
        else:
            self.sm.to_idle()
            self.tray.refresh(self.sm.state)
        self._sync_widget()

    def _cmd_toggle_widget(self):
        self.cfg["timer_widget"] = "off" if self.cfg.get("timer_widget") != "off" else "always"
        config.save_config(self.cfg)
        self._sync_widget()
        self.tray.rebuild()  # обновить галочку в меню трея
        if self.cfg["timer_widget"] == "off":
            self.notifier.toast(T("Таймер скрыт"), T("Вернуть: трей → «Таймер на экране»"))

    def _cmd_open_stats(self, photos: bool = False):
        if self.stats_win is not None and self.stats_win.win.winfo_exists():
            self.stats_win.refresh()
            self.stats_win.win.deiconify()
            pop_to_front(self.stats_win.win)
        else:
            self.stats_win = StatsWindow(self.root, self.stats, self.cfg)
        if photos:
            self.stats_win.show_photos_tab()

    def _cmd_open_settings(self):
        if self.settings_win is not None and self.settings_win.win.winfo_exists():
            self.settings_win.win.deiconify()
            pop_to_front(self.settings_win.win)
            return

        def on_save(changes):
            theme_changed = changes.get("theme") != self.cfg.get("theme")
            self.cfg.update(changes)
            config.save_config(self.cfg)
            i18n.set_language(self.cfg["language"])
            if theme_changed:
                theme.apply(self.root, self.cfg["theme"])
                self.widget.retheme()
            self.widget.set_mascot(self.cfg["mascot"])
            if self.sm.state == ses.FOCUS:  # новые блокировки и снимки — сразу
                self._apply_block()
                self._webcam_start()
            self._sync_widget()
            self.tray.rebuild()
            self.notifier.toast(T("Настройки сохранены"),
                                T("Тема применится к новым окнам") if theme_changed else "")
        self.settings_win = SettingsWindow(self.root, self.cfg, on_save)

    def _cmd_quit(self):
        if self.sm.state == ses.FOCUS and self.cfg.get("strict", True):
            if not ask_friction(self.root):
                return
        self._shutdown()

    def _cmd_photo(self, path, sid):
        self.stats.add_photo(sid, path)

    # ---------- переходы ----------

    def _finish_focus(self, outcome=None, recovered=False, ask=True):
        """Закрывает фокус: самоотчёт (если возможно), бд, разблок, перерыв."""
        s = self.sm.s
        actual = (time.time() - s.started_at) / 60
        if ask and not recovered:
            outcome = ask_outcome(self.root, s.intention, s.work_min, round(actual)) or "skipped"
        try:
            self.stats.finish_session(s.session_db_id, time.time(),
                                      round(actual, 1), outcome)
        except Exception:
            log.exception("finish_session упал")
        self._unblock()
        self._webcam_stop()
        if outcome == "stopped_early":  # досрочно — без перерыва, сразу idle
            self.sm.to_idle()
            self.tray.refresh(self.sm.state)
            self._sync_widget()
            return
        self.sm.s.cycle += 1
        long = self.sm.s.cycle >= self.cfg.get("cycles", 4)
        if long:
            self.sm.s.cycle = 0
        minutes = self.cfg.get("long_break_min", 15) if long else self.cfg.get("short_break_min", 5)
        if recovered:
            self.sm.to_idle()
        elif self.cfg.get("auto_continue"):
            self.sm.start_break(minutes, long)
            self._open_break()
            self.notifier.toast(T("Фокус завершён — перерыв!"),
                                T("{n} мин без блокировки", n=minutes))
        else:
            self.sm.to_idle()
            self.notifier.toast(T("Фокус завершён"), T("Отдохни — и возвращайся"))
        self.tray.refresh(self.sm.state)
        self._sync_widget()

    def _start_next_focus(self):
        prev = self.sm.s
        suffix = " (" + T("продолжение") + ")"
        intention = (prev.intention or "").removesuffix(suffix)
        tagged = intention + suffix if intention else ""
        sid = self.stats.new_session(time.time(), prev.work_min, tagged)
        self.sm.start_focus(prev.work_min, intention, sid)
        self.watcher.reset()
        self._apply_block()
        self._webcam_start()
        self.notifier.toast(T("Снова фокус: {n} мин", n=prev.work_min), intention or "")
        self.tray.refresh(self.sm.state)
        self._sync_widget()

    # ---------- циклы ----------

    def _poll(self):
        """Слив очереди событий трея/камеры/таймера — только в Tk-потоке."""
        try:
            while True:
                event, kw = self.queue.get_nowait()
                if event != "photo":
                    log.info("событие: %s %s", event, kw or "")
                handler = {
                    "start": self._cmd_start,
                    "tray_click": self._cmd_tray_click,
                    "stop_early": self._cmd_stop_early,
                    "skip_break": self._cmd_skip_break,
                    "toggle_widget": self._cmd_toggle_widget,
                    "open_stats": self._cmd_open_stats,
                    "open_photos": lambda: self._cmd_open_stats(photos=True),
                    "open_settings": self._cmd_open_settings,
                    "quit": self._cmd_quit,
                    "photo": lambda: self._cmd_photo(kw.get("path"), kw.get("sid")),
                }.get(event)
                if handler:
                    try:
                        handler()
                    except Exception:
                        log.exception("handler события %s упал", event)
        except queue.Empty:
            pass
        self.root.after(100, self._poll)

    def _tick(self):
        self._tick_n += 1
        try:
            self._tick_body()
        except Exception:
            log.exception("tick упал")
        self.root.after(1000, self._tick)

    def _tick_body(self):
        now = time.time()
        if show_requested():  # exe запустили ещё раз — показаться
            self.emit("tray_click")
        for event in self.sm.tick(now):
            if event == "focus_end" and not self._in_transition:
                self._in_transition = True
                try:
                    self._finish_focus()
                finally:
                    self._in_transition = False
            elif event.startswith("break_end"):
                if self.break_win:
                    self.break_win.close()
                    self.break_win = None
                if self.cfg.get("auto_next_focus"):
                    self._start_next_focus()
                else:
                    hint = (T("Начни следующую сессию — нажми ▶ на таймере")
                            if self.cfg.get("timer_widget") != "off"
                            else T("Начни следующую сессию из трея"))
                    self.notifier.toast(T("Перерыв закончен"), hint)
                self.tray.refresh(self.sm.state)

        state = self.sm.state
        self.tray.set_title(self.view.status_line())  # живой отсчёт — в tooltip
        self.tray.refresh(state)  # no-op, если состояние не менялось
        self._sync_widget()

        if state == ses.FOCUS:
            if self._tick_n % 2 == 1:
                try:
                    self._enforce_apps()
                except Exception:
                    log.exception("enforce_apps упал")
            if self.cfg.get("tab_guard") and self._tick_n % 2 == 0:
                for ev in self.guard.update(now, self.cfg.get("title_keywords", [])):
                    self.stats.add_distraction(ev["exe"])
                    self.notifier.toast(T("Вкладка закрыта — ты в фокусе") + " 🛡",
                                        ev["title"][:80])
            if self._tick_n % 3 == 0:
                for ev in self.watcher.update(now, self.cfg.get("focus_apps", []),
                                              self.cfg.get("restore_after_sec", 60),
                                              self.cfg.get("focus_trigger", "both")):
                    self.stats.add_distraction(ev["exe"])
                    self.notifier.toast(T("Вернись к фокусу") + " 👀",
                                        T("Вернул: {title}", title=ev["title"][:60]))
            if self._tick_n % 45 == 0:
                try:
                    doms = hosts.domains_for(self.cfg)
                    if doms:
                        hosts.re_assert(doms)
                except Exception:
                    log.exception("re_assert упал")
            if self.cfg.get("webcam_enabled"):
                self.webcam.maybe_tick(self.cfg.get("webcam_every_sec", 300))
            if self.cfg.get("screen_enabled"):
                self.screens.maybe_tick(self.cfg.get("screen_every_sec", 300))

        if self.break_win and state in (ses.BREAK, ses.LONG_BREAK):
            self.break_win.update(now)

    # ---------- выключение ----------

    def _shutdown(self):
        log.info("выключение")
        try:
            if self.sm.state in (ses.FOCUS, ses.OUTCOME_PENDING):
                self.stats.finish_session(self.sm.s.session_db_id, time.time(),
                                          (time.time() - self.sm.s.started_at) / 60,
                                          "stopped_early")
            self.sm.to_idle()
            self._unblock()
            self.stats.close()
        except Exception:
            log.exception("завершение криво прошло")
        finally:
            self.tray.stop()
            self.root.quit()
            os._exit(0)


def main() -> int:
    if any(a in sys.argv for a in ("--uninstall", "--unblock")):
        setup_logging()
        return run_cli(sys.argv)
    if not single_instance():
        return 0
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
    setup_logging()
    ensure_autostart()
    app = App()
    app.start()
    return 0


if __name__ == "__main__":
    sys.exit(main())
