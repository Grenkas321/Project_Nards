"""Ruleset skeleton for short backgammon."""

from __future__ import annotations

from typing import Mapping

from nardy.domain.models import GameMode, GameState, Player
from nardy.domain.rules_base import BaseRuleset


class ShortNardyRules(BaseRuleset):
    """Partial implementation of the short backgammon rules contract."""

    mode = GameMode.SHORT

    def initial_layout(self) -> Mapping[int, tuple[Player, int]]:
        """Return the classical backgammon starting positions."""
        return {
            24: (Player.WHITE, 2),
            13: (Player.WHITE, 5),
            8: (Player.WHITE, 3),
            6: (Player.WHITE, 5),
            1: (Player.BLACK, 2),
            12: (Player.BLACK, 5),
            17: (Player.BLACK, 3),
            19: (Player.BLACK, 5),
        }

    def direction_for(self, player: Player) -> int:
        """Return the movement direction for a player."""
        return -1 if player is Player.WHITE else 1

    def can_land_on_point(
        self,
        state: GameState,
        player: Player,
        point_number: int,
    ) -> bool:
        """Allow landing on empty, friendly or opposing blot points."""
        point = state.point(point_number)
        return point.owner in (None, player) or point.checkers == 1
