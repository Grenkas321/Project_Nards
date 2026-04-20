"""High-level game engine coordinating rules, moves and undo."""

from __future__ import annotations

from dataclasses import replace
from typing import Mapping

from nardy.domain.models import GameMode, GameState, Move, TurnPhase
from nardy.domain.move_generator import MoveGenerator
from nardy.domain.rules_long import LongNardyRules
from nardy.domain.rules_base import Ruleset
from nardy.domain.rules_short import ShortNardyRules
from nardy.domain.undo import SnapshotStore


class GameEngine:
    """Coordinate immutable state transitions for an active match."""

    def __init__(self, rules_by_mode: Mapping[GameMode, Ruleset]) -> None:
        """Bind the engine to a registry of rulesets."""
        self._rules_by_mode = dict(rules_by_mode)
        self._history = SnapshotStore()
        self._state: GameState | None = None

    @property
    def state(self) -> GameState:
        """Return the current game state."""
        return self._require_state()

    def start_new_game(self, mode: GameMode) -> GameState:
        """Create a fresh state for the selected mode."""
        rules = self._rules(mode)
        self._history.clear()
        self._state = self._refresh_turn_state(rules.initial_state())
        return self._state

    def roll_dice(self) -> GameState:
        """Start the active turn by rolling two dice."""
        state = self._require_state()
        rules = self._rules(state.mode)
        self._history.push(state)
        self._state = self._refresh_turn_state(rules.start_turn(state))
        return self._state

    def available_moves(self) -> tuple[Move, ...]:
        """Expose the currently cached legal moves."""
        return self._require_state().turn.legal_moves

    def apply_move(self, move: Move) -> GameState:
        """Apply a legal move and refresh the move list."""
        state = self._require_state()
        rules = self._rules(state.mode)
        self._history.push(state)
        self._state = self._refresh_turn_state(rules.apply_move(state, move))
        return self._state

    def end_turn(self) -> GameState:
        """Finish the current turn and hand control to the opponent."""
        state = self._require_state()
        rules = self._rules(state.mode)
        self._history.push(state)
        self._state = self._refresh_turn_state(rules.end_turn(state))
        return self._state

    def undo(self) -> GameState:
        """Restore the previous snapshot."""
        self._state = self._history.pop()
        return self._state

    def can_undo(self) -> bool:
        """Return ``True`` when undo is available."""
        return self._history.can_undo()

    def _refresh_turn_state(self, state: GameState) -> GameState:
        """Recompute legal moves for the current state."""
        rules = self._rules(state.mode)
        generator = MoveGenerator(rules)
        moves = generator.generate(state)
        turn = state.turn.with_legal_moves(moves)
        if (
            turn.phase is TurnPhase.READY_TO_MOVE
            and turn.remaining_pips
            and not moves
        ):
            turn = turn.finish()
        return replace(state, turn=turn, winner=rules.winner(state))

    def _require_state(self) -> GameState:
        """Return the current state or fail when no game exists."""
        if self._state is None:
            raise RuntimeError("Start a game before using the engine.")
        return self._state

    def _rules(self, mode: GameMode) -> Ruleset:
        """Return the ruleset registered for a mode."""
        try:
            return self._rules_by_mode[mode]
        except KeyError as exc:
            raise RuntimeError(
                f"No rules registered for mode {mode.value!r}."
            ) from exc


def build_default_engine() -> GameEngine:
    """Create the standard engine with both supported rulesets."""
    return GameEngine(
        {
            GameMode.LONG: LongNardyRules(),
            GameMode.SHORT: ShortNardyRules(),
        }
    )
