# -*- coding: utf-8 -*-
"""Маскот плавающего таймера: круглый росток.

Канвас Tk не сглаживает фигуры, поэтому кадр рисуется в PIL с
суперсэмплингом (SS×) и уменьшается Lanczos'ом — получаются мягкие
края, градиент, блики и размытая тень. Готовые кадры кэшируются:
параметры анимации квантуются, и повторяющиеся кадры не рисуются заново.

Настроение: focus — сосредоточен и косится на таймер, hurry — последняя
минута, break — довольно жмурится, sleep — дремлет в простое, joy — его ткнули.

Рост (growth 0…1) — доля серии помидоров до длинного перерыва: росток на
макушке тянется вверх, обрастает листьями, к концу серии даёт бутон, а на
длинном перерыве (growth = 1) распускает цветок.
"""
import math
from collections import OrderedDict

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

SS = 3                # суперсэмплинг
W, H = 48, 76         # логический размер кадра (до DPI)
INK = (29, 27, 38)
WHITE = (255, 255, 255)
LEAF = (76, 211, 138)
LEAF_DARK = (38, 150, 96)
BLUSH = (255, 120, 150)
SPARK = (255, 209, 102)
SWEAT = (140, 210, 255)
PETAL = (255, 158, 196)
PETAL_DARK = (232, 104, 152)
POLLEN = (255, 214, 92)

_cache = OrderedDict()
_CACHE_MAX = 600
_font_cache = {}


def frame(k: float, mood: str, t: float, color: str, bg: str, dark: bool,
          growth: float = 0.0, look=(0.8, 0.0)) -> Image.Image:
    """Кадр маскота размером (W·k, H·k), RGB на фоне bg; t — время в секундах;
    look — куда смотрят глаза (-1…1 по x и y), по умолчанию — вправо, на таймер."""
    if mood == "sleep":
        breath, bob, sway = math.sin(t * 1.4) * 1.6, 0.0, 0.0
    elif mood == "break":
        breath, bob, sway = math.sin(t * 2.2), 0.0, math.sin(t * 1.6) * 1.6
    elif mood == "hurry":
        breath, bob, sway = math.sin(t * 5), -abs(math.sin(t * 6)) * 3, 0.0
    elif mood == "joy":
        breath, bob, sway = math.sin(t * 9), -abs(math.sin(t * 9)) * 5, 0.0
    else:
        breath, bob, sway = math.sin(t * 2.5), 0.0, 0.0

    def q(v, step):
        return round(round(v / step) * step, 3)

    p = dict(breath=q(breath, 0.2), bob=q(bob, 0.25), sway=q(sway, 0.25),
             wave=q(math.sin(t * 2) * 6, 1.5),
             blink=mood in ("focus", "hurry") and (t % 4.0) < 0.14,
             zz=q((t * 0.45) % 1.0, 0.04) if mood == "sleep" else 0,
             spark=q((t * 3) % 1.0, 0.1) if mood == "joy" else 0,
             growth=q(max(0.0, min(1.0, growth)), 0.02),
             look=(q(look[0], 0.25), q(look[1], 0.25)))
    key = (round(k, 3), mood, color, bg, dark, tuple(sorted(p.items())))
    img = _cache.get(key)
    if img is None:
        img = _render(k, mood, _rgb(color), _rgb(bg), dark, **p)
        _cache[key] = img
        if len(_cache) > _CACHE_MAX:
            _cache.popitem(last=False)
    else:
        _cache.move_to_end(key)
    return img


# ---------- отрисовка ----------

