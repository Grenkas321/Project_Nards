"""Ruleset skeleton for long backgammon."""

from __future__ import annotations

from typing import Mapping

from nardy.domain.models import GameMode, GameState, Player
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
        return -1 if player is Player.WHITE else 1

    def can_land_on_point(
        self,
        state: GameState,
        player: Player,
        point_number: int,
    ) -> bool:
        """Allow landing only on empty or friendly points."""
        point = state.point(point_number)
        return point.owner in (None, player)
