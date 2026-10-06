# -*- coding: utf-8 -*-
"""Тосты Windows: winotify (чистый питон, работает из повышенного процесса),
fallback — balloon pystray (icon.notify), крайний fallback — лог."""
import logging

log = logging.getLogger("focus.notify")

try:
    from winotify import Notification
    WINOTIFY_OK = True
except ImportError:
    Notification = None
    WINOTIFY_OK = False
    log.warning("winotify не установлен — тосты через fallback")


class Notifier:
    def __init__(self, icon=None):
        self.icon = icon  # pystray.Icon для fallback-уведомлений

    def toast(self, title: str, body: str = "") -> None:
        if WINOTIFY_OK:
            try:
                n = Notification(app_id="FocusShield", title=title, msg=body or "")
                n.show()
                return
            except Exception:
                log.exception("winotify не сработал, пробую fallback")
        if self.icon is not None:
            try:
                self.icon.notify(message=body or title, title=title)
                return
            except Exception:
                log.exception("icon.notify тоже не сработал")
        log.info("TOAST: %s | %s", title, body)
