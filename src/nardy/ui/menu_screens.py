"""Pygame menu screens: title, play mode, AI, network, local, rules."""

from __future__ import annotations

import math
import random
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pygame
import pygame.gfxdraw
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

from nardy.i18n import Localizer, gettext_noop as _
from nardy.ui.runtime import (
    Button, ScrollableText, TextInput, get_font,
    BG_DARK, TEXT_LIGHT, TEXT_MUTED, TEXT_GOLD,
)
from nardy.ui.textures import pil_to_surface, set_theme, get_theme, THEMES

_ASSETS_DIR = Path(__file__).with_name("assets")


def _discover_backgrounds() -> list[str]:
    if not _ASSETS_DIR.exists():
        return []
    return sorted(p.name for p in _ASSETS_DIR.glob("bg_mountain*.jpg"))


_BG_IMAGES = _discover_backgrounds()
_bg_cache: dict[tuple[str, int, int], pygame.Surface] = {}


def _random_bg(w: int, h: int) -> pygame.Surface | None:
    """Load and darken a random mountain photo, sized to (w, h)."""
    if not _BG_IMAGES:
        return None
    name = random.choice(_BG_IMAGES)
    key = (name, w, h)
    if key in _bg_cache:
        return _bg_cache[key]
    try:
        path = _ASSETS_DIR / name
        img = pygame.image.load(str(path)).convert()
        img = pygame.transform.smoothscale(img, (w, h))
        dark = pygame.Surface((w, h), pygame.SRCALPHA)
        dark.fill((0, 0, 0, 160))
        img.blit(dark, (0, 0))
        _bg_cache[key] = img
        if len(_bg_cache) > 6:
            _bg_cache.pop(next(iter(_bg_cache)))
        return img
    except Exception:
        return None


