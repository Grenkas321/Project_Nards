"""Ruleset skeleton for long backgammon."""

from __future__ import annotations

from typing import Mapping

from nardy.domain.models import (
    BAR_POSITION,
    BOARD_POINT_COUNT,
    GameMode,
    GameState,
    Move,
    Player,
)
from nardy.domain.rules_base import BaseRuleset


class LongNardyRules(BaseRuleset):
    """Partial implementation of the long backgammon rules contract."""

    mode = GameMode.LONG

    def initial_layout(self) -> Mapping[int, tuple[Player, int]]:
        """Return the starting positions for long backgammon."""
        return {
            24: (Player.WHITE, 15),
            12: (Player.BLACK, 15),
        }

    def direction_for(self, player: Player) -> int:
        """Return the movement direction for a player."""
        del player
        return -1

    def target_for(self, player: Player, source: int, die_value: int) -> int | None:
        """Return target point along the player's circular movement path."""
        path = self._path_for(player)
        index = path.index(source) + die_value
        if index >= BOARD_POINT_COUNT:
            return None
        return path[index]

    def home_points_for(self, player: Player) -> range:
        """Return the player's home board points."""
        if player is Player.WHITE:
            return range(1, 7)
        return range(13, 19)

    def _is_exact_bear_off(
        self,
        player: Player,
        source: int,
        die_value: int,
    ) -> bool:
        """Return ``True`` when die reaches the end of the movement path."""
        path = self._path_for(player)
        return path.index(source) + die_value == BOARD_POINT_COUNT

    def _can_bear_off_with_overshoot(
        self,
        state: GameState,
        player: Player,
        source: int,
    ) -> bool:
        """Allow overshoot only from the farthest occupied home point."""
        path = self._path_for(player)
        source_index = path.index(source)
        return not any(
            state.point(point).owner is player and state.point(point).checkers > 0
            for point in self.home_points_for(player)
            if path.index(point) < source_index
        )

    @staticmethod
    def head_point_for(player: Player) -> int:
        """Return the head (starting) point for a player."""
        return 24 if player is Player.WHITE else 12

    def max_head_departures(self, state: GameState) -> int:
        """Return max checkers that may leave head this turn."""
        if state.turn.dice is None:
            return 1
        is_first_turn = state.turn_number <= 2
        if is_first_turn and state.turn.dice.is_double:
            return 2
        return 1

    def is_head_departure(self, move: Move) -> bool:
        """Return True if this move leaves the head point."""
        return move.source == self.head_point_for(move.player)

    def can_land_on_point(
        self,
        state: GameState,
        player: Player,
        point_number: int,
    ) -> bool:
        """Allow landing only on empty or friendly points."""
        point = state.point(point_number)
        return point.owner in (None, player)

    def post_validate_landing(
        self,
        state: GameState,
        player: Player,
        source: int,
        target: int,
    ) -> bool:
        """Forbid moves that create 6+ consecutive blocking points."""
        return not self._would_create_illegal_prime(state, player, source, target)

    def _would_create_illegal_prime(
        self,
        state: GameState,
        player: Player,
        source: int,
        target: int,
    ) -> bool:
        """Return True if landing creates 6+ consecutive blocking points."""
        opponent = player.opponent
        opponent_path = self._path_for(opponent)

        owned: set[int] = set()
        for pt in range(1, BOARD_POINT_COUNT + 1):
            ps = state.point(pt)
            if ps.owner is player and ps.checkers > 0:
                owned.add(pt)

        if source != BAR_POSITION:
            ps = state.point(source)
            if ps.owner is player and ps.checkers == 1:
                owned.discard(source)

        owned.add(target)

        runs: list[tuple[int, int]] = []
        start = -1
        length = 0
        for i, pt in enumerate(opponent_path):
            if pt in owned:
                if length == 0:
                    start = i
                length += 1
            else:
                if length >= 6:
                    runs.append((start, start + length - 1))
                length = 0
        if length >= 6:
            runs.append((start, start + length - 1))

        if not runs:
            return False

        # Wall of 6+ is allowed ONLY if opponent has at least one
        # checker in their home board (bearing-off zone)
        home = set(self.home_points_for(opponent))
        opponent_in_home = any(
            state.point(pt).owner is opponent and state.point(pt).checkers > 0
            for pt in home
        )
        if opponent_in_home:
            return False

        return True

    @staticmethod
    def _path_for(player: Player) -> tuple[int, ...]:
        """Return board points in movement order for the player."""
        if player is Player.WHITE:
            return tuple(range(24, 0, -1))
        return tuple(range(12, 0, -1)) + tuple(range(24, 12, -1))