def _render(k, mood, color, bg, dark, breath, bob, sway, wave, blink, zz, spark, growth,
            look):
    s = k * SS
    size = (round(W * s), round(H * s))
    if not dark:  # на насыщенном цвете светлой палитры тёмные глаза теряются
        color = _mix(color, WHITE, 0.3)
    base = Image.new("RGBA", size, bg + (255,))

    def S(*v):
        return [x * s for x in v]

    R = 17
    rx, ry = R * (1 + 0.03 * breath), R * (1 - 0.03 * breath)
    ground = 62
    cx, cy = 24 + sway, ground - ry + bob

    # тень на «полу»: меньше и бледнее, когда подпрыгнул
    lift = min(1.0, -bob / 6)
    sw = rx * (0.8 - 0.25 * lift)
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).ellipse(S(24 - sw, ground - 1.6, 24 + sw, ground + 2.2), fill=255)
    _paint(base, _blur(m, 1.4 * s), (0, 0, 0), (0.45 if dark else 0.16) * (1 - 0.4 * lift))

    _sprout(base, s, cx, cy - ry + 1.5, wave, growth)

    # тело: «яйцо», чуть шире снизу
    pts = []
    for i in range(64):
        a = 2 * math.pi * i / 64
        pts.append(((cx + rx * math.cos(a) * (1 + 0.05 * math.sin(a))) * s,
                    (cy + ry * math.sin(a)) * s))
    body = Image.new("L", size, 0)
    ImageDraw.Draw(body).polygon(pts, fill=255)
    top, bottom = _mix(color, WHITE, 0.28), _mix(color, (0, 0, 0), 0.12)
    y0, y1 = int((cy - ry) * s), int((cy + ry) * s)
    g = Image.new("L", size, 0)
    g.paste(255, (0, y1, size[0], size[1]))
    g.paste(Image.linear_gradient("L").resize((size[0], max(1, y1 - y0))), (0, y0))
    fill = Image.composite(Image.new("RGBA", size, bottom + (255,)),
                           Image.new("RGBA", size, top + (255,)), g)
    base.paste(fill, (0, 0), body)

    # объём: тень по нижне-правому краю, свет по верхне-левому, блик
    shade = ImageChops.subtract(body, ImageChops.offset(body, int(-3 * s), int(-4 * s)))
    _paint(base, ImageChops.multiply(_blur(shade, 2 * s), body),
           _mix(color, (0, 0, 0), 0.45), 0.35)
    rim = ImageChops.subtract(body, ImageChops.offset(body, int(2 * s), int(2.5 * s)))
    _paint(base, ImageChops.multiply(_blur(rim, 1.2 * s), body), WHITE, 0.35)
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).ellipse(S(cx - 10.5, cy - ry + 3, cx - 3.5, cy - ry + 7.5), fill=255)
    _paint(base, ImageChops.multiply(_blur(m, 0.9 * s), body), WHITE, 0.6)

    # контур
    ImageDraw.Draw(base).line(pts + pts[:1], fill=_mix(color, (0, 0, 0), 0.4) + (255,),
                              width=max(1, round(0.8 * s)), joint="curve")

    # румянец
    m = Image.new("L", size, 0)
    md = ImageDraw.Draw(m)
    for sd in (-1, 1):
        bx = cx + sd * 10
        md.ellipse(S(bx - 2.6, cy + 2.4, bx + 2.6, cy + 4.8), fill=255)
    _paint(base, _blur(m, 0.8 * s), BLUSH, 0.55)

    _face(base, s, mood, cx, cy, blink, look)

    if mood == "hurry":
        _drop(base, s, cx + 13, cy - 9)
    elif mood == "sleep":
        _zzz(base, s, cx, cy, zz, dark)
    elif mood == "joy":
        for i, (sx, sy) in enumerate(((cx - 15, cy - 12), (cx + 15, cy - 14), (cx + 17, cy + 2))):
            ph = (spark + i / 3) % 1.0
            _star(base, s, sx, sy, 1.2 + 2.2 * math.sin(math.pi * ph))

    return base.convert("RGB").resize((round(W * k), round(H * k)), Image.LANCZOS)