class _BaseMenuScreen:
    """Base for all menu screens: random photo background + button list."""

    def __init__(self, localizer: Localizer) -> None:
        """Create base menu state."""
        self._translate = localizer.gettext
        self._localizer = localizer
        self._buttons: list[Button] = []
        self._bg: pygame.Surface | None = None
        self._bg_size: tuple[int, int] = (0, 0)
        self._layout_size: tuple[int, int] | None = None

    def _ensure_bg(self, size: tuple[int, int]) -> None:
        if size != self._bg_size:
            self._bg_size = size
            self._bg = _random_bg(*size)

    def _maybe_layout(self, size: tuple[int, int]) -> None:
        """Re-run layout whenever the window size changes (resize/maximize)."""
        if size != self._layout_size:
            self._layout_size = size
            self.layout(size)

    def handle_event(self, event: pygame.event.Event) -> None:
        """Forward events to all buttons."""
        for btn in self._buttons:
            btn.handle_event(event)

    def update(self, dt_ms: int) -> None:
        """No-op by default."""

    def draw(self, surface: pygame.Surface) -> None:
        """Draw background then buttons; subclasses call this first."""
        size = surface.get_size()
        self._ensure_bg(size)
        if self._bg is not None:
            surface.blit(self._bg, (0, 0))
        else:
            surface.fill(BG_DARK)
        self._maybe_layout(size)
        for btn in self._buttons:
            btn.draw(surface)

    def layout(self, size: tuple[int, int]) -> None:
        """Position buttons; called once on first draw. Override as needed."""

    def _add_button(self, text: str, callback: Callable[[], None],
                    relx: float, rely: float, size: int = 24, bold: bool = True,
                    boxed: bool = False) -> Button:
        font = get_font(size, bold=bold, text=text)
        btn = Button(text, font, (0, 0), callback, boxed=boxed)
        btn._relx, btn._rely = relx, rely  # type: ignore[attr-defined]
        self._buttons.append(btn)
        return btn

    def _reposition_buttons(self, size: tuple[int, int]) -> None:
        w, h = size
        for btn in self._buttons:
            relx = getattr(btn, "_relx", 0.5)
            rely = getattr(btn, "_rely", 0.5)
            btn.set_center((int(w * relx), int(h * rely)))

    def _draw_title(self, surface: pygame.Surface, text: str, rely: float = 0.06, size: int = 34) -> None:
        w, h = surface.get_size()
        font = get_font(size, bold=True, text=text)
        shadow = font.render(text, True, (0, 0, 0))
        main = font.render(text, True, TEXT_GOLD)
        cx = w // 2
        cy = int(h * rely)
        surface.blit(shadow, shadow.get_rect(midtop=(cx + 3, cy + 3)))
        surface.blit(main, main.get_rect(midtop=(cx, cy)))

    def _draw_subtitle(self, surface: pygame.Surface, text: str, rely: float = 0.13, size: int = 16) -> None:
        w, h = surface.get_size()
        font = get_font(size, text=text)
        surf = font.render(text, True, TEXT_MUTED)
        surface.blit(surf, surf.get_rect(midtop=(w // 2, int(h * rely))))

    @staticmethod
    def _draw_card(surface: pygame.Surface, rect: pygame.Rect, alpha: int = 150) -> None:
        """Translucent dark card with a wooden border — groups controls."""
        card = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(card, (24, 14, 7, alpha), card.get_rect(), border_radius=12)
        surface.blit(card, rect.topleft)
        pygame.draw.rect(surface, (122, 84, 46), rect, width=2, border_radius=12)


def _plank_sign(w: int, h: int, rng) -> "Image.Image":
    """Compose a classic hanging plank sign from the real wood photo.

    Three horizontal boards with visible seams and per-board tone variation,
    a dark bevelled frame, and iron bolts in the corners.
    """
    from PIL import ImageEnhance

    frame = max(6, int(min(w, h) * 0.055))
    inner_w, inner_h = w - 2 * frame, h - 2 * frame

    photo_path = _ASSETS_DIR / "wood_bg.jpg"
    photo = Image.open(photo_path).convert("RGB") if photo_path.exists() else None

    def wood_patch(pw: int, ph: int) -> Image.Image:
        if photo is None:
            return Image.new("RGB", (pw, ph), (150, 103, 60))
        fw, fh = photo.size
        cw = min(fw, max(pw, fw // 2))
        chh = min(fh, max(ph, fh // 4))
        x0 = rng.randint(0, max(0, fw - cw))
        y0 = rng.randint(0, max(0, fh - chh))
        return photo.crop((x0, y0, x0 + cw, y0 + chh)).resize((pw, ph), Image.LANCZOS)

    # Face: three boards, each its own crop + slight tone shift
    face = Image.new("RGB", (inner_w, inner_h))
    n_boards = 3
    board_h = inner_h // n_boards
    for i in range(n_boards):
        bh = board_h if i < n_boards - 1 else inner_h - board_h * (n_boards - 1)
        board = wood_patch(inner_w, bh)
        board = ImageEnhance.Brightness(board).enhance(rng.uniform(0.88, 1.06))
        face.paste(board, (0, i * board_h))
    fd = ImageDraw.Draw(face)
    seam_w = max(1, int(h * 0.008))
    for i in range(1, n_boards):
        y = i * board_h
        fd.line([(0, y), (inner_w, y)], fill=(38, 24, 12), width=seam_w)
        fd.line([(0, y + seam_w), (inner_w, y + seam_w)],
                fill=(196, 158, 110), width=1)

    # Soft top-light so the face doesn't look like a flat print
    grad = Image.new("L", (1, inner_h))
    for y in range(inner_h):
        grad.putpixel((0, y), int(255 - 50 * (y / inner_h)))
    grad = grad.resize((inner_w, inner_h))
    face = ImageChops.multiply(face, Image.merge("RGB", (grad,) * 3))

    # Frame: darker wood, bevelled
    sign = wood_patch(w, h)
    sign = ImageEnhance.Brightness(sign).enhance(0.52)
    sign.paste(face, (frame, frame))
    sd = ImageDraw.Draw(sign)
    bevel = max(1, frame // 4)
    # Outer bevel: light top/left, dark bottom/right
    sd.rectangle([0, 0, w - 1, bevel], fill=(172, 128, 82))
    sd.rectangle([0, 0, bevel, h - 1], fill=(150, 110, 70))
    sd.rectangle([0, h - 1 - bevel, w - 1, h - 1], fill=(24, 14, 7))
    sd.rectangle([w - 1 - bevel, 0, w - 1, h - 1], fill=(30, 18, 9))
    # Inner lip around the face
    sd.rectangle([frame - bevel, frame - bevel, w - frame + bevel, h - frame + bevel],
                 outline=(26, 16, 8), width=bevel)

    # Iron corner bolts
    bolt_r = max(3, int(frame * 0.62))
    for bx in (frame // 2 + bevel, w - frame // 2 - bevel):
        for by in (frame // 2 + bevel, h - frame // 2 - bevel):
            sd.ellipse([bx - bolt_r, by - bolt_r, bx + bolt_r, by + bolt_r],
                       fill=(52, 48, 46), outline=(14, 12, 11),
                       width=max(1, bolt_r // 4))
            hr = max(1, bolt_r // 2)
            sd.ellipse([bx - hr, by - hr - 1, bx + hr, by + hr - 1],
                       fill=(96, 92, 88))

    return sign.convert("RGBA")


def _split_two_lines(text: str) -> tuple[str, str]:
    """Split text into two roughly balanced lines at a word boundary."""
    words = text.split()
    if len(words) <= 1:
        return text, ""
    best_split, best_diff = 1, None
    for i in range(1, len(words)):
        line1 = " ".join(words[:i])
        line2 = " ".join(words[i:])
        diff = abs(len(line1) - len(line2))
        if best_diff is None or diff < best_diff:
            best_diff, best_split = diff, i
    return " ".join(words[:best_split]), " ".join(words[best_split:])


def _draw_rope(
    surface: pygame.Surface, ax: float, ay: float, bx: float, by: float,
) -> None:
    """Draw a sagging, twisted rope from (ax, ay) down to (bx, by) on the bark."""
    sag = min(22.0, max(8.0, math.hypot(bx - ax, by - ay) * 0.10))
    mx, my = (ax + bx) / 2, (ay + by) / 2 + sag
    segments = 18
    pts = []
    for i in range(segments + 1):
        t = i / segments
        x = (1 - t) ** 2 * ax + 2 * (1 - t) * t * mx + t ** 2 * bx
        y = (1 - t) ** 2 * ay + 2 * (1 - t) * t * my + t ** 2 * by
        pts.append((x, y))

    pygame.draw.lines(surface, (34, 22, 12), False, pts, 7)
    pygame.draw.lines(surface, (96, 64, 34), False, pts, 5)
    pygame.draw.lines(surface, (148, 108, 64), False, pts, 2)

    for i in range(0, len(pts) - 1, 2):
        x0, y0 = pts[i]
        x1, y1 = pts[i + 1]
        dx, dy = x1 - x0, y1 - y0
        length = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / length, dx / length
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        pygame.draw.line(
            surface, (52, 34, 18),
            (cx - nx * 3.2, cy - ny * 3.2), (cx + nx * 3.2, cy + ny * 3.2), 1,
        )

    pygame.draw.circle(surface, (28, 16, 8), (int(bx), int(by)), 4)
    pygame.draw.circle(surface, (90, 62, 32), (int(bx), int(by)), 4, width=1)


class TitleScreen(_BaseMenuScreen):
    """Main title with hanging log sign; physics-based fall plays once."""

    _intro_played = False

    def __init__(
        self, localizer: Localizer,
        on_play: Callable[[], None], on_rules: Callable[[], None],
        on_set_locale: Callable[[str], None],
        on_exit: Callable[[], None],
    ) -> None:
        """Create title screen."""
        super().__init__(localizer)
        t = self._translate
        self._title_text = t(_("Explosive Backgammon"))

        self._add_button(t(_("Play")), on_play, 0.5, 0.54, size=28)
        self._add_button(t(_("Rules")), on_rules, 0.5, 0.66, size=28)

        langs = [("Русский", "ru"), ("English", "en"), ("Հայերեն", "hy")]
        for i, (text, code) in enumerate(langs):
            self._add_button(text, (lambda c=code: on_set_locale(c)),
                             0.35 + i * 0.15, 0.81, size=15, bold=False)

        self._add_button(t(_("Exit")), on_exit, 0.5, 0.92, size=15, bold=False)

        self._log_photo: pygame.Surface | None = None
        self._log_photo_key: tuple[int, int] | None = None
        self._log_pos = [0.0, -150.0]
        self._log_vel = [0.0, 0.0]
        self._anim_phase = "idle"
        self._anchor_cx = 0.0
        self._target_y = 0.0
        self._settle_frames = 0
        self._log_w = 0
        self._log_h = 0
        # Ropes tie to the sign's top corners.
        self._attach_x_frac_l = 0.07
        self._attach_x_frac_r = 0.93
        self._attach_y_frac_l = 0.03
        self._attach_y_frac_r = 0.03

    def layout(self, size: tuple[int, int]) -> None:
        """Position buttons and start the fall animation (once per process)."""
        self._reposition_buttons(size)
        w, h = size
        self._log_w = min(600, int(w * 0.52))
        self._log_h = int(self._log_w * 0.42)
        self._anchor_cx = w / 2
        self._target_y = self._log_h / 2 + 30
        if TitleScreen._intro_played:
            self._log_pos = [self._anchor_cx, self._target_y]
            self._anim_phase = "done"
        else:
            TitleScreen._intro_played = True
            self._log_pos = [self._anchor_cx, -150.0]
            self._log_vel = [0.0, 0.0]
            self._anim_phase = "fall"

    def update(self, dt_ms: int) -> None:
        """Advance the spring-damper fall physics."""
        if self._anim_phase == "done":
            return
        sub_ms = 16.0
        accum = getattr(self, "_phys_accum", 0.0) + dt_ms
        while accum >= sub_ms:
            accum -= sub_ms
            self._tick_physics()
        self._phys_accum = accum

    def _tick_physics(self) -> None:
        if self._anim_phase == "fall":
            self._log_vel[1] += 1.15
            self._log_pos[1] += self._log_vel[1]
            if self._log_pos[1] >= self._target_y:
                self._log_pos[1] = self._target_y
                self._log_vel[1] = -self._log_vel[1] * 0.40
                self._log_vel[0] = random.choice((-1, 1)) * random.uniform(6.0, 9.0)
                self._anim_phase = "settle"
        elif self._anim_phase == "settle":
            k, damp = 0.085, 0.90
            ax = (self._anchor_cx - self._log_pos[0]) * k
            ay = (self._target_y - self._log_pos[1]) * k
            self._log_vel[0] = (self._log_vel[0] + ax) * damp
            self._log_vel[1] = (self._log_vel[1] + ay) * damp
            self._log_pos[0] += self._log_vel[0]
            self._log_pos[1] += self._log_vel[1]

            settled = (
                abs(self._log_vel[0]) < 0.12 and abs(self._log_vel[1]) < 0.12
                and abs(self._log_pos[0] - self._anchor_cx) < 0.6
                and abs(self._log_pos[1] - self._target_y) < 0.6
            )
            self._settle_frames = self._settle_frames + 1 if settled else 0
            if self._settle_frames > 3:
                self._log_pos = [self._anchor_cx, self._target_y]
                self._anim_phase = "done"

    def _ensure_log_photo(self, log_w: int, log_h: int) -> None:
        key = (log_w, log_h)
        if self._log_photo_key == key and self._log_photo is not None:
            return
        try:
            ss = 2
            W, H = log_w * ss, log_h * ss
            rng = random.Random(20260630)

            wood = _plank_sign(W, H, rng)

            # Ropes tie to the top corners of the frame.
            self._attach_y_frac_l = 0.03
            self._attach_y_frac_r = 0.03

            from nardy.ui.runtime import contains_armenian
            font_candidates = (
                ("C:/Windows/Fonts/sylfaen.ttf",)
                if contains_armenian(self._title_text)
                else ("C:/Windows/Fonts/georgiab.ttf", "C:/Windows/Fonts/georgia.ttf",
                      "C:/Windows/Fonts/timesbd.ttf")
            )
            font_path = None
            for fp in font_candidates:
                try:
                    ImageFont.truetype(fp, 10)
                    font_path = fp
                    break
                except Exception:
                    continue

            def _load_font(size: int) -> ImageFont.FreeTypeFont:
                if font_path is not None:
                    return ImageFont.truetype(font_path, size)
                return ImageFont.load_default()

            line1, line2 = _split_two_lines(self._title_text)
            font_size = int(H * 0.24)
            font = _load_font(font_size)
            text_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            td = ImageDraw.Draw(text_layer)
            bbox1 = td.textbbox((0, 0), line1, font=font)
            bbox2 = td.textbbox((0, 0), line2, font=font) if line2 else (0, 0, 0, 0)

            # Auto-shrink if the widest line would overflow the bark width.
            max_line_w = max(bbox1[2] - bbox1[0], bbox2[2] - bbox2[0])
            available_w = W * 0.82
            if max_line_w > available_w:
                font_size = max(10, int(font_size * available_w / max_line_w))
                font = _load_font(font_size)
                bbox1 = td.textbbox((0, 0), line1, font=font)
                bbox2 = td.textbbox((0, 0), line2, font=font) if line2 else (0, 0, 0, 0)
            h1 = bbox1[3] - bbox1[1]
            h2 = bbox2[3] - bbox2[1]
            line_gap = H * 0.05
            total_h = h1 + (h2 + line_gap if line2 else 0)
            start_y = (H - total_h) / 2
            ty1 = start_y - bbox1[1]
            tx1 = (W - (bbox1[2] - bbox1[0])) / 2 - bbox1[0]
            placements = [((tx1, ty1), line1)]
            if line2:
                ty2 = start_y + h1 + line_gap - bbox2[1]
                tx2 = (W - (bbox2[2] - bbox2[0])) / 2 - bbox2[0]
                placements.append(((tx2, ty2), line2))

            # Burnt-in (pyrography) lettering that stays readable on both the
            # light and dark bark plates: a wide scorch halo darkens the wood
            # around the glyphs, a charred outline rings them, and the glyph
            # itself is bright heated gold with an ember-orange core.
            halo = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            hd = ImageDraw.Draw(halo)
            for pos, line in placements:
                hd.text(pos, line, font=font, fill=(30, 13, 4, 235))
            halo = halo.filter(ImageFilter.GaussianBlur(4 * ss))
            text_layer.alpha_composite(halo)
            char_off = max(1, int(1.2 * ss))
            for pos, line in placements:
                for dx, dy in ((-char_off, 0), (char_off, 0), (0, -char_off), (0, char_off),
                               (char_off, char_off)):
                    td.text((pos[0] + dx, pos[1] + dy), line, font=font,
                            fill=(28, 12, 4, 255))
                td.text(pos, line, font=font, fill=(233, 196, 128, 255))
                td.text((pos[0] + ss * 0.6, pos[1] + ss * 0.8), line, font=font,
                        fill=(206, 118, 38, 110))
            wood = Image.alpha_composite(wood, text_layer)

            wood = wood.filter(ImageFilter.SMOOTH)
            final = wood.resize((log_w, log_h), Image.LANCZOS)
            self._log_photo = pil_to_surface(final)
            self._log_photo_key = key
        except Exception:
            self._log_photo = None

    def draw(self, surface: pygame.Surface) -> None:
        """Draw background, hanging log, card, then buttons."""
        size = surface.get_size()
        self._ensure_bg(size)
        if self._bg is not None:
            surface.blit(self._bg, (0, 0))
        else:
            surface.fill(BG_DARK)
        self._maybe_layout(size)

        self._draw_log(surface, size)

        w, h = size
        card = pygame.Rect(0, 0, min(480, int(w * 0.5)), int(h * 0.46))
        card.center = (w // 2, int(h * 0.72))
        self._draw_card(surface, card)

        for btn in self._buttons:
            btn.draw(surface)

    def _draw_log(self, surface: pygame.Surface, size: tuple[int, int]) -> None:
        log_w, log_h = self._log_w, self._log_h
        self._ensure_log_photo(log_w, log_h)

        log_cx, log_cy = self._log_pos
        log_x1 = log_cx - log_w / 2
        log_y1 = log_cy - log_h / 2

        anchor_l = self._anchor_cx - log_w / 2 + self._attach_x_frac_l * log_w
        anchor_r = self._anchor_cx - log_w / 2 + self._attach_x_frac_r * log_w
        attach_l = log_x1 + self._attach_x_frac_l * log_w
        attach_r = log_x1 + self._attach_x_frac_r * log_w
        attach_top_l = log_y1 + self._attach_y_frac_l * log_h
        attach_top_r = log_y1 + self._attach_y_frac_r * log_h

        # Ropes run behind the sign to its top corners; drawing them first
        # lets the frame hide the rope ends naturally.
        _draw_rope(surface, anchor_l, -20, attach_l, attach_top_l + 6)
        _draw_rope(surface, anchor_r, -20, attach_r, attach_top_r + 6)

        if self._log_photo is not None:
            surface.blit(self._log_photo, (int(log_x1), int(log_y1)))


class PlayModeScreen(_BaseMenuScreen):
    """Choose play mode: Online / vs AI / Local, plus board theme."""

    def __init__(
        self, localizer: Localizer,
        on_network: Callable[[], None], on_ai: Callable[[], None], on_local: Callable[[], None],
        on_back: Callable[[], None],
    ) -> None:
        """Create play mode selection screen."""
        super().__init__(localizer)
        t = self._translate

        self._add_button(t(_("Online")), on_network, 0.5, 0.32, size=26)
        self._add_button(t(_("vs AI")), on_ai, 0.5, 0.45, size=26)
        self._add_button(t(_("Local game")), on_local, 0.5, 0.58, size=26)

        self._theme_buttons: dict[str, Button] = {}
        for i, key in enumerate(THEMES.keys()):
            theme = THEMES[key]
            btn = self._add_button(
                t(_(theme["label"])), (lambda k=key: self._select_theme(k)),
                0.42 + i * 0.16, 0.78, size=16,
            )
            self._theme_buttons[key] = btn
        self._highlight_theme()

        self._add_button(t(_("Back to menu")), on_back, 0.5, 0.90, size=15, bold=False)

    def _select_theme(self, key: str) -> None:
        set_theme(key)
        self._highlight_theme()

    def _highlight_theme(self) -> None:
        active = get_theme()
        for key, btn in self._theme_buttons.items():
            btn.color = TEXT_GOLD if key == active else TEXT_MUTED

    def draw(self, surface: pygame.Surface) -> None:
        """Draw background, card, title, subtitle, buttons."""
        size = surface.get_size()
        self._ensure_bg(size)
        if self._bg is not None:
            surface.blit(self._bg, (0, 0))
        else:
            surface.fill(BG_DARK)
        self._maybe_layout(size)

        w, h = size
        card = pygame.Rect(0, 0, min(520, int(w * 0.55)), int(h * 0.76))
        card.center = (w // 2, int(h * 0.55))
        self._draw_card(surface, card)

        self._draw_title(surface, self._translate(_("Play")), rely=0.06)
        self._draw_subtitle(surface, self._translate(_("Choose a mode")))
        self._draw_subtitle(surface, self._translate(_("Style")) + ":", rely=0.72)
        for btn in self._buttons:
            btn.draw(surface)

    def layout(self, size: tuple[int, int]) -> None:
        """Position all buttons."""
        self._reposition_buttons(size)


class AIMenuScreen(_BaseMenuScreen):
    """Choose AI difficulty, color, and game type on one screen."""

    def __init__(
        self, localizer: Localizer,
        on_start: Callable[[str, str, str], None],
        on_back: Callable[[], None],
    ) -> None:
        """Create AI difficulty/mode selection."""
        super().__init__(localizer)
        t = self._translate
        self._on_start = on_start
        self._selected_diff = "medium"
        self._selected_color = "white"

        difficulties = [
            ("easy", t(_("Easy"))), ("medium", t(_("Medium"))),
            ("hard", t(_("Hard"))), ("pro", t(_("Pro"))),
        ]
        self._diff_buttons: dict[str, Button] = {}
        for i, (key, label) in enumerate(difficulties):
            btn = self._add_button(label, (lambda d=key: self._select_diff(d)),
                                   0.5, 0.24 + i * 0.10, size=20)
            self._diff_buttons[key] = btn
        self._highlight_diff()

        self._color_buttons: dict[str, Button] = {
            "white": self._add_button(t(_("White")), lambda: self._select_color("white"),
                                      0.42, 0.68, size=16),
            "black": self._add_button(t(_("Black")), lambda: self._select_color("black"),
                                      0.58, 0.68, size=16),
        }
        self._highlight_color()

        self._add_button(t(_("Long backgammon")),
                         lambda: on_start("long", self._selected_diff, self._selected_color),
                         0.35, 0.80, size=16)
        self._add_button(t(_("Short backgammon")),
                         lambda: on_start("short", self._selected_diff, self._selected_color),
                         0.65, 0.80, size=16)

        self._add_button(t(_("Back to menu")), on_back, 0.5, 0.92, size=15, bold=False)

    def _select_diff(self, diff: str) -> None:
        self._selected_diff = diff
        self._highlight_diff()

    def _highlight_diff(self) -> None:
        for key, btn in self._diff_buttons.items():
            btn.color = TEXT_GOLD if key == self._selected_diff else TEXT_LIGHT

    def _select_color(self, color: str) -> None:
        self._selected_color = color
        self._highlight_color()

    def _highlight_color(self) -> None:
        for key, btn in self._color_buttons.items():
            btn.color = TEXT_GOLD if key == self._selected_color else TEXT_MUTED

    def draw(self, surface: pygame.Surface) -> None:
        """Draw background, card, headers, buttons, color chips."""
        size = surface.get_size()
        self._ensure_bg(size)
        if self._bg is not None:
            surface.blit(self._bg, (0, 0))
        else:
            surface.fill(BG_DARK)
        self._maybe_layout(size)

        w, h = size
        card = pygame.Rect(0, 0, min(560, int(w * 0.6)), int(h * 0.86))
        card.center = (w // 2, int(h * 0.53))
        self._draw_card(surface, card)

        self._draw_title(surface, self._translate(_("vs AI")), rely=0.04)
        self._draw_subtitle(surface, self._translate(_("Choose difficulty")), rely=0.11)
        self._draw_subtitle(surface, self._translate(_("Your color")) + ":", rely=0.62)
        self._draw_subtitle(surface, self._translate(_("Choose a mode")) + ":", rely=0.74)

        for btn in self._buttons:
            btn.draw(surface)

        # Drawn checker chips next to the color labels (font glyphs like
        # "⚪" render as tofu boxes in Georgia/Sylfaen).
        for key, btn in self._color_buttons.items():
            chip_r = 9
            cx = btn.rect.left - 2
            cy = btn.rect.centery
            fill = (240, 236, 226) if key == "white" else (56, 36, 22)
            pygame.gfxdraw.filled_circle(surface, cx, cy, chip_r, fill)
            pygame.gfxdraw.aacircle(surface, cx, cy, chip_r, (20, 12, 6))
            if key == self._selected_color:
                pygame.gfxdraw.aacircle(surface, cx, cy, chip_r + 3, TEXT_GOLD)
                pygame.gfxdraw.aacircle(surface, cx, cy, chip_r + 4, TEXT_GOLD)

    def layout(self, size: tuple[int, int]) -> None:
        """Position all buttons."""
        self._reposition_buttons(size)


class LocalMenuScreen(_BaseMenuScreen):
    """Local game: Long / Short backgammon."""

    def __init__(
        self, localizer: Localizer,
        on_start_long: Callable[[], None], on_start_short: Callable[[], None],
        on_back: Callable[[], None],
    ) -> None:
        """Create local game menu."""
        super().__init__(localizer)
        t = self._translate
        self._add_button(t(_("Long backgammon")), on_start_long, 0.5, 0.42, size=26)
        self._add_button(t(_("Short backgammon")), on_start_short, 0.5, 0.56, size=26)
        self._add_button(t(_("Back to menu")), on_back, 0.5, 0.88, size=15, bold=False)

    def draw(self, surface: pygame.Surface) -> None:
        """Draw background, card, title, buttons."""
        size = surface.get_size()
        self._ensure_bg(size)
        if self._bg is not None:
            surface.blit(self._bg, (0, 0))
        else:
            surface.fill(BG_DARK)
        self._maybe_layout(size)

        w, h = size
        card = pygame.Rect(0, 0, min(480, int(w * 0.5)), int(h * 0.66))
        card.center = (w // 2, int(h * 0.60))
        self._draw_card(surface, card)

        self._draw_title(surface, self._translate(_("Local game")), rely=0.06)
        for btn in self._buttons:
            btn.draw(surface)

    def layout(self, size: tuple[int, int]) -> None:
        """Position all buttons."""
        self._reposition_buttons(size)


class NetworkMenuScreen(_BaseMenuScreen):
    """Online play, kept as simple as possible.

    Pick a mode, one big "create game" button that yields a shareable code,
    and one field to paste the opponent's code into.
    """

    def __init__(self, localizer: Localizer, on_back: Callable[[], None]) -> None:
        """Create the online menu."""
        super().__init__(localizer)
        t = self._translate
        self._on_back_cb = on_back

        self._selected_mode = "long"
        self._mode_buttons: dict[str, Button] = {
            "long": self._add_button(t(_("Long backgammon")),
                                     lambda: self._select_mode("long"), 0.38, 0.235, size=20),
            "short": self._add_button(t(_("Short backgammon")),
                                      lambda: self._select_mode("short"), 0.62, 0.235, size=20),
        }
        self._highlight_mode()

        self._add_button(t(_("Host Game")), self._do_auto_host, 0.5, 0.36, size=24, boxed=True)
        self._copy_button = Button(
            t(_("Copy code")), get_font(15), (0, 0), self._copy_address, boxed=True,
        )
        self._add_button(t(_("Join")), self._do_auto_join, 0.5, 0.83, size=20, boxed=True)
        self._add_button(t(_("Back to menu")), on_back, 0.5, 0.965, size=15, bold=False)

        self._code_input = TextInput(
            get_font(16), pygame.Rect(0, 0, 380, 40), placeholder=t(_("Code from host")),
        )

        self._tunnel_status = ""
        self._tunnel_status_color = TEXT_GOLD
        self._tunnel_address: str | None = None
        self._copy_flash_ms = 0.0

    def layout(self, size: tuple[int, int]) -> None:
        """Position buttons and the code field."""
        self._reposition_buttons(size)
        w, h = size
        self._copy_button.set_center((int(w * 0.5), int(h * 0.545)))
        self._code_input.rect.center = (int(w * 0.5), int(h * 0.73))

    def handle_event(self, event: pygame.event.Event) -> None:
        """Forward to buttons and the code field."""
        super().handle_event(event)
        if self._tunnel_address:
            self._copy_button.handle_event(event)
        self._code_input.handle_event(event)

    def update(self, dt_ms: int) -> None:
        """Blink the cursor and fade the copy-confirmation flash."""
        self._code_input.update(dt_ms)
        if self._copy_flash_ms > 0:
            self._copy_flash_ms = max(0.0, self._copy_flash_ms - dt_ms)

    def draw(self, surface: pygame.Surface) -> None:
        """Draw background, card, controls."""
        size = surface.get_size()
        self._ensure_bg(size)
        if self._bg is not None:
            surface.blit(self._bg, (0, 0))
        else:
            surface.fill(BG_DARK)
        self._maybe_layout(size)

        t = self._translate
        w, h = size

        card = pygame.Rect(0, 0, min(600, int(w * 0.62)), int(h * 0.78))
        card.center = (w // 2, int(h * 0.545))
        self._draw_card(surface, card)

        self._draw_title(surface, t(_("Online")), rely=0.03, size=30)
        self._draw_subtitle(surface, t(_("Choose a mode")), rely=0.175, size=15)

        status_text = self._tunnel_status
        if status_text:
            font = get_font(14, bold=True, text=status_text)
            ly = int(h * 0.455)
            for line in _wrap_status(status_text, font, card.width - 40):
                surf_line = font.render(line, True, self._tunnel_status_color)
                surface.blit(surf_line, surf_line.get_rect(center=(w // 2, ly)))
                ly += font.get_height() + 2

        if self._tunnel_address:
            if self._copy_flash_ms > 0:
                self._copy_button.text = t(_("Copied!"))
                self._copy_button.color = (96, 224, 96)
            else:
                self._copy_button.text = t(_("Copy code"))
                self._copy_button.color = TEXT_LIGHT
            self._copy_button.draw(surface)

        self._draw_subtitle(surface, t(_("Code from host")) + ":", rely=0.655, size=15)
        self._code_input.draw(surface)

        for btn in self._buttons:
            btn.draw(surface)

    def _select_mode(self, mode: str) -> None:
        self._selected_mode = mode
        self._highlight_mode()

    def _highlight_mode(self) -> None:
        for key, btn in self._mode_buttons.items():
            btn.color = TEXT_GOLD if key == self._selected_mode else TEXT_MUTED

    def _copy_address(self) -> None:
        if not self._tunnel_address:
            return
        from nardy.ui.clipboard import set_text
        set_text(self._tunnel_address)
        self._copy_flash_ms = 1200.0

    def _do_auto_host(self) -> None:
        import threading
        t = self._translate
        self._tunnel_status = t(_("Starting tunnel..."))
        self._tunnel_status_color = (224, 192, 96)

        def _start() -> None:
            from nardy.net.tunnel import is_ssh_available
            if not is_ssh_available():
                self._tunnel_status = t(_("ssh not found — needed for Online play."))
                self._tunnel_status_color = (224, 96, 96)
                return

            # Spawn the game window as host; the tunnel lives in THAT
            # process (closing this menu must not kill the opponent's
            # game), and it reports the public address back on stdout.
            args = [sys.executable, "-m", "nardy", "--server", "--tunnel",
                    "--mode", self._selected_mode,
                    "--locale", self._localizer.locale_code]
            try:
                process = subprocess.Popen(
                    args, stdout=subprocess.PIPE, text=True, bufsize=1,
                )
            except Exception as e:
                self._tunnel_status = str(e)
                self._tunnel_status_color = (224, 96, 96)
                return

            addr = error = None
            for line in process.stdout:
                line = line.strip()
                if line.startswith("TUNNEL_ADDR "):
                    addr = line.removeprefix("TUNNEL_ADDR ")
                    break
                if line.startswith("TUNNEL_ERROR "):
                    error = line.removeprefix("TUNNEL_ERROR ")
                    break
            if addr:
                self._tunnel_address = addr
                from nardy.ui.clipboard import set_text
                set_text(addr)
                self._tunnel_status = t(_("Share this code with opponent")) + f": {addr}"
                self._tunnel_status_color = (96, 224, 96)
            else:
                self._tunnel_status = error or "Tunnel failed"
                self._tunnel_status_color = (224, 96, 96)

        threading.Thread(target=_start, daemon=True).start()

    def _do_auto_join(self) -> None:
        code = self._code_input.text.strip()
        if not code:
            return
        from nardy.net.tunnel import parse_tunnel_address
        host, port = parse_tunnel_address(code)
        args = [sys.executable, "-m", "nardy", "--join",
                "--socket-host", host, "--socket-port", str(port),
                "--locale", self._localizer.locale_code]
        try:
            subprocess.Popen(args)
        except Exception:
            return
        self._on_back_cb()


def _wrap_status(text, font, max_width):
    """Word-wrap the status line to fit inside the card."""
    words = text.split(" ")
    lines = []
    current = ""
    for word in words:
        candidate = (current + " " + word).strip()
        if font.size(candidate)[0] <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


class RulesScreen(_BaseMenuScreen):
    """Rules with tabs for Long/Short backgammon."""

    def __init__(self, localizer: Localizer, on_back: Callable[[], None]) -> None:
        """Create rules screen with tabbed scrollable content."""
        super().__init__(localizer)
        t = self._translate
        self._active_tab = "long"

        self._tab_long = self._add_button(t(_("Long backgammon")), lambda: self._switch_tab("long"),
                                          0.35, 0.13, size=16)
        self._tab_short = self._add_button(t(_("Short backgammon")), lambda: self._switch_tab("short"),
                                           0.65, 0.13, size=16)
        self._add_button(t(_("Back to menu")), on_back, 0.5, 0.94, size=15, bold=False)

        self._panel = ScrollableText(pygame.Rect(0, 0, 100, 100), "georgia", 14)
        self._update_tab_highlight()
        self._render_rules()

    def layout(self, size: tuple[int, int]) -> None:
        """Position buttons and the scrollable panel."""
        self._reposition_buttons(size)
        w, h = size
        panel_w = int(w * 0.86)
        panel_h = int(h * 0.72)
        self._panel.rect = pygame.Rect((w - panel_w) // 2, int(h * 0.19), panel_w, panel_h)
        self._panel._rebuild()

    def handle_event(self, event: pygame.event.Event) -> None:
        """Forward to buttons and scrollable panel."""
        super().handle_event(event)
        self._panel.handle_event(event)

    def update(self, dt_ms: int) -> None:
        """Update panel (no-op)."""
        self._panel.update(dt_ms)

    def _switch_tab(self, tab: str) -> None:
        self._active_tab = tab
        self._update_tab_highlight()
        self._render_rules()

    def _update_tab_highlight(self) -> None:
        self._tab_long.color = TEXT_GOLD if self._active_tab == "long" else TEXT_MUTED
        self._tab_short.color = TEXT_GOLD if self._active_tab == "short" else TEXT_MUTED

    def _render_rules(self) -> None:
        t = self._translate
        if self._active_tab == "long":
            sections = [
                (t(_("LONG BACKGAMMON")), "h1"),
                (t(_(
                    "Backgammon is a traditional game for two players. Each player has 15 checkers. "
                    "The goal is to move all the checkers counterclockwise across the entire board, "
                    "bring them into your home and remove them before your opponent."
                )), "body"),
                (t(_("Setup")), "h2"),
                (t(_(
                    "At the beginning of the game, all 15 white checkers are on point 24, all 15 "
                    "black checkers are on point 12. This is called the “head”. White moves "
                    "from 24 to 1. Black moves from 12 through 1 and then in a circle to 13."
                )), "body"),
                (t(_("Movement")), "h2"),
                (t(_(
                    "Players take turns rolling two dice and moving the checkers by the number of "
                    "points rolled. Each die value is a separate move with one checker (or two "
                    "different checkers). If a double is rolled (the same numbers on both dice), "
                    "the number of moves is doubled: instead of two moves, the player makes four "
                    "moves with this value."
                )), "body"),
                (t(_(
                    "You cannot place a checker on a point occupied by at least one opponent's "
                    "checker. In long backgammon there is no capture (combat) - opponents' checkers "
                    "simply cannot be on the same point at the same time."
                )), "body"),
                (t(_(
                    "If a move is possible in at least one way, the player must make it, even if "
                    "it is disadvantageous. If no dice can be used, the turn is skipped."
                )), "body"),
                (t(_("Head Rule")), "h2"),
                (t(_(
                    "Only one checker can be removed from the head (starting point) per move. The "
                    "exception applies once during the entire game: if on the very first move a "
                    "player throws a double 3-3, 4-4 or 6-6, he is allowed to remove two checkers "
                    "from his head at once."
                )), "body"),
                (t(_("Blocking")), "h2"),
                (t(_(
                    "It is prohibited to build a continuous screen of six or more points in a row "
                    "occupied by your own checkers, if not a single checker of the opponent has yet "
                    "entered its home quarter (the zone from which checkers are removed). As soon as "
                    "the opponent has at least one checker in his house, building such a screen is "
                    "allowed."
                )), "body"),
                (t(_("Bearing Off")), "h2"),
                (t(_(
                    "When all 15 of a player's checkers are in his home (the last quarter of the "
                    "way), he begins to remove them from the board. A checker is removed if the "
                    "rolled number of the cube exactly matches its position, or - if there are no "
                    "checkers at more distant points of the house - with a larger number."
                )), "body"),
                (t(_(
                    "The winner is the player who is the first to remove all 15 of his checkers "
                    "from the board."
                )), "body"),
            ]
        else:
            sections = [
                (t(_("SHORT BACKGAMMON")), "h1"),
                (t(_(
                    "Short backgammon (classic backgammon, backgammon) is a game for two players "
                    "with the ability to capture the opponent’s checkers. Each player has 15 "
                    "checkers."
                )), "body"),
                (t(_("Setup")), "h2"),
                (t(_(
                    "The initial arrangement is standard: White has 2 checkers at point 24, 5 at "
                    "point 13, 3 at point 8 and 5 at point 6. Black has a mirror: 2 at point 1, 5 at "
                    "point 12, 3 at point 17 and 5 at point 19. White moves from 24 to 1, black - "
                    "from 1 to 24."
                )), "body"),
                (t(_("Movement")), "h2"),
                (t(_(
                    "Two dice are rolled and the checkers are moved to the values shown. With a "
                    "double, the number of moves doubles to four."
                )), "body"),
                (t(_("Capturing")), "h2"),
                (t(_(
                    "If there is exactly one opponent's checker (blot) on a point, you can place "
                    "your own checker on it - the opponent's checker is removed from the board and "
                    "sent to the bar (the middle of the board). A point with two or more opponent's "
                    "checkers is blocked - you cannot stand on it."
                )), "body"),
                (t(_("The Bar")), "h2"),
                (t(_(
                    "The checker from the bar must come into play first before the player makes any "
                    "other move. The entry is made into the opponent's home quarter, at the point "
                    "corresponding to the value of the die. If all the necessary points are blocked, "
                    "the move is skipped completely."
                )), "body"),
                (t(_("Bearing Off")), "h2"),
                (t(_(
                    "Removal of checkers begins only when all 15 of a player's checkers are in his "
                    "house. The withdrawal principle is the same as in long backgammon."
                )), "body"),
                (t(_(
                    "The winner is the player who is the first to remove all his checkers from the "
                    "board."
                )), "body"),
            ]
        self._panel.set_content(sections)

    def draw(self, surface: pygame.Surface) -> None:
        """Draw background, title, tabs, panel, back button."""
        size = surface.get_size()
        self._ensure_bg(size)
        if self._bg is not None:
            surface.blit(self._bg, (0, 0))
        else:
            surface.fill(BG_DARK)
        self._maybe_layout(size)

        self._draw_title(surface, self._translate(_("Rules")), rely=0.02, size=26)
        self._panel.draw(surface)
        for btn in self._buttons:
            btn.draw(surface)
