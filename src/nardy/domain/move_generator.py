"""Shared move generation scaffolding for both rulesets."""

from __future__ import annotations

from nardy.domain.models import (
    BOARD_POINT_COUNT,
    OFF_POSITION,
    GameState,
    Move,
    TurnPhase,
)
from nardy.domain.rules_base import BaseRuleset


class MoveGenerator:
    """Generate legal move candidates from a state and ruleset hooks."""

    def __init__(self, ruleset: BaseRuleset) -> None:
        """Bind the generator to a concrete ruleset."""
        self._ruleset = ruleset

    def generate(self, state: GameState) -> tuple[Move, ...]:
        """Return move candidates for the current player.

        The generator intentionally keeps the first iteration conservative:
        re-entry from the bar and bearing off are reserved for the next
        implementation step, but the contract and data flow are already in place.
        """
        if (
            state.turn.phase is not TurnPhase.READY_TO_MOVE
            or state.turn.dice is None
        ):
            return ()
        if state.bar_for(state.current_player) > 0:
            return ()

        candidates: list[Move] = []
        for die_value in state.turn.remaining_pips:
            for point_number in range(1, BOARD_POINT_COUNT + 1):
                point = state.point(point_number)
                if (
                    point.owner is not state.current_player
                    or point.checkers == 0
                ):
                    continue

                target = point_number + (
                    self._ruleset.direction_for(state.current_player) * die_value
                )
                if 1 <= target <= BOARD_POINT_COUNT:
                    if not self._ruleset.can_land_on_point(
                        state,
                        state.current_player,
                        target,
                    ):
                        continue
                    target_point = state.point(target)
                    candidates.append(
                        Move(
                            player=state.current_player,
                            source=point_number,
                            target=target,
                            die_value=die_value,
                            captures=(
                                target_point.owner is state.current_player.opponent
                                and target_point.checkers == 1
                            ),
                        )
                    )
                    continue

                if self._ruleset.can_bear_off_from(
                    state,
                    state.current_player,
                    point_number,
                    die_value,
                ):
                    candidates.append(
                        Move(
                            player=state.current_player,
                            source=point_number,
                            target=OFF_POSITION,
                            die_value=die_value,
                            bears_off=True,
                        )
                    )

        return tuple(dict.fromkeys(candidates))
