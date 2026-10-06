# -*- coding: utf-8 -*-
"""Периодические снимки во время фокуса: веб-камера и экран.

Всё строго локально: файлы в %LOCALAPPDATA%\\focus-shield\\photos\\ГГГГ-ММ-ДД,
авто-очистка старше webcam_retention_days, никакой сети. Снимок камеры —
«ЧЧ-ММ-СС.jpg», скриншот экрана — «ЧЧ-ММ-СС-screen.jpg».

Захват — в короткоживущем worker-потоке (камера открывается 1–3 с);
результат возвращается колбэком в Tk-поток через очередь оркестратора.
Камеру закрываем сразу после снимка (индикатор камеры вспыхивает на
секунду, а не горит постоянно).
"""
import logging
import threading
import time
from datetime import datetime

import config

log = logging.getLogger("focus.webcam")

try:
    import cv2
    CV2_OK = True
except ImportError:
    cv2 = None
    CV2_OK = False
    log.warning("opencv-python не установлен — снимки камеры отключены")


SCREEN_SUFFIX = "-screen"
SCREEN_MAX_W = 1920  # скриншоты уменьшаем: несколько мониторов — это десятки МБ


def _save_jpeg(data: bytes, suffix: str = "") -> str:
    now = datetime.now()
    day_dir = config.PHOTOS_DIR / now.strftime("%Y-%m-%d")
    day_dir.mkdir(parents=True, exist_ok=True)
    path = day_dir / (now.strftime("%H-%M-%S") + suffix + ".jpg")
    path.write_bytes(data)
    log.info("снимок сохранён: %s", path)
    return str(path)


class Snapper:
    """Периодический снимок во время фокуса. Наследники реализуют _capture()."""

    what = "снимок"

    def __init__(self, emit_photo):
        """emit_photo(path|None, session_db_id) — вызывается в Tk-потоке
        через очередь событий оркестратора."""
        self.emit_photo = emit_photo
        self._next_at = 0.0
        self._busy = False
        self._session_id = None
        self.disabled = False  # источник недоступен → тихо выключаем до перезапуска

    def start(self, session_db_id, every_sec: int) -> None:
        self._session_id = session_db_id
        self._next_at = time.time() + min(every_sec, 30)  # первый снимок скоро
        self._busy = False

    def stop(self) -> None:
        self._next_at = 0.0
        self._session_id = None

    def maybe_tick(self, every_sec: int) -> None:
        if self.disabled or self._busy or self._next_at <= 0:
            return
        now = time.time()
        if now < self._next_at:
            return
        self._busy = True
        t = threading.Thread(target=self._worker, args=(every_sec,), daemon=True)
        t.start()

    def _worker(self, every_sec: int) -> None:
        path = None
        try:
            path = self._capture()
        except Exception:
            log.exception("%s не удался", self.what)
        self._next_at = time.time() + every_sec
        self._busy = False
        if path is not None:
            self.emit_photo(path, self._session_id)

    def _capture(self):
        raise NotImplementedError


class Webcam(Snapper):
    what = "снимок камеры"

    def __init__(self, emit_photo):
        super().__init__(emit_photo)
        self.disabled = not CV2_OK

    def _capture(self):
        # DirectShow открывается заметно быстрее Media Foundation на Windows.
        cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        try:
            if not cap.isOpened():
                self.disabled = True
                log.warning("камера не открылась — отключаю снимки до перезапуска")
                return None
            frame = None
            for _ in range(3):  # первые кадры у многих камер тёмные
                ok, f = cap.read()
                if ok:
                    frame = f
                time.sleep(0.06)
            if frame is None:
                return None
            ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 82])
            if not ok:
                return None
            return _save_jpeg(buf.tobytes())
        finally:
            cap.release()


class ScreenShooter(Snapper):
    """Скриншот всех мониторов (уменьшенный до SCREEN_MAX_W по ширине)."""

    what = "скриншот экрана"

    def _capture(self):
        import io
        from PIL import Image, ImageGrab
        img = ImageGrab.grab(all_screens=True)
        if img.width > SCREEN_MAX_W:
            img = img.resize((SCREEN_MAX_W, round(img.height * SCREEN_MAX_W / img.width)),
                             Image.LANCZOS)
        buf = io.BytesIO()
        img.convert("RGB").save(buf, "JPEG", quality=72, optimize=True)
        return _save_jpeg(buf.getvalue(), SCREEN_SUFFIX)


def list_photo_days() -> list:
    """[(‘ГГГГ-ММ-ДД’, число снимков)] — новые дни первыми."""
    if not config.PHOTOS_DIR.exists():
        return []
    days = []
    for d in config.PHOTOS_DIR.iterdir():
        if d.is_dir():
            n = sum(1 for _ in d.glob("*.jpg"))
            if n:
                days.append((d.name, n))
    return sorted(days, reverse=True)


def photos_for_day(day: str) -> list:
    """[(путь, ‘ЧЧ:ММ’, ‘camera’|‘screen’)] по времени съёмки."""
    d = config.PHOTOS_DIR / day
    if not d.is_dir():
        return []
    return [(str(f), f.stem[:5].replace("-", ":"),
             "screen" if f.stem.endswith(SCREEN_SUFFIX) else "camera")
            for f in sorted(d.glob("*.jpg"))]


def open_folder(day: str = None) -> None:
    """Открыть в Проводнике папку дня (или корень со всеми днями)."""
    import os
    target = config.PHOTOS_DIR / day if day else config.PHOTOS_DIR
    if not target.is_dir():
        target = config.PHOTOS_DIR
    target.mkdir(parents=True, exist_ok=True)
    os.startfile(str(target))


def purge_old_photos(retention_days: int) -> list:
    """Удаляет папки дней старше retention_days. Возвращает список удалённых путей."""
    if retention_days <= 0 or not config.PHOTOS_DIR.exists():
        return []
    cutoff = time.time() - retention_days * 86400
    removed = []
    for day_dir in config.PHOTOS_DIR.iterdir():
        if not day_dir.is_dir():
            continue
        try:
            if day_dir.stat().st_mtime < cutoff:
                for f in day_dir.glob("*.jpg"):
                    f.unlink(missing_ok=True)
                    removed.append(str(f))
                day_dir.rmdir()
        except OSError:
            log.warning("не удалось почистить %s", day_dir, exc_info=True)
    if removed:
        log.info("удалено старых снимков: %d", len(removed))
    return removed
