"""Photo-realistic game assets via Pillow — traditional wooden backgammon."""

from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path
from typing import Literal

import pygame
from PIL import Image, ImageDraw, ImageFilter

SUPERSAMPLE = 2
_ASSETS = Path(__file__).with_name("assets")


def pil_to_surface(img: Image.Image) -> pygame.Surface:
    """Convert a PIL Image to a pygame Surface, preserving alpha."""
    img = img.convert("RGBA")
    return pygame.image.fromstring(img.tobytes(), img.size, "RGBA").convert_alpha()


# Board color themes
THEMES = {
    "bone": {
        "dark_tri": ((25, 25, 25), (10, 10, 10), (45, 45, 45), (20, 20, 20)),
        "light_tri": ((240, 235, 220), (200, 192, 175), (250, 248, 238), (225, 218, 200)),
        "surface": (228, 215, 190),
        "label": "Bone",
    },
    "wood": {
        "dark_tri": ((100, 30, 18), (70, 20, 10), (130, 50, 30), (85, 25, 14)),
        "light_tri": ((140, 70, 35), (110, 50, 25), (165, 90, 50), (120, 60, 30)),
        "surface": (220, 200, 170),
        "label": "Wood",
    },
}
_current_theme: str = "bone"


_theme_change_counter: int = 0


def set_theme(name: str) -> None:
    """Switch the active board color theme."""
    global _current_theme, _theme_change_counter
    if name in THEMES:
        _current_theme = name
        _theme_change_counter += 1
        checker_photo.cache_clear()
        shadow_photo.cache_clear()
        die_photo.cache_clear()


def get_theme() -> str:
    """Return the current theme name."""
    return _current_theme


def _load_asset(name: str) -> Image.Image | None:
    """Load an image from assets directory, or None if missing."""
    path = _ASSETS / name
    if path.exists():
        try:
            return Image.open(path).convert("RGB")
        except Exception:
            return None
    return None


# ── Checkers ──────────────────────────────────────────────────────────

@lru_cache(maxsize=32)
def checker_photo(diameter: int, is_white: bool) -> pygame.Surface:
    """Return a cached Surface of a checker."""
    return pil_to_surface(_checker_image(diameter, is_white))


