"""Shared ruleset interfaces and partial implementations."""

from __future__ import annotations

import random
from abc import ABC, abstractmethod
from dataclasses import replace
from typing import Callable, Mapping

from nardy.domain.models import (
    BAR_POSITION,
    BOARD_POINT_COUNT,
    OFF_POSITION,
    TOTAL_CHECKERS,
    DiceRoll,
    GameMode,
    GameState,
    Move,
    Player,
    PointState,
    TurnPhase,
    TurnState,
    build_board,
)

RandomDie = Callable[[int, int], int]


class RuleViolationError(ValueError):
    """Raised when a move or transition violates the active rules."""


class Ruleset(ABC):
    """Define the contract shared by all game mode rulesets."""

    mode: GameMode

    @abstractmethod
    def initial_state(self) -> GameState:
        """Build the initial immutable game state."""

    @abstractmethod
    def roll_dice(self) -> DiceRoll:
        """Generate a dice roll for the current turn."""

    @abstractmethod
    def start_turn(self, state: GameState) -> GameState:
        """Transition from waiting for a roll to an active move phase."""

    @abstractmethod
    def legal_moves(self, state: GameState) -> tuple[Move, ...]:
        """Return the list of currently legal moves."""

    @abstractmethod
    def apply_move(self, state: GameState, move: Move) -> GameState:
        """Apply a move and return the resulting state."""

    @abstractmethod
    def end_turn(self, state: GameState) -> GameState:
        """Advance control to the next player."""

    @abstractmethod
    def winner(self, state: GameState) -> Player | None:
        """Return the winning player when the game is finished."""


