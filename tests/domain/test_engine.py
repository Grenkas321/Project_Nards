"""Tests for the game engine and undo flow."""

from __future__ import annotations

from typing import Callable

from nardy.domain.engine import GameEngine
from nardy.domain.models import GameMode, Player, TurnPhase
from nardy.domain.rules_long import LongNardyRules
from nardy.domain.rules_short import ShortNardyRules


def test_engine_rolls_and_generates_moves() -> None:
    """Rolling dice should switch the turn into the move phase."""
    rules = {
        GameMode.LONG: LongNardyRules(randint=_sequence_randint([3, 4])),
        GameMode.SHORT: ShortNardyRules(randint=_sequence_randint([1, 2])),
    }
    engine = GameEngine(rules)

    state = engine.start_new_game(GameMode.LONG)
    assert state.current_player is Player.WHITE
    assert state.turn.phase is TurnPhase.WAITING_FOR_ROLL

    rolled_state = engine.roll_dice()
    assert rolled_state.turn.dice is not None
    assert rolled_state.turn.phase is TurnPhase.READY_TO_MOVE
    assert rolled_state.turn.legal_moves


def test_engine_undo_restores_previous_snapshot() -> None:
    """Undo should restore the state from before the last mutation."""
    engine = GameEngine(
        {
            GameMode.LONG: LongNardyRules(randint=_sequence_randint([1, 2])),
            GameMode.SHORT: ShortNardyRules(randint=_sequence_randint([1, 2])),
        }
    )
    initial = engine.start_new_game(GameMode.LONG)
    engine.roll_dice()

    restored = engine.undo()
    assert restored == initial


def _sequence_randint(values: list[int]) -> Callable[[int, int], int]:
    """Build a deterministic randint replacement for tests."""
    iterator = iter(values)

    def _randint(_lower: int, _upper: int) -> int:
        return next(iterator)

    return _randint