def _checker_image(diameter: int, is_white: bool) -> Image.Image:
    big = diameter * SUPERSAMPLE
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx = cy = big // 2
    r = big // 2 - 3

    if is_white:
        edge = (195, 185, 165)
        face = (248, 242, 230)
        groove_col = (180, 168, 148, 200)
        shine_alpha = 55
    else:
        edge = (55, 30, 18)
        face = (100, 58, 32)
        groove_col = (40, 22, 12, 200)
        shine_alpha = 30

    # Main face — smooth gradient
    for i in range(r, 0, -1):
        t = 1.0 - i / r
        t_s = t * t * (3 - 2 * t)
        c = tuple(int(edge[j] + (face[j] - edge[j]) * t_s) for j in range(3))
        draw.ellipse([cx - i, cy - i, cx + i, cy + i], fill=(*c, 255))

    # Carved grooves
    for frac in (0.74, 0.48):
        gr = int(r * frac)
        gw = max(2, r // 18)
        draw.ellipse([cx - gr, cy - gr, cx + gr, cy + gr],
                     outline=groove_col, width=gw)

    # Center medallion
    mr = int(r * 0.22)
    mc = tuple(int((edge[j] + face[j]) // 2) for j in range(3))
    draw.ellipse([cx - mr, cy - mr, cx + mr, cy + mr],
                 fill=(*mc, 180), outline=groove_col, width=max(1, r // 25))

    # Soft highlight
    hi = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    hd = ImageDraw.Draw(hi)
    glow_r = int(r * 0.5)
    glow_cy = cy - int(r * 0.12)
    for gi in range(glow_r, 0, -1):
        alpha = int(shine_alpha * (gi / glow_r) ** 2)
        hd.ellipse([cx - gi, glow_cy - int(gi * 0.5),
                    cx + gi, glow_cy + int(gi * 0.4)],
                   fill=(255, 255, 255, alpha))
    hi = hi.filter(ImageFilter.GaussianBlur(radius=max(2, big // 16)))
    img = Image.alpha_composite(img, hi)

    # Circular clip — multiply existing alpha with circle mask
    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).ellipse([cx - r, cy - r, cx + r, cy + r], fill=255)
    # Combine: keep existing alpha only inside circle
    alpha = img.split()[3]
    from PIL import ImageChops
    clipped_alpha = ImageChops.multiply(alpha, mask)
    img.putalpha(clipped_alpha)

    return img.resize((diameter, diameter), Image.LANCZOS)


@lru_cache(maxsize=16)
def shadow_photo(diameter: int) -> pygame.Surface:
    """Return a soft circular shadow image."""
    big = diameter * SUPERSAMPLE
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    r = big // 2 - 1
    cx = cy = big // 2
    for i in range(r, 0, -1):
        alpha = int(70 * (i / r))
        draw.ellipse([cx - i, cy - i, cx + i, cy + i], fill=(0, 0, 0, alpha))
    img = img.filter(ImageFilter.GaussianBlur(radius=max(1, big // 12)))
    # Clip to circle
    from PIL import ImageChops
    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, big - 1, big - 1], fill=255)
    clipped = ImageChops.multiply(img.split()[3], mask)
    img.putalpha(clipped)
    return pil_to_surface(img.resize((diameter, diameter), Image.LANCZOS))


# ── Dice (ivory) ─────────────────────────────────────────────────────

@lru_cache(maxsize=12)
def die_photo(size: int, value: int) -> pygame.Surface:
    """Return a cached Surface of a die face."""
    return pil_to_surface(_die_image(size, value))


def _die_image(size: int, value: int) -> Image.Image:
    big = size * SUPERSAMPLE
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    margin = big // 10
    cr = big // 5

    # Shadow
    draw.rounded_rectangle(
        (margin + 3, margin + 3, big - margin + 3, big - margin + 3),
        radius=cr, fill=(30, 20, 10, 140),
    )
    # Ivory body
    draw.rounded_rectangle(
        (margin, margin, big - margin, big - margin),
        radius=cr, fill=(252, 248, 235, 255),
        outline=(210, 195, 170, 255), width=max(1, big // 45),
    )
    # Warm ivory gradient
    for i in range(margin + 2, big - margin - 1):
        t = (i - margin) / (big - 2 * margin)
        r_c = int(252 - t * 10)
        g_c = int(248 - t * 12)
        b_c = int(235 - t * 15)
        draw.line([(margin + 2, i), (big - margin - 2, i)],
                  fill=(r_c, g_c, b_c, 35))

    # Pips (dark brown, not black — traditional)
    pip_map = {
        1: [(0.5, 0.5)],
        2: [(0.28, 0.28), (0.72, 0.72)],
        3: [(0.28, 0.28), (0.5, 0.5), (0.72, 0.72)],
        4: [(0.28, 0.28), (0.72, 0.28), (0.28, 0.72), (0.72, 0.72)],
        5: [(0.28, 0.28), (0.72, 0.28), (0.5, 0.5), (0.28, 0.72), (0.72, 0.72)],
        6: [(0.28, 0.28), (0.72, 0.28), (0.28, 0.5), (0.72, 0.5), (0.28, 0.72), (0.72, 0.72)],
    }
    pr = max(3, big // 9)
    field = big - 2 * margin
    for px, py in pip_map.get(value, []):
        pcx = int(margin + px * field)
        pcy = int(margin + py * field)
        draw.ellipse([pcx - pr - 1, pcy - pr - 1, pcx + pr + 1, pcy + pr + 1],
                     fill=(220, 210, 190, 160))
        draw.ellipse([pcx - pr, pcy - pr, pcx + pr, pcy + pr],
                     fill=(40, 25, 15, 255))
        hpr = max(1, pr // 3)
        draw.ellipse([pcx - hpr - 1, pcy - hpr - 2, pcx + hpr - 1, pcy + hpr - 2],
                     fill=(90, 70, 50, 120))

    img = img.filter(ImageFilter.SMOOTH)
    return img.resize((size, size), Image.LANCZOS)


# ── Board textures ────────────────────────────────────────────────────

def light_wood(width: int, height: int, base_r: int = 210, base_g: int = 180, base_b: int = 140) -> Image.Image:
    """Light pine/birch wood for playing surface and frame."""
    tw, th = min(width, 160), min(height, 160)
    img = Image.new("RGB", (tw, th))
    pixels = img.load()
    for y in range(th):
        ry = y * height / th
        for x in range(tw):
            rx = x * width / tw
            grain = (
                math.sin(ry * 0.06 + math.sin(rx * 0.015) * 4) * 0.4 +
                math.sin(ry * 0.18 + rx * 0.008) * 0.25 +
                math.sin(ry * 0.4 + math.sin(rx * 0.04 + ry * 0.02) * 2.5) * 0.15 +
                math.sin(rx * 0.12 + ry * 0.06) * 0.1
            )
            pixels[x, y] = (
                max(0, min(255, base_r + int(grain * 30))),
                max(0, min(255, base_g + int(grain * 25))),
                max(0, min(255, base_b + int(grain * 18))),
            )
    img = img.filter(ImageFilter.SMOOTH_MORE)
    if (tw, th) != (width, height):
        img = img.resize((width, height), Image.LANCZOS)
    return img


def dark_wood(width: int, height: int) -> Image.Image:
    """Darker wood for frame border."""
    return light_wood(width, height, base_r=120, base_g=80, base_b=45)


def ivory_surface(width: int, height: int) -> Image.Image:
    """Smooth polished ivory/bone surface."""
    tw, th = min(width, 160), min(height, 160)
    img = Image.new("RGB", (tw, th))
    pixels = img.load()
    for y in range(th):
        ry = y * height / th
        for x in range(tw):
            rx = x * width / tw
            grain = (
                math.sin(ry * 0.03 + rx * 0.01) * 0.15 +
                math.sin(rx * 0.05 + ry * 0.02) * 0.1 +
                math.sin(ry * 0.08 + math.sin(rx * 0.03) * 1.5) * 0.08
            )
            pixels[x, y] = (
                max(0, min(255, 238 + int(grain * 12))),
                max(0, min(255, 232 + int(grain * 10))),
                max(0, min(255, 218 + int(grain * 8))),
            )
    img = img.filter(ImageFilter.SMOOTH_MORE)
    if (tw, th) != (width, height):
        img = img.resize((width, height), Image.LANCZOS)
    return img


def board_surface(width: int, height: int) -> Image.Image:
    """Theme-dependent playing surface."""
    if _current_theme == "wood":
        photo = _load_asset("wood_bg.jpg")
        if photo is not None:
            return photo.resize((width, height), Image.LANCZOS)
        return light_wood(width, height, base_r=195, base_g=155, base_b=110)
    return ivory_surface(width, height)


def bark_texture(width: int, height: int) -> Image.Image:
    """Dark tree bark — loads real photo or generates procedurally."""
    photo = _load_asset("wood_bg.jpg")
    if photo is not None:
        return photo.resize((width, height), Image.LANCZOS)
    tw, th = min(width, 160), min(height, 160)
    img = Image.new("RGB", (tw, th))
    pixels = img.load()
    for y in range(th):
        ry = y * height / th
        for x in range(tw):
            rx = x * width / tw
            v1 = math.sin(rx * 0.3 + math.sin(ry * 0.05) * 5) * 0.4
            v2 = math.sin(rx * 0.7 + ry * 0.02) * 0.25
            v3 = math.sin(rx * 1.5 + math.sin(ry * 0.08 + rx * 0.03) * 3) * 0.2
            v4 = math.sin(ry * 0.15 + rx * 0.1) * 0.15
            grain = v1 + v2 + v3 + v4
            pixels[x, y] = (
                max(0, min(255, 60 + int(grain * 35))),
                max(0, min(255, 32 + int(grain * 22))),
                max(0, min(255, 18 + int(grain * 14))),
            )
    img = img.filter(ImageFilter.SMOOTH)
    if (tw, th) != (width, height):
        img = img.resize((width, height), Image.LANCZOS)
    return img


def menu_background(width: int, height: int) -> Image.Image:
    """Menu background — loads real photo or falls back to bark."""
    photo = _load_asset("menu_bg.jpg")
    if photo is not None:
        return photo.resize((width, height), Image.LANCZOS)
    return bark_texture(width, height)


# ── Triangles (traditional ornate style) ─────────────────────────────

def triangle_image(
    width: int, height: int,
    color_type: Literal["dark", "light"],
    pointing: Literal["up", "down"],
) -> Image.Image:
    """Traditional tapered backgammon triangle — wide at base, narrow pointed tip."""
    big_w, big_h = width * SUPERSAMPLE, height * SUPERSAMPLE
    img = Image.new("RGBA", (big_w, big_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    theme = THEMES.get(_current_theme, THEMES["bone"])
    if color_type == "dark":
        fill_color, edge_color, inner_color, tip_color = theme["dark_tri"]
    else:
        fill_color, edge_color, inner_color, tip_color = theme["light_tri"]

    cx = big_w // 2
    base_half = big_w // 2 - 2
    ow = max(1, big_w // 22)

    # Main body — narrow tapered shape
    neck = max(2, big_w // 10)
    if pointing == "down":
        body = [
            (cx - base_half, 0), (cx + base_half, 0),
            (cx + neck, big_h * 3 // 4),
            (cx, big_h - big_h // 8),
            (cx - neck, big_h * 3 // 4),
        ]
    else:
        body = [
            (cx - base_half, big_h), (cx + base_half, big_h),
            (cx + neck, big_h // 4),
            (cx, big_h // 8),
            (cx - neck, big_h // 4),
        ]
    draw.polygon(body, fill=fill_color)

    # Inner stripe
    inset = big_w // 6
    neck_in = max(1, neck - 2)
    if pointing == "down":
        inner = [
            (cx - base_half + inset, big_h // 8),
            (cx + base_half - inset, big_h // 8),
            (cx + neck_in, big_h * 3 // 4 - big_h // 10),
            (cx, big_h - big_h // 5),
            (cx - neck_in, big_h * 3 // 4 - big_h // 10),
        ]
    else:
        inner = [
            (cx - base_half + inset, big_h - big_h // 8),
            (cx + base_half - inset, big_h - big_h // 8),
            (cx + neck_in, big_h // 4 + big_h // 10),
            (cx, big_h // 5),
            (cx - neck_in, big_h // 4 + big_h // 10),
        ]
    draw.polygon(inner, fill=inner_color)

    # Outline
    draw.polygon(body, fill=None, outline=edge_color, width=ow)

    # Ornamental tip — a single subtle curl. (The old triple-scroll + red
    # dot repeated 24 times read as visual clutter, especially on bone.)
    tip_y = big_h - big_h // 10 if pointing == "down" else big_h // 10
    curl_r = max(3, big_w // 7)
    draw.ellipse([cx - curl_r, tip_y - curl_r, cx + curl_r, tip_y + curl_r],
                 fill=tip_color, outline=edge_color, width=max(1, ow - 1))
    cr2 = max(1, curl_r // 2)
    draw.ellipse([cx - cr2, tip_y - cr2, cx + cr2, tip_y + cr2],
                 fill=inner_color)

    return img.resize((width, height), Image.LANCZOS)


def center_ornament(width: int, height: int) -> Image.Image:
    """Theme-dependent ornament: eastern vines for wood, spiral rosette for bone."""
    if _current_theme == "wood":
        return _ornament_eastern(width, height)
    return _ornament_rosette(width, height)


def _ornament_eastern(width: int, height: int) -> Image.Image:
    """Eastern vine/arabesque ornament with colored accents."""
    big_w, big_h = width * SUPERSAMPLE, height * SUPERSAMPLE
    img = Image.new("RGBA", (big_w, big_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = big_w // 2, big_h // 2
    R = min(cx, cy) - 4

    dark = (40, 30, 20, 240)
    brown = (85, 50, 28, 210)
    green = (110, 72, 34, 190)  # warm ochre; true green clashed with the wood palette
    red = (150, 35, 25, 210)
    gold = (160, 120, 50, 180)
    lw = max(2, R // 7)

    # Outer border
    draw.ellipse([cx - R, cy - R, cx + R, cy + R],
                 fill=None, outline=dark, width=lw)

    # 4 main vine scrolls
    for rot in range(4):
        a = rot * 90
        for frac, col, span in [(0.8, dark, 80), (0.6, brown, 90), (0.4, green, 100)]:
            vr = int(R * frac)
            draw.arc([cx - vr, cy - vr, cx + vr, cy + vr],
                     start=a, end=a + span,
                     fill=col, width=max(2, lw))

    # 4 leaf pairs at diagonals
    for i in range(4):
        angle = math.radians(i * 90 + 45)
        dist = R * 0.55
        lx = cx + int(dist * math.cos(angle))
        ly = cy + int(dist * math.sin(angle))
        lr = max(3, R // 4)
        # Two crossing ellipses for leaf shape
        for da in (-20, 20):
            a2 = angle + math.radians(da)
            ex = lx + int(lr * 0.3 * math.cos(a2))
            ey = ly + int(lr * 0.3 * math.sin(a2))
            draw.ellipse([ex - lr // 2, ey - lr, ex + lr // 2, ey + lr],
                         fill=green, outline=dark, width=max(1, lw // 3))

    # Diamond frame
    d = int(R * 0.38)
    draw.polygon([(cx, cy - d), (cx + d, cy), (cx, cy + d), (cx - d, cy)],
                 fill=None, outline=gold, width=max(1, lw - 1))

    # Center medallion
    mr = max(4, R // 4)
    draw.ellipse([cx - mr, cy - mr, cx + mr, cy + mr],
                 fill=brown, outline=dark, width=max(1, lw // 2))
    mr2 = max(2, mr // 2)
    draw.ellipse([cx - mr2, cy - mr2, cx + mr2, cy + mr2], fill=red)

    # Cardinal accent dots
    dot_r = max(2, R // 12)
    for i in range(8):
        angle = math.radians(i * 45)
        dx = int(R * 0.85 * math.cos(angle))
        dy = int(R * 0.85 * math.sin(angle))
        col = red if i % 2 == 0 else gold
        draw.ellipse([cx + dx - dot_r, cy + dy - dot_r,
                      cx + dx + dot_r, cy + dy + dot_r], fill=col)

    img = img.filter(ImageFilter.SMOOTH)
    return img.resize((width, height), Image.LANCZOS)


def _ornament_rosette(width: int, height: int) -> Image.Image:
    """Spiral petal rosette — elegant thin curves."""
    big_w, big_h = width * SUPERSAMPLE, height * SUPERSAMPLE
    img = Image.new("RGBA", (big_w, big_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = big_w // 2, big_h // 2
    R = min(cx, cy) - 4

    ink = (35, 30, 25, 200)
    lw = max(2, R // 9)

    # Outer circle
    draw.ellipse([cx - R, cy - R, cx + R, cy + R],
                 fill=None, outline=ink, width=lw)

    # Spiral petals — 8 overlapping ellipses rotated around center
    petals = 8
    petal_r = int(R * 0.75)
    petal_w = int(R * 0.45)
    for i in range(petals):
        angle = math.radians(i * 360 / petals)
        # Petal center offset from main center
        px = cx + int(R * 0.28 * math.cos(angle))
        py = cy + int(R * 0.28 * math.sin(angle))
        # Draw ellipse as petal — rotated by using offset bbox
        # Approximate rotation with arc pairs
        a_start = math.degrees(angle) - 60
        a_end = math.degrees(angle) + 60
        draw.arc([px - petal_r, py - petal_r, px + petal_r, py + petal_r],
                 start=a_start, end=a_end,
                 fill=ink, width=max(1, lw - 1))
        # Opposite curve for petal outline
        draw.arc([px - petal_w, py - petal_w, px + petal_w, py + petal_w],
                 start=a_start - 10, end=a_end + 10,
                 fill=ink, width=max(1, lw - 1))

    # Inner circle
    ir = int(R * 0.2)
    draw.ellipse([cx - ir, cy - ir, cx + ir, cy + ir],
                 fill=None, outline=ink, width=lw)

    # Center dot
    cr = max(3, R // 10)
    draw.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], fill=ink)

    img = img.filter(ImageFilter.SMOOTH)
    return img.resize((width, height), Image.LANCZOS)