def _face(base, s, mood, cx, cy, blink, look):
    d = ImageDraw.Draw(base)
    ink = INK + (255,)
    lw = max(1, round(1.15 * s))
    ey, my = cy - 0.5, cy + 5.5

    def S(*v):
        return [x * s for x in v]

    for sd in (-1, 1):
        ex = cx + sd * 6
        if mood in ("break", "joy"):              # ^ ^
            d.arc(S(ex - 2.6, ey - 1.6, ex + 2.6, ey + 3.4), 200, 340, fill=ink, width=lw)
        elif mood == "sleep" or blink:            # ‿ ‿
            d.arc(S(ex - 2.6, ey - 3, ex + 2.6, ey + 1.6), 20, 160, fill=ink, width=lw)
        else:
            ew, eh = (2.2, 3.0) if mood == "hurry" else (1.9, 2.6)
            x, y = ex + look[0] * 1.6, ey + look[1] * 1.1   # смотрит на курсор
            d.ellipse(S(x - ew, y - eh, x + ew, y + eh), fill=ink)
            d.ellipse(S(x + 0.1, y - eh + 0.5, x + 1.7, y - eh + 2.1), fill=WHITE + (255,))
            d.ellipse(S(x - 1.3, y + 0.8, x - 0.4, y + 1.7), fill=WHITE + (220,))
            if mood == "focus":                   # сведённые брови — сосредоточен
                d.line(S(ex + sd * 2.6, ey - 5.2, ex - sd * 1.8, ey - 4.2),
                       fill=ink, width=max(1, round(0.95 * s)))

    if mood in ("break", "joy"):                  # открытая улыбка с языком
        w = 3.4 if mood == "joy" else 2.8
        d.chord(S(cx - w, my - w, cx + w, my + w), 0, 180, fill=ink)
        d.chord(S(cx - w * 0.6, my + w * 0.15, cx + w * 0.6, my + w * 0.92), 180, 360,
                fill=(255, 110, 130, 255))
    elif mood == "hurry":
        d.ellipse(S(cx - 1.3, my - 0.6, cx + 1.3, my + 2.4), fill=ink)
    elif mood == "sleep":
        d.ellipse(S(cx - 0.9, my, cx + 0.9, my + 1.6), fill=ink)
    else:
        d.arc(S(cx - 2, my - 2.4, cx + 2, my + 0.8), 30, 150, fill=ink, width=lw)


def _sprout(base, s, x, y, wave, g):
    """Росток на макушке; g — рост 0…1, wave — покачивание в градусах.

    0 — две семядоли; дальше стебель тянется вверх и на 0.3 / 0.6 обрастает
    ярусами листьев; с 0.8 на верхушке набухает бутон, на 1.0 — цветок.
    """
    d = ImageDraw.Draw(base)
    L = 3 + 13 * g                                   # высота стебля
    lean = math.sin(math.radians(wave)) * L * 0.35   # стебель гнётся, а не крутится

    def at(t):
        """Точка стебля на доле t (0 — макушка, 1 — верхушка)."""
        return x + math.sin(t * math.pi) * 0.8 + lean * t * t, y - L * t

    n = 12
    stem = [at(i / n) for i in range(n + 1)]
    d.line([(px * s, py * s) for px, py in stem], fill=LEAF_DARK + (255,),
           width=max(1, round((1.2 + 0.6 * g) * s)), joint="curve")

    # ярусы листьев: (доля стебля, порог роста, сторона)
    for t, th, side in ((0.35, 0.3, 1), (0.6, 0.6, -1)):
        a = _smooth((g - th) / 0.2)
        if a > 0:
            ang = (25 if side > 0 else 155) + wave * 0.5
            _leaf(d, s, at(t), ang, 7 * a, 3 * a)
    tip = at(1)
    top = 1 - 0.3 * _smooth((g - 0.8) / 0.2)         # с бутоном верхние листья раскрываются шире
    _leaf(d, s, tip, 28 * top + wave, 6 + 4 * g, 2.8 + 1.4 * g)
    _leaf(d, s, tip, 180 - 20 * top + wave * 0.6, 4.5 + 2.5 * g, 2.2 + 1 * g)

    if g >= 0.999:
        _flower(d, s, tip[0], tip[1] - 2.2, 3.2)
    elif g > 0.8:
        b = _smooth((g - 0.8) / 0.2)
        bx, by = tip[0], tip[1] - 1.2 - b
        r = 0.8 + 1.0 * b
        d.ellipse([(bx - r) * s, (by - r * 1.3) * s, (bx + r) * s, (by + r) * s],
                  fill=PETAL_DARK + (255,))
        d.polygon([((bx - r) * s, by * s), (bx * s, (by + r * 1.4) * s),
                   ((bx + r) * s, by * s)], fill=LEAF_DARK + (255,))  # чашелистик


