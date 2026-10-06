# -*- coding: utf-8 -*-
"""Управление маркированной секцией в hosts-файле.

Трогаем ТОЛЬКО строки между своими маркерами, остальной файл остаётся
байт-в-байт нетронутым. Наша секция — чистый ASCII, поэтому работаем с bytes.

CLI для отладки без трея:
    python hosts.py --status  [--hosts ПУТЬ]
    python hosts.py --block   [--hosts ПУТЬ] [--no-doh]
    python hosts.py --unblock [--hosts ПУТЬ]
"""
import argparse
import logging
import subprocess
import sys
import time
from pathlib import Path

log = logging.getLogger("focus.hosts")

HOSTS_PATH = Path(r"C:\Windows\System32\drivers\etc\hosts")

MARKER_BEGIN = b"# focus-shield:BEGIN"
MARKER_END = b"# focus-shield:END"

# Блокируемые домены живут в config.json («blocklist», по умолчанию — YouTube).

# Endpoints secure-DNS (DoH): блокируем их на время сессии, чтобы браузер
# откатывался на системный резолвер, где действует hosts.
# Это best-effort: DoH по голому IP (https://8.8.8.8/dns-query) так не закрыть.
DOH_DOMAINS = [
    "dns.google",
    "dns.google.com",
    "cloudflare-dns.com",
    "mozilla.cloudflare-dns.com",
    "security.cloudflare-dns.com",
    "family.cloudflare-dns.com",
    "one.one.one.one",
    "doh.opendns.com",
    "dns.quad9.net",
    "dns9.quad9.net",
    "doh.cleanbrowsing.org",
    "dns.adguard.com",
    "doh.adguard.com",
    "dns.nextdns.io",
]

CREATE_NO_WINDOW = 0x08000000


def domains_for(cfg: dict) -> list:
    """Итоговый список доменов для блокировки по конфигу. Пустой blocklist —
    пустой результат: блокировать DoH без сайтов смысла нет."""
    doms = list(dict.fromkeys(str(d).lower() for d in cfg.get("blocklist", [])))
    if doms and cfg.get("block_doh", True):
        doms += [d for d in DOH_DOMAINS if d not in doms]
    return doms


def _clean_domain(raw) -> str:
    d = str(raw).strip().lower()
    for pref in ("https://", "http://"):
        if d.startswith(pref):  # removeprefix, но совместимо со старым питоном
            d = d[len(pref):]
    d = d.split("/")[0].split(":")[0].split()[0] if d else d
    return d


def _enc(domain: str) -> bytes:
    try:
        return domain.encode("idna")
    except ValueError:
        return domain.encode("utf-8")


def _build_section(domains) -> bytes:
    lines = b"\r\n".join(b"0.0.0.0 " + _enc(d) for d in domains)
    return MARKER_BEGIN + b"\r\n" + lines + b"\r\n" + MARKER_END + b"\r\n"


def _find_section(data: bytes):
    """Возвращает (start, end) нашей секции в bytes или None."""
    start = data.find(MARKER_BEGIN)
    if start == -1:
        return None
    end = data.find(MARKER_END, start)
    if end == -1:
        # Повреждённая секция без END — вырезаем до конца файла.
        return start, len(data)
    end += len(MARKER_END)
    # Захватываем завершающий перевод строки, чтобы не плодить пустые строки.
    if data[end:end + 2] == b"\r\n":
        end += 2
    elif data[end:end + 1] == b"\n":
        end += 1
    return start, end


def _read(path) -> bytes:
    return Path(path).read_bytes()