class BaseRuleset(Ruleset):
    """Provide shared state transitions for concrete backgammon rulesets."""

    mode: GameMode

    def __init__(self, randint: RandomDie | None = None) -> None:
        """Store the RNG dependency for deterministic tests."""
        self._randint = randint or random.randint

    def initial_state(self) -> GameState:
        """Build the initial state using the mode-specific layout."""
        current_player = self.starting_player()
        return GameState(
            mode=self.mode,
            board=build_board(self.initial_layout()),
            current_player=current_player,
            turn=TurnState(player=current_player),
        )

    def roll_dice(self) -> DiceRoll:
        """Generate two dice using the configured RNG."""
        return DiceRoll.from_values(self._randint(1, 6), self._randint(1, 6))

    def start_turn(self, state: GameState) -> GameState:
        """Roll dice and move the state into the active phase."""
        self._ensure_mode(state)
        if state.turn.phase is not TurnPhase.WAITING_FOR_ROLL:
            raise RuleViolationError("The current turn has already started.")
        return replace(state, turn=state.turn.with_roll(self.roll_dice()))

    def legal_moves(self, state: GameState) -> tuple[Move, ...]:
        """Delegate move generation to the shared move generator."""
        from nardy.domain.move_generator import MoveGenerator

        self._ensure_mode(state)
        return MoveGenerator(self).generate(state)

    def apply_move(self, state: GameState, move: Move) -> GameState:
        """Validate and apply a generated move."""
        self._ensure_mode(state)
        self.validate_move(state, move)
        next_state = self._relocate_checker(state, move)
        next_turn = next_state.turn.record_move(move)
        candidate = replace(next_state, turn=next_turn)
        return replace(candidate, winner=self.winner(candidate))

    def end_turn(self, state: GameState) -> GameState:
        """Pass control to the opposing player."""
        self._ensure_mode(state)
        if state.turn.phase is not TurnPhase.TURN_COMPLETE:
            raise RuleViolationError(
                "The turn cannot end before all moves are resolved."
            )
        return state.switch_player()

    def winner(self, state: GameState) -> Player | None:
        """Determine whether a player has borne off all checkers."""
        for player in Player:
            if state.borne_off_for(player) >= TOTAL_CHECKERS:
                return player
        return None

    def validate_move(self, state: GameState, move: Move) -> None:
        """Ensure that a move belongs to the current position."""
        if move.player is not state.current_player:
            raise RuleViolationError("Only the active player may move.")
        if state.turn.phase is not TurnPhase.READY_TO_MOVE:
            raise RuleViolationError("Moves are only allowed after rolling dice.")
        if move not in self.legal_moves(state):
            raise RuleViolationError(
                "The move is not legal in the current position."
            )

    def starting_player(self) -> Player:
        """Return the player who begins a new match."""
        return Player.WHITE

    @abstractmethod
    def initial_layout(self) -> Mapping[int, tuple[Player, int]]:
        """Return the initial board layout indexed from 1 to 24."""

    @abstractmethod
    def direction_for(self, player: Player) -> int:
        """Return movement direction for a player as ``-1`` or ``1``."""

    @abstractmethod
    def can_land_on_point(
        self,
        state: GameState,
        player: Player,
        point_number: int,
    ) -> bool:
        """Return ``True`` when a checker may end a move on the point."""

    def can_bear_off_from(
        self,
        state: GameState,
        player: Player,
        source: int,
        die_value: int,
    ) -> bool:
        """Return ``True`` when a checker may leave the board."""
        if state.bar_for(player) > 0:
            return False
        if not self._all_checkers_in_home(state, player):
            return False
        if source not in self.home_points_for(player):
            return False
        target = source + self.direction_for(player) * die_value
        if 1 <= target <= BOARD_POINT_COUNT:
            return False
        if self._is_exact_bear_off(player, source, die_value):
            return True
        return self._can_bear_off_with_overshoot(state, player, source)

    def _ensure_mode(self, state: GameState) -> None:
        """Protect against mixing states and rulesets."""
        if state.mode is not self.mode:
            raise RuleViolationError("The ruleset does not match the game mode.")

    def _relocate_checker(self, state: GameState, move: Move) -> GameState:
        """Move a checker on the immutable board and update counters."""
        if move.source == BAR_POSITION:
            bar_count = state.bar_for(move.player)
            if bar_count <= 0:
                raise RuleViolationError(
                    "There is no checker for the player on the bar."
                )
            next_state = state.with_bar(move.player, bar_count - 1)
        else:
            source_state = state.point(move.source)
            if source_state.owner is not move.player or source_state.checkers == 0:
                raise RuleViolationError(
                    "The source point has no checker for the player."
                )
            next_state = state.replace_point(
                move.source,
                source_state.remove_checker(move.player),
            )

        if move.bears_off or move.target == OFF_POSITION:
            return next_state.with_borne_off(
                move.player,
                next_state.borne_off_for(move.player) + 1,
            )

        target_state = next_state.point(move.target)
        if target_state.owner not in (None, move.player):
            if target_state.checkers != 1 or not move.captures:
                raise RuleViolationError("Cannot land on a blocked opposing point.")
            next_state = next_state.with_bar(
                target_state.owner,
                next_state.bar_for(target_state.owner) + 1,
            )
            target_state = PointState()

        return next_state.replace_point(
            move.target,
            target_state.add_checker(move.player),
        )

    def home_points_for(self, player: Player) -> range:
        """Return the player's home board points."""
        if self.direction_for(player) < 0:
            return range(1, 7)
        return range(BOARD_POINT_COUNT - 5, BOARD_POINT_COUNT + 1)

    def _all_checkers_in_home(self, state: GameState, player: Player) -> bool:
        """Return ``True`` when all active checkers are in the home board."""
        home_points = set(self.home_points_for(player))
        home_checkers = sum(
            state.point(point).checkers
            for point in home_points
            if state.point(point).owner is player
        )
        return (
            home_checkers + state.borne_off_for(player) >= TOTAL_CHECKERS
            and state.bar_for(player) == 0
        )

    def _is_exact_bear_off(
        self,
        player: Player,
        source: int,
        die_value: int,
    ) -> bool:
        """Return ``True`` for exact die values that bear off from source."""
        if self.direction_for(player) < 0:
            return source == die_value
        return source + die_value == OFF_POSITION

    def _can_bear_off_with_overshoot(
        self,
        state: GameState,
        player: Player,
        source: int,
    ) -> bool:
        """Allow overshoot only from the farthest occupied home point."""
        if self.direction_for(player) < 0:
            higher_points = range(source + 1, 7)
            return not any(
                state.point(point).owner is player
                and state.point(point).checkers > 0
                for point in higher_points
            )
        lower_points = range(BOARD_POINT_COUNT - 5, source)
        return not any(
            state.point(point).owner is player
            and state.point(point).checkers > 0
            for point in lower_points
        )
