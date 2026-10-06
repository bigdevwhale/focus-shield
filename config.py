# -*- coding: utf-8 -*-
"""Конфигурация FocusShield: дефолты + загрузка/сохранение config.json."""
import json
import logging
import os
from pathlib import Path

log = logging.getLogger("focus.config")

APP_NAME = "focus-shield"
BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"

# Каталог данных вне папки с кодом: hosts-лог, sqlite, снимки камеры.
DATA_DIR = Path(os.environ.get("LOCALAPPDATA", str(BASE_DIR))) / APP_NAME
DB_PATH = DATA_DIR / "stats.db"
PHOTOS_DIR = DATA_DIR / "photos"
STATE_PATH = DATA_DIR / "state.json"
LOG_PATH = DATA_DIR / "focus.log"

# hosts не умеет wildcard — только точные FQDN.
DEFAULT_BLOCKLIST = [
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtube-nocookie.com",
    "youtu.be",
    "i.ytimg.com",
    "s.ytimg.com",
]

DEFAULTS = {
    "work_min": 25,            # длительность фокус-сессии
    "short_break_min": 5,      # короткий перерыв
    "long_break_min": 15,      # длинный перерыв
    "cycles": 4,               # фокусов до длинного перерыва
    "strict": True,            # досрочный стоп только через диалог трения
    "auto_continue": True,     # автоматически начинать перерыв/следующий фокус
    "blocklist": list(DEFAULT_BLOCKLIST),  # домены, блокируемые на время фокуса
    "block_doh": True,         # блокировать DoH-endpoints на время сессии
    "focus_apps": [],          # имена exe, которые должны быть в фокусе
    "restore_after_sec": 60,   # порог для возврата к фокус-приложению
    # когда возвращать: minimized — свёрнуто; background — не на переднем
    # плане (ушёл в другое окно); both — оба правила
    "focus_trigger": "both",
    "webcam_enabled": True,    # снимки камеры во время фокуса
    "webcam_every_sec": 300,   # период снимков
    "webcam_retention_days": 14,  # сколько дней хранить снимки (камера и экран)
    "screen_enabled": False,   # скриншоты экрана во время фокуса
    "screen_every_sec": 300,   # период скриншотов
    # Страж вкладок: закрывает вкладку браузера, если сегмент заголовка окна
    # совпал с ключевым словом. Работает через любой прокси/VPN/DoH.
    "tab_guard": True,
    "title_keywords": ["youtube", "youtube music"],
    "blocked_apps": [],        # exe, которые закрываются во время фокуса
    "blocked_folders": [],     # папки, недоступные во время фокуса (NTFS deny)
    "timer_widget": "always",  # плавающий таймер: always | session | off
    "widget_x": None,          # позиция таймера (None — по умолчанию)
    "widget_y": None,
    "theme": "system",         # system | light | dark
    "language": "en",          # en | ru
}

_INT_KEYS = ("work_min", "short_break_min", "long_break_min", "cycles",
             "restore_after_sec", "webcam_every_sec", "webcam_retention_days",
             "screen_every_sec")
_BOOL_KEYS = ("strict", "auto_continue", "block_doh", "webcam_enabled", "tab_guard",
              "screen_enabled")
_LIST_KEYS = ("blocklist", "focus_apps", "title_keywords", "blocked_apps")
_PATH_LIST_KEYS = ("blocked_folders",)  # регистр путей сохраняем
_CHOICE_KEYS = {
    "focus_trigger": ("minimized", "background", "both"),
    "timer_widget": ("always", "session", "off"),
    "theme": ("system", "light", "dark"),
    "language": ("en", "ru"),
}
_POS_KEYS = ("widget_x", "widget_y")  # могут быть отрицательными (мультимонитор)


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PHOTOS_DIR.mkdir(parents=True, exist_ok=True)


def load_config(path: Path = CONFIG_PATH) -> dict:
    cfg = dict(DEFAULTS)
    try:
        if path.exists():
            with open(path, encoding="utf-8") as f:
                user = json.load(f)
            if isinstance(user, dict):
                # Миграция: раньше YouTube был зашит в код, а в конфиге
                # жили только дополнительные домены.
                extras = user.pop("blocklist_extras", None)
                if extras and "blocklist" not in user:
                    user["blocklist"] = DEFAULT_BLOCKLIST + list(extras)
                cfg.update(user)
    except Exception:
        log.exception("config.json повреждён, использую дефолты: %s", path)
    _coerce(cfg)
    return cfg


def save_config(cfg: dict, path: Path = CONFIG_PATH) -> None:
    _coerce(cfg)
    tmp = path.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def _coerce(cfg: dict) -> None:
    """Приводит значения к нужным типам, чтобы кривой ручной правке не радовался UI."""
    for k in _INT_KEYS:
        try:
            v = int(cfg.get(k, DEFAULTS[k]))
        except (TypeError, ValueError):
            v = DEFAULTS[k]
        cfg[k] = max(1, v)
    for k in _BOOL_KEYS:
        cfg[k] = bool(cfg.get(k, DEFAULTS[k]))
    for k in _LIST_KEYS:
        v = cfg.get(k, DEFAULTS[k])
        if isinstance(v, str):
            v = [x.strip() for x in v.replace(",", "\n").splitlines() if x.strip()]
        cfg[k] = [str(x).strip().lower() for x in v if str(x).strip()] if isinstance(v, (list, tuple)) else []
    for k in _PATH_LIST_KEYS:
        v = cfg.get(k, DEFAULTS[k])
        if isinstance(v, str):
            v = v.splitlines()
        cfg[k] = list(dict.fromkeys(str(x).strip().strip('"') for x in v
                                    if str(x).strip())) if isinstance(v, (list, tuple)) else []
    for k, choices in _CHOICE_KEYS.items():
        if cfg.get(k) not in choices:
            cfg[k] = DEFAULTS[k]
    for k in _POS_KEYS:
        try:
            cfg[k] = None if cfg.get(k) is None else int(cfg[k])
        except (TypeError, ValueError):
            cfg[k] = None
