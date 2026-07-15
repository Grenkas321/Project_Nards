"""Minimal Pygame UI runtime: scheduler, screen protocol, text input, scroll widget."""

from __future__ import annotations

import heapq
import itertools
from collections.abc import Callable
from typing import Protocol

import pygame

# ── Color palette (shared across screens) ──────────────────────────────

BG_DARK = (42, 21, 8)
WOOD_DARK = (58, 37, 21)
WOOD_MID = (90, 58, 32)
WOOD_LIGHT = (138, 90, 48)
TEXT_LIGHT = (240, 223, 192)
TEXT_MUTED = (168, 136, 96)
TEXT_GOLD = (255, 224, 144)
ACCENT_RED = (192, 57, 45)


# ── Scheduler — replaces tkinter's root.after() ────────────────────────

class Scheduler:
    """Frame-driven delayed-callback scheduler."""

    def __init__(self) -> None:
        """Initialize an empty timer heap."""
        self._heap: list[tuple[int, int, Callable[[], None]]] = []
        self._counter = itertools.count()
        self._now = 0

    def schedule(self, delay_ms: int, callback: Callable[[], None]) -> None:
        """Schedule callback to run after delay_ms (relative to last update())."""
        heapq.heappush(self._heap, (self._now + delay_ms, next(self._counter), callback))

    def update(self, dt_ms: int) -> None:
        """Advance the clock and fire any due callbacks."""
        self._now += dt_ms
        while self._heap and self._heap[0][0] <= self._now:
            _, _, callback = heapq.heappop(self._heap)
            try:
                callback()
            except Exception:
                pass

    def clear(self) -> None:
        """Cancel all pending callbacks."""
        self._heap.clear()


# ── Screen protocol ─────────────────────────────────────────────────────

class Screen(Protocol):
    """Contract every UI screen must satisfy."""

    def handle_event(self, event: pygame.event.Event) -> None:
        """Process one pygame event."""

    def update(self, dt_ms: int) -> None:
        """Advance animations/state by dt_ms milliseconds."""

    def draw(self, surface: pygame.Surface) -> None:
        """Render the screen onto the given surface."""


# ── Button helper ────────────────────────────────────────────────────────

