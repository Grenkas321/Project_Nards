"""Sound effects via pygame.mixer — cross-platform, no threading needed."""

from __future__ import annotations

from pathlib import Path

import pygame

_ASSETS = Path(__file__).with_name("assets")
_sounds: dict[str, pygame.mixer.Sound] = {}
_enabled = False


def init_sounds() -> None:
    """Initialize the mixer and pre-load all sound effects."""
    global _enabled
    try:
        if not pygame.mixer.get_init():
            pygame.mixer.init()
        for name in ("dice_hit", "dice_roll", "dice_land", "checker_place"):
            path = _ASSETS / f"{name}.wav"
            if path.exists():
                _sounds[name] = pygame.mixer.Sound(str(path))
        _enabled = True
    except Exception:
        _enabled = False


def _play(name: str) -> None:
    if not _enabled:
        return
    sound = _sounds.get(name)
    if sound is not None:
        sound.play()


def play_dice_hit() -> None:
    """Single dice bounce."""
    _play("dice_hit")


def play_dice_roll() -> None:
    """Full dice rolling sequence."""
    _play("dice_roll")


def play_dice_land() -> None:
    """Dice settling thud."""
    _play("dice_land")


def play_checker_place() -> None:
    """Checker placed on board."""
    _play("checker_place")
