"""Ruleset for long backgammon with head restriction: only one checker from head per turn, except first turn double."""

from __future__ import annotations

from typing import Mapping

from nardy.domain.models import BOARD_POINT_COUNT, GameMode, GameState, Move, Player
from nardy.domain.rules_base import BaseRuleset


class LongNardyRules(BaseRuleset):
    """Long backgammon rules with head restriction.

    In long backgammon:
    - All checkers start on the opposite edges (White on point 24, Black on point 12).
    - Movement is counter-clockwise for White (24 → 1) and for Black (12 → 11 → … → 1 → 24 → … → 13).
    - No capturing; landing on an opponent's point is forbidden.
    - Bearing off requires all checkers to be in the home board (points 1-6 for White, 13-18 for Black).
    - Head restriction: only one checker may leave the head (starting point) per turn,
      except on the very first turn of the game when a double is rolled – then White may take two checkers.
    """

    mode = GameMode.LONG

    def __init__(self, randint=None):
        """Initialise the ruleset and reset first-turn flags."""
        super().__init__(randint)
        self._first_turn_started = True   # будет выставлен в False при initial_state
        self._first_turn_white_double_allowed = False

    def initial_state(self) -> GameState:
        """Create the initial game state and reset first-turn flags."""
        self._first_turn_started = True
        self._first_turn_white_double_allowed = False
        return super().initial_state()

    def start_turn(self, state: GameState) -> GameState:
        """Start a turn: detect if this is the very first turn of the game."""
        # Если это первый ход партии (ещё не было ни одного применённого хода)
        # и текущий игрок белые, то разрешаем дубль для двух шашек с головы.
        if self._first_turn_started and state.current_player is Player.WHITE:
            # Сразу помечаем, что первый ход начался, но ещё не завершён
            self._first_turn_white_double_allowed = True
        return super().start_turn(state)

    def apply_move(self, state: GameState, move: Move) -> GameState:
        """Apply a move and update first-turn flags."""
        # После первого применённого хода запрещаем два хода с головы
        if self._first_turn_started:
            self._first_turn_started = False
            self._first_turn_white_double_allowed = False
        return super().apply_move(state, move)

    def legal_moves(self, state: GameState) -> tuple[Move, ...]:
        """Return all legal moves, respecting head restriction.

        Head restriction:
        - Normally, only one checker may be moved from the head (starting point) per turn.
        - Exception: on the very first turn of the game, if the current player is White
          and a double is rolled, two checkers may leave the head.
        """
        moves = super().legal_moves(state)
        head_source = 24 if state.current_player is Player.WHITE else 12
        head_moves_done = sum(1 for m in state.turn.moves if m.source == head_source)

        # Разрешаем две шашки с головы только в самом первом ходу белых при дубле
        if (self._first_turn_white_double_allowed and
            state.current_player is Player.WHITE and
            state.turn.dice and state.turn.dice.is_double):
            max_head = 2
        else:
            max_head = 1

        if head_moves_done >= max_head:
            moves = tuple(m for m in moves if m.source != head_source)
        return moves

    def initial_layout(self) -> Mapping[int, tuple[Player, int]]:
        """Return the starting board layout for long backgammon.

        White starts with 15 checkers on point 24.
        Black starts with 15 checkers on point 12.
        """
        return {
            24: (Player.WHITE, 15),
            12: (Player.BLACK, 15),
        }

    def direction_for(self, player: Player) -> int:
        """Movement direction: -1 means decreasing point numbers (counter-clockwise)."""
        return -1

    def target_for(self, player: Player, source: int, die_value: int) -> int | None:
        """Return the target point after moving a checker along the player's movement path.

        If the move would go beyond the board (bearing off), returns None.
        """
        path = self._path_for(player)
        try:
            idx = path.index(source)
        except ValueError:
            return None
        target_idx = idx + die_value
        if target_idx >= BOARD_POINT_COUNT:
            return None
        return path[target_idx]

    def home_points_for(self, player: Player) -> range:
        """Return the home board points for the player.

        For White home points are 1-6, for Black home points are 13-18.
        """
        if player is Player.WHITE:
            return range(1, 7)
        return range(13, 19)

    def _is_exact_bear_off(self, player: Player, source: int, die_value: int) -> bool:
        """Check if the die value exactly bears off a checker from the source point."""
        path = self._path_for(player)
        return path.index(source) + die_value == BOARD_POINT_COUNT

    def _can_bear_off_with_overshoot(self, state: GameState, player: Player, source: int) -> bool:
        """Allow overshoot only from the farthest occupied home point."""
        path = self._path_for(player)
        source_idx = path.index(source)
        # Check if any home point closer to the bear-off edge is occupied
        return not any(
            state.point(point).owner is player and state.point(point).checkers > 0
            for point in self.home_points_for(player)
            if path.index(point) < source_idx
        )

    def can_land_on_point(self, state: GameState, player: Player, point_number: int) -> bool:
        """In long backgammon, landing on empty or friendly points is allowed."""
        point = state.point(point_number)
        return point.owner in (None, player)

    @staticmethod
    def _path_for(player: Player) -> tuple[int, ...]:
        """Return the ordered list of points a checker visits during movement.

        For White: 24,23,...,1
        For Black: 12,11,...,1,24,23,...,13
        """
        if player is Player.WHITE:
            return tuple(range(24, 0, -1))
        return tuple(range(12, 0, -1)) + tuple(range(24, 12, -1))
