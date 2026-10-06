# -*- coding: utf-8 -*-
"""Иконка в трее (pystray): статичное меню с callable-текстами.

Тексты/видимость пунктов — функции от состояния приложения; тик
оркестратора дёргает icon.update_menu(). Колбэки меню исполняются в потоке
pystray и ТОЛЬКО кладут события в очередь (не трогают Tk/бд).
"""
import logging
from PIL import Image, ImageDraw
from pystray import Icon, Menu, MenuItem

from i18n import T

log = logging.getLogger("focus.tray")

COLORS = {
    "idle": (120, 124, 134, 255),
    "focus": (36, 168, 82, 255),
    "break": (52, 120, 220, 255),
    "warn": (200, 70, 60, 255),
}

_icon_cache = {}


def state_icon(state: str):
    img = _icon_cache.get(state)
    if img is None:
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.ellipse((4, 4, 60, 60), fill=COLORS.get(state, COLORS["idle"]))
        d.ellipse((24, 24, 40, 40), fill=(255, 255, 255, 240))
        _icon_cache[state] = img
    return img


class Tray:
    def __init__(self, view, emit):
        """view — объект-провайдер состояния (state, remaining_str, intention…);
        emit(event, **kw) — потокобезопасная постановка события."""
        self.view = view
        self.emit = emit
        self._last_state = None
        self._last_title = None
        self.icon = Icon(
            "FocusShield",
            icon=state_icon("idle"),
            title="FocusShield",
            menu=self._build_menu(),
        )

    # ---------- меню ----------

    def _build_menu(self):
        v = self.view

        def ev(name):
            return lambda icon, item: self.emit(name)

        def tr(text):  # текст пункта вычисляется при перестройке меню → смена языка на лету
            return lambda item: T(text)

        return Menu(
            # Левый клик по иконке: в простое — новая сессия, иначе — показать таймер.
            MenuItem("default", ev("tray_click"), default=True, visible=lambda i: False),
            MenuItem(lambda i: v.menu_status_line(), None, enabled=lambda i: False),
            Menu.SEPARATOR,
            MenuItem(tr("Начать фокус…"), ev("start"),
                     visible=lambda i: v.state == "idle"),
            MenuItem(tr("Завершить досрочно…"), ev("stop_early"),
                     visible=lambda i: v.state == "focus"),
            MenuItem(tr("Пропустить перерыв"), ev("skip_break"),
                     visible=lambda i: v.state in ("break", "long_break")),
            Menu.SEPARATOR,
            MenuItem(tr("Таймер на экране"), ev("toggle_widget"),
                     checked=lambda i: v.widget_enabled),
            MenuItem(tr("Статистика"), ev("open_stats")),
            MenuItem(tr("Фото по дням"), ev("open_photos")),
            MenuItem(tr("Настройки"), ev("open_settings")),
            Menu.SEPARATOR,
            MenuItem(tr("Выход"), ev("quit")),
        )

    # ---------- вызовы из Tk-потока ----------

    def refresh(self, state: str) -> None:
        """Обновить иконку/меню — ТОЛЬКО при смене состояния.

        update_menu() в pystray делает DestroyMenu текущего меню. Если меню
        в этот момент открыто, клик по пункту теряется — поэтому никакого
        периодического обновления меню, живой отсчёт живёт в tooltip.
        """
        if state == self._last_state:
            return
        self._last_state = state
        self.rebuild(state)

    def rebuild(self, state: str = None) -> None:
        """Перестроить меню без проверки состояния (например, после клика по
        галочке — меню в этот момент уже закрыто)."""
        state = state or self._last_state or "idle"
        try:
            key = "break" if state in ("break", "long_break") else (
                "focus" if state == "focus" else "idle")
            self.icon.icon = state_icon(key)
            self.icon.update_menu()
        except Exception:
            log.exception("refresh трея упал")

    def set_title(self, text: str) -> None:
        text = text[:120]  # лимит NOTIFYICONDATAW.szTip ~128
        if text == self._last_title:
            return
        self._last_title = text
        try:
            self.icon.title = text
        except Exception:
            log.exception("set_title упал")

    def start(self) -> None:
        self.icon.run_detached()

    def stop(self) -> None:
        try:
            self.icon.stop()
        except Exception:
            pass
