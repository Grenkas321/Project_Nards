"""Pygame victory screen shown when a game ends."""

from __future__ import annotations

import math
import random
from collections.abc import Callable

import pygame

from nardy.app.presentation import VictoryScreenData
from nardy.i18n import Localizer, gettext_noop as _
from nardy.ui.menu_screens import _BaseMenuScreen
from nardy.ui.runtime import TEXT_GOLD, get_font
from nardy.ui.textures import checker_photo


class VictoryScreen(_BaseMenuScreen):
    """Celebratory panel with the result and rematch / menu actions."""

    def __init__(
        self,
        localizer: Localizer,
        data: VictoryScreenData,
        on_back_to_menu: Callable[[], None],
        on_rematch: Callable[[], None] | None = None,
    ) -> None:
        """Create victory screen content."""
        super().__init__(localizer)
        t = self._translate
        self._data = data
        if on_rematch is not None:
            self._add_button(t(_("Play again")), on_rematch, 0.5, 0.60, size=22, boxed=True)
            self._add_button(t(_("Back to menu")), on_back_to_menu, 0.5, 0.71, size=17)
        else:
            self._add_button(t(_("Back to menu")), on_back_to_menu, 0.5, 0.62, size=22, boxed=True)

        # Falling checker confetti
        rng = random.Random()
        self._confetti = [
            {
                "x": rng.uniform(0.02, 0.98), "y": rng.uniform(-1.2, -0.05),
                "speed": rng.uniform(0.05, 0.14), "size": rng.randint(18, 34),
                "white": rng.random() < 0.5, "sway": rng.uniform(0, math.tau),
            }
            for _ in range(26)
        ]

    def layout(self, size: tuple[int, int]) -> None:
        """Position the buttons."""
        self._reposition_buttons(size)

    def update(self, dt_ms: int) -> None:
        """Advance the confetti fall."""
        dt = dt_ms / 1000.0
        for p in self._confetti:
            p["y"] += p["speed"] * dt * 4
            p["sway"] += dt * 2
            if p["y"] > 1.15:
                p["y"] = -0.15
                p["x"] = random.uniform(0.02, 0.98)

    def draw(self, surface: pygame.Surface) -> None:
        """Draw background, confetti, result card, buttons."""
        size = surface.get_size()
        self._ensure_bg(size)
        if self._bg is not None:
            surface.blit(self._bg, (0, 0))
        else:
            surface.fill((26, 15, 8))
        self._maybe_layout(size)

        w, h = size
        for p in self._confetti:
            px = int(p["x"] * w + math.sin(p["sway"]) * 14)
            py = int(p["y"] * h)
            ch = checker_photo(p["size"], p["white"])
            surface.blit(ch, ch.get_rect(center=(px, py)))

        card = pygame.Rect(0, 0, min(520, int(w * 0.55)), int(h * 0.52))
        card.center = (w // 2, int(h * 0.52))
        self._draw_card(surface, card, alpha=195)

        self._draw_title(surface, self._data.title, rely=0.33, size=44)
        font = get_font(20, text=self._data.summary)
        summary = font.render(self._data.summary, True, TEXT_GOLD)
        surface.blit(summary, summary.get_rect(center=(w // 2, int(h * 0.475))))

        for btn in self._buttons:
            btn.draw(surface)