def _flower(d, s, x, y, r):
    for i in range(5):
        a = math.radians(i * 72 - 90)
        px, py = x + math.cos(a) * r * 0.62, y + math.sin(a) * r * 0.62
        pr = r * 0.5
        d.ellipse([(px - pr) * s, (py - pr) * s, (px + pr) * s, (py + pr) * s],
                  fill=PETAL + (255,), outline=PETAL_DARK + (255,), width=max(1, round(0.3 * s)))
    c = r * 0.36
    d.ellipse([(x - c) * s, (y - c) * s, (x + c) * s, (y + c) * s], fill=POLLEN + (255,))


def _leaf(d, s, base_pt, angle, length, width):
    if length < 0.3:
        return
    a = math.radians(angle)
    ca, sa = math.cos(a), math.sin(a)

    def P(u, v):
        return ((base_pt[0] + u * ca - v * sa) * s, (base_pt[1] - (u * sa + v * ca)) * s)

    n = 16
    side1 = [P(length * i / n, width / 2 * math.sin(math.pi * i / n)) for i in range(n + 1)]
    side2 = [P(length * i / n, -width / 2 * math.sin(math.pi * i / n)) for i in range(n, -1, -1)]
    d.polygon(side1 + side2, fill=LEAF + (255,))
    d.polygon(side2 + [P(0, 0)], fill=_mix(LEAF, LEAF_DARK, 0.45) + (255,))  # нижняя половинка темнее
    d.line([P(0.5, 0), P(length * 0.8, 0)], fill=_mix(LEAF, WHITE, 0.45) + (255,),
           width=max(1, round(0.5 * s)))


def _drop(base, s, x, y):
    """Капелька пота — «не успеваю!»."""
    d = ImageDraw.Draw(base)
    r = 1.7
    d.ellipse([(x - r) * s, (y - r) * s, (x + r) * s, (y + r) * s], fill=SWEAT + (255,))
    d.polygon([((x - r * 0.93) * s, (y - 0.5) * s), (x * s, (y - 4) * s),
               ((x + r * 0.93) * s, (y - 0.5) * s)], fill=SWEAT + (255,))
    d.ellipse([(x - 0.9) * s, (y - 1) * s, (x - 0.1) * s, (y + 0.1) * s], fill=WHITE + (230,))


def _star(base, s, x, y, r):
    pts = []
    for i in range(8):
        a = math.pi / 4 * i - math.pi / 2
        rr = r if i % 2 == 0 else r * 0.35
        pts.append(((x + rr * math.cos(a)) * s, (y + rr * math.sin(a)) * s))
    ImageDraw.Draw(base).polygon(pts, fill=SPARK + (255,))


def _zzz(base, s, cx, cy, ph0, dark):
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    col = (170, 170, 185) if dark else (120, 120, 135)
    for i in range(2):
        ph = (ph0 + i * 0.5) % 1.0
        alpha = int(255 * math.sin(math.pi * ph))
        d.text(((cx + 11 + ph * 6) * s, (cy - 9 - ph * 14) * s), "z",
               font=_font(round((5 + ph * 3.5) * s)), fill=col + (alpha,), anchor="mm")
    base.alpha_composite(layer)


# ---------- утилиты ----------

def _paint(base, mask, rgb, alpha):
    """Залить base цветом rgb через маску mask с непрозрачностью alpha."""
    if alpha < 1:
        mask = mask.point(lambda v: int(v * alpha))
    solid = Image.new("RGBA", base.size, tuple(rgb) + (0,))
    solid.putalpha(mask)
    base.alpha_composite(solid)


def _blur(mask, radius):
    return mask.filter(ImageFilter.GaussianBlur(radius))


def _font(size):
    f = _font_cache.get(size)
    if f is None:
        try:
            f = ImageFont.truetype("segoeuib.ttf", size)
        except OSError:
            f = ImageFont.load_default()
        _font_cache[size] = f
    return f


def _smooth(v):
    v = max(0.0, min(1.0, v))
    return v * v * (3 - 2 * v)


def _rgb(c):
    return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))


def _mix(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))
