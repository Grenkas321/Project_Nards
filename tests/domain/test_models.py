"""Tests for core domain models."""

from __future__ import annotations

import pytest

from nardy.domain.models import (
    DiceRoll,
    GameMode,
    GameState,
    Player,
    PointState,
    TurnState,
)


def test_player_exposes_opponent() -> None:
    """Players should be able to reference their opponent."""
    assert Player.WHITE.opponent is Player.BLACK
    assert Player.BLACK.opponent is Player.WHITE


def test_dice_roll_expands_doubles() -> None:
    """Double rolls should expose four pips."""
    roll = DiceRoll.from_values(4, 4)
    assert roll.is_double is True
    assert roll.pips == (4, 4, 4, 4)


def test_game_state_requires_turn_player_to_match_current_player() -> None:
    """The active turn should belong to the active player."""
    with pytest.raises(ValueError):
        GameState(
            mode=GameMode.LONG,
            board=tuple(PointState() for _ in range(24)),
            current_player=Player.WHITE,
            turn=TurnState(player=Player.BLACK),
        )