class Button:
    """A clickable text button with hover highlight; optional boxed style."""

    def __init__(
        self,
        text: str,
        font: pygame.font.Font,
        center: tuple[int, int],
        callback: Callable[[], None],
        color: tuple[int, int, int] = TEXT_LIGHT,
        hover_color: tuple[int, int, int] = TEXT_GOLD,
        boxed: bool = False,
    ) -> None:
        """Create a button rendered as shadowed text, optionally on a plate."""
        self.text = text
        self.font = font
        self.center = center
        self.callback = callback
        self.color = color
        self.hover_color = hover_color
        self.boxed = boxed
        self.enabled = True
        self._hover = False
        self.rect = pygame.Rect(0, 0, 0, 0)
        self._update_rect()

    def _update_rect(self) -> None:
        surf = self.font.render(self.text, True, self.color)
        self.rect = surf.get_rect(center=self.center)
        # Generous click padding
        self.rect.inflate_ip(28, 18)

    def set_center(self, center: tuple[int, int]) -> None:
        """Reposition the button."""
        self.center = center
        self._update_rect()

    def handle_event(self, event: pygame.event.Event) -> None:
        """Track hover and clicks."""
        if not self.enabled:
            self._hover = False
            return
        if event.type == pygame.MOUSEMOTION:
            self._hover = self.rect.collidepoint(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                self.callback()

    def draw(self, surface: pygame.Surface) -> None:
        """Render optional plate, shadow + text; color shifts on hover."""
        if not self.enabled:
            color = (110, 92, 72)
        else:
            color = self.hover_color if self._hover else self.color
        if self.boxed:
            plate = (66, 44, 26) if (self._hover and self.enabled) else (52, 34, 20)
            pygame.draw.rect(surface, plate, self.rect, border_radius=8)
            border = TEXT_GOLD if (self._hover and self.enabled) else WOOD_LIGHT
            pygame.draw.rect(surface, border, self.rect, width=2, border_radius=8)
        shadow = self.font.render(self.text, True, (0, 0, 0))
        shadow_rect = shadow.get_rect(center=(self.center[0] + 2, self.center[1] + 2))
        surface.blit(shadow, shadow_rect)
        text_surf = self.font.render(self.text, True, color)
        text_rect = text_surf.get_rect(center=self.center)
        surface.blit(text_surf, text_rect)


# ── Text input field ─────────────────────────────────────────────────────

class TextInput:
    """Single-line text field with cursor, focus, backspace, and clipboard paste."""

    def __init__(
        self,
        font: pygame.font.Font,
        rect: pygame.Rect,
        initial: str = "",
        placeholder: str = "",
    ) -> None:
        """Create a text input box."""
        self.font = font
        self.rect = rect
        self.text = initial
        self.placeholder = placeholder
        self.focused = False
        self._cursor_visible = True
        self._cursor_timer = 0

    def handle_event(self, event: pygame.event.Event) -> None:
        """Handle focus, typing, and paste."""
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.focused = self.rect.collidepoint(event.pos)
            return
        if not self.focused:
            return
        if event.type == pygame.KEYDOWN:
            mods = pygame.key.get_mods()
            if event.key == pygame.K_BACKSPACE:
                self.text = self.text[:-1]
            elif event.key == pygame.K_v and (mods & pygame.KMOD_CTRL):
                self._paste()
            elif event.key in (pygame.K_RETURN, pygame.K_TAB):
                self.focused = False
            elif event.unicode and event.unicode.isprintable():
                self.text += event.unicode

    def _paste(self) -> None:
        from nardy.ui.clipboard import get_text
        text = get_text()
        if text:
            self.text += text

    def update(self, dt_ms: int) -> None:
        """Blink the cursor."""
        self._cursor_timer += dt_ms
        if self._cursor_timer >= 500:
            self._cursor_timer = 0
            self._cursor_visible = not self._cursor_visible

    def draw(self, surface: pygame.Surface) -> None:
        """Render box, text, and blinking cursor."""
        bg = (58, 42, 28) if self.focused else (46, 32, 20)
        pygame.draw.rect(surface, bg, self.rect, border_radius=4)
        border = TEXT_GOLD if self.focused else WOOD_LIGHT
        pygame.draw.rect(surface, border, self.rect, width=2, border_radius=4)

        display = self.text if (self.text or self.focused) else self.placeholder
        color = TEXT_LIGHT if (self.text or self.focused) else TEXT_MUTED
        text_surf = self.font.render(display, True, color)
        text_rect = text_surf.get_rect(midleft=(self.rect.left + 8, self.rect.centery))
        # Clip to box
        prev_clip = surface.get_clip()
        surface.set_clip(self.rect.inflate(-6, -4))
        surface.blit(text_surf, text_rect)
        if self.focused and self._cursor_visible:
            cx = text_rect.right + 2
            pygame.draw.line(
                surface, TEXT_LIGHT,
                (cx, self.rect.top + 6), (cx, self.rect.bottom - 6), 2,
            )
        surface.set_clip(prev_clip)


# ── Scrollable rich text (for RulesScreen) ──────────────────────────────

class ScrollableText:
    """Vertically scrollable list of (text, style) lines with word-wrap."""

    STYLES = {
        "h1": {"color": TEXT_GOLD, "bold": True, "size_mult": 1.5, "pad_top": 14, "pad_bottom": 10},
        "h2": {"color": (224, 168, 104), "bold": True, "size_mult": 1.15, "pad_top": 12, "pad_bottom": 4},
        "body": {"color": (236, 220, 192), "bold": False, "size_mult": 1.0, "pad_top": 0, "pad_bottom": 8},
    }

    def __init__(
        self,
        rect: pygame.Rect,
        base_font_name: str | None,
        base_size: int,
    ) -> None:
        """Create an empty scrollable text panel."""
        self.rect = rect
        self._base_font_name = base_font_name
        self._base_size = base_size
        self._fonts: dict[tuple[bool, int, str], pygame.font.Font] = {}
        self.lines: list[tuple[str, str]] = []
        self.scroll = 0
        self._content_height = 0
        self._rendered: list[tuple[pygame.Surface, int, int]] = []

    def _font(self, bold: bool, size: int, text: str = "") -> pygame.font.Font:
        face = "sylfaen" if contains_armenian(text) else (self._base_font_name or "georgia")
        key = (bold, size, face)
        if key not in self._fonts:
            f = pygame.font.SysFont(face, size, bold=bold)
            self._fonts[key] = f
        return self._fonts[key]

    def set_content(self, sections: list[tuple[str, str]]) -> None:
        """Set (text, style) pairs and rebuild wrapped/rendered lines."""
        self.lines = sections
        self.scroll = 0
        self._rebuild()

    def _rebuild(self) -> None:
        self._rendered = []
        y = 10
        max_w = self.rect.width - 24
        for text, style_key in self.lines:
            style = self.STYLES.get(style_key, self.STYLES["body"])
            size = int(self._base_size * style["size_mult"])
            font = self._font(style["bold"], size, text)
            y += style["pad_top"]
            for wrapped_line in _wrap_text(text, font, max_w):
                surf = font.render(wrapped_line, True, style["color"])
                self._rendered.append((surf, 12, y))
                y += surf.get_height() + 2
            y += style["pad_bottom"]
        self._content_height = y

    def handle_event(self, event: pygame.event.Event) -> None:
        """Scroll with mouse wheel when hovering the panel."""
        if event.type == pygame.MOUSEWHEEL:
            mouse_pos = pygame.mouse.get_pos()
            if self.rect.collidepoint(mouse_pos):
                self.scroll -= event.y * 40
                max_scroll = max(0, self._content_height - self.rect.height + 20)
                self.scroll = max(0, min(self.scroll, max_scroll))

    def update(self, dt_ms: int) -> None:
        """No per-frame state needed."""

    def draw(self, surface: pygame.Surface) -> None:
        """Render visible lines clipped to the panel rect."""
        pygame.draw.rect(surface, (46, 32, 20), self.rect)
        pygame.draw.rect(surface, WOOD_LIGHT, self.rect, width=2)
        prev_clip = surface.get_clip()
        surface.set_clip(self.rect)
        for line_surf, lx, ly in self._rendered:
            y = self.rect.top + ly - self.scroll
            if self.rect.top - 30 <= y <= self.rect.bottom + 10:
                surface.blit(line_surf, (self.rect.left + lx, y))
        surface.set_clip(prev_clip)

        # Scrollbar
        max_scroll = max(0, self._content_height - self.rect.height + 20)
        if max_scroll > 0:
            track_h = self.rect.height - 8
            thumb_h = max(24, int(track_h * self.rect.height / (self._content_height + 20)))
            thumb_y = self.rect.top + 4 + int(
                (track_h - thumb_h) * (self.scroll / max_scroll),
            )
            bar_x = self.rect.right - 8
            pygame.draw.rect(surface, (30, 20, 12), (bar_x, self.rect.top + 4, 5, track_h), border_radius=2)
            pygame.draw.rect(surface, WOOD_LIGHT, (bar_x, thumb_y, 5, thumb_h), border_radius=2)


def _wrap_text(text: str, font: pygame.font.Font, max_width: int) -> list[str]:
    """Word-wrap text to fit within max_width pixels."""
    words = text.split(" ")
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if font.size(candidate)[0] <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [""]


# ── Font helpers ─────────────────────────────────────────────────────────

_FONT_CACHE: dict[tuple[str | None, int, bool], pygame.font.Font] = {}


def contains_armenian(text: str) -> bool:
    """Return True if text contains Armenian-script characters."""
    return any(0x0530 <= ord(ch) <= 0x058F for ch in text)


def get_font(
    size: int, bold: bool = False, name: str | None = None, text: str | None = None,
) -> pygame.font.Font:
    """Return a cached pygame Font, auto-picking an Armenian-capable face when needed.

    Georgia has no Armenian glyphs (renders tofu boxes), so when ``text``
    contains Armenian script we switch to Sylfaen, which does.
    """
    if name is None:
        name = "sylfaen" if text and contains_armenian(text) else "georgia"
    key = (name, size, bold)
    if key not in _FONT_CACHE:
        try:
            f = pygame.font.SysFont(name, size, bold=bold)
        except Exception:
            f = pygame.font.Font(None, size)
        _FONT_CACHE[key] = f
    return _FONT_CACHE[key]