def _write(path, data: bytes) -> None:
    path = Path(path)
    # Один раз делаем резервную копию оригинала — страховка от наших же ошибок.
    bak = path.with_name(path.name + ".focus-shield.bak")
    if not bak.exists():
        try:
            bak.write_bytes(data)
        except OSError:
            log.warning("не удалось создать бэкап hosts: %s", bak, exc_info=True)
    # Атомарная подмена требует права удалить hosts, а его часто держит открытым
    # DNS-клиент Windows или Defender (без FILE_SHARE_DELETE) — тогда
    # PermissionError. Запасной путь — перезапись поверх: ей хватает
    # FILE_SHARE_WRITE, который у этих читателей есть.
    tmp = path.with_name(path.name + ".fs-tmp")
    last_err = None
    for attempt in range(4):
        try:
            tmp.write_bytes(data)
            tmp.replace(path)
            return
        except PermissionError as e:
            last_err = e
            try:
                with open(path, "r+b") as f:
                    f.write(data)
                    f.truncate()
                tmp.unlink(missing_ok=True)
                log.info("hosts: записан поверх (атомарная подмена занята)")
                return
            except PermissionError as e2:
                last_err = e2
                time.sleep(0.25 * (attempt + 1))
    tmp.unlink(missing_ok=True)
    raise last_err


def is_blocked(path=HOSTS_PATH) -> bool:
    return _find_section(_read(path)) is not None


def normalize(path=HOSTS_PATH, flush: bool = True) -> bool:
    """Удаляет нашу секцию. Возвращает True, если файл изменился."""
    data = _read(path)
    sec = _find_section(data)
    if sec is None:
        return False
    new = data[:sec[0]] + data[sec[1]:]
    if new and not new.endswith(b"\n"):
        new += b"\r\n"
    _write(path, new)
    if flush:
        flush_dns()
    log.info("hosts: секция удалена (%s)", path)
    return True


def apply_block(domains, path=HOSTS_PATH, flush: bool = True) -> bool:
    """Перезаписывает нашу секцию свежим списком доменов (идемпотентно).
    Возвращает True, если файл изменился."""
    doms = []
    for raw in domains:
        d = _clean_domain(raw)
        if d and d[0] not in "#." and d not in doms:
            doms.append(d)
    want = _build_section(doms)

    data = _read(path)
    sec = _find_section(data)
    if sec is not None and data[sec[0]:sec[1]].rstrip(b"\r\n") == want.rstrip(b"\r\n"):
        if flush:  # секция уже актуальна; flush всё равно не помешает
            flush_dns()
        return False

    before = data[:sec[0]].rstrip(b"\r\n") if sec else data.rstrip(b"\r\n")
    after = data[sec[1]:].lstrip(b"\r\n") if sec else b""
    new = (before + b"\r\n\r\n" if before else b"") + want + (after if after else b"")
    _write(path, new)
    if flush:
        flush_dns()
    log.info("hosts: заблокировано %d доменов", len(doms))
    return True


def re_assert(domains, path=HOSTS_PATH) -> bool:
    """Периодический перезапис секции во время фокуса: лечит ручные правки
    hosts посреди сессии. Идемпотентен и тих (без flush)."""
    return apply_block(domains, path, flush=False)


def flush_dns() -> None:
    try:
        subprocess.run(["ipconfig", "/flushdns"], capture_output=True,
                       creationflags=CREATE_NO_WINDOW, check=False, timeout=15)
    except Exception:
        log.warning("flushdns не удался", exc_info=True)


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    p = argparse.ArgumentParser(description="Управление блокировкой hosts для FocusShield")
    p.add_argument("--status", action="store_true")
    p.add_argument("--block", action="store_true")
    p.add_argument("--unblock", action="store_true")
    p.add_argument("--hosts", default=str(HOSTS_PATH), help="путь к hosts (для тестов)")
    p.add_argument("--no-doh", action="store_true", help="не добавлять DoH-домены")
    a = p.parse_args(argv)
    path = Path(a.hosts)

    if a.status:
        print("BLOCKED" if is_blocked(path) else "clean")
        return 0
    if a.unblock:
        print("unblocked" if normalize(path) else "already clean")
        return 0
    if a.block:
        try:
            from config import load_config
            cfg = load_config()
        except Exception:
            from config import DEFAULTS
            cfg = dict(DEFAULTS)
        cfg["block_doh"] = not a.no_doh
        apply_block(domains_for(cfg), path)
        print("blocked" if is_blocked(path) else "failed")
        return 0
    p.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
