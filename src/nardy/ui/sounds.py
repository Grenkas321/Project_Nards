"""Sound effects from real backgammon recording."""

from __future__ import annotations

import sys
import threading
from pathlib import Path

_ASSETS = Path(__file__).with_name("assets")


def _load(name: str) -> bytes:
    """Load a WAV file from assets directory."""
    path = _ASSETS / name
    if path.exists():
        return path.read_bytes()
    return b""


_DICE_HIT = _load("dice_hit.wav")
_DICE_ROLL = _load("dice_roll.wav")
_DICE_LAND = _load("dice_land.wav")
_CHECKER_PLACE = _load("checker_place.wav")


def play_dice_hit() -> None:
    """Single dice bounce."""
    _play_async(_DICE_HIT)


def play_dice_roll() -> None:
    """Full dice rolling sequence (use at animation start)."""
    _play_async(_DICE_ROLL)


def play_dice_land() -> None:
    """Dice settling thud."""
    _play_async(_DICE_LAND)


def play_checker_place() -> None:
    """Checker placed on board."""
    _play_async(_CHECKER_PLACE)


def _play_async(wav_data: bytes) -> None:
    if sys.platform != "win32" or not wav_data:
        return
    threading.Thread(target=_play, args=(wav_data,), daemon=True).start()


def _play(wav_data: bytes) -> None:
    try:
        import winsound
        winsound.PlaySound(wav_data, winsound.SND_MEMORY | winsound.SND_NOSTOP)
    except Exception:
        pass
