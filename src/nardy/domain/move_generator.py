"""Shared move generation scaffolding for both rulesets."""

from __future__ import annotations

from collections.abc import Sequence
from functools import lru_cache

from nardy.domain.models import (
    BAR_POSITION,
    BOARD_POINT_COUNT,
    OFF_POSITION,
    GameState,
    Move,
    Player,
    TurnPhase,
)
from nardy.domain.rules_base import BaseRuleset


class MoveGenerator:
    """Generate legal move candidates from a state and ruleset hooks."""

    def __init__(self, ruleset: BaseRuleset) -> None:
        """Bind the generator to a concrete ruleset."""
        self._ruleset = ruleset

    def generate(self, state: GameState) -> tuple[Move, ...]:
        """Return move candidates for the current player."""
        if (
            state.turn.phase is not TurnPhase.READY_TO_MOVE
            or state.turn.dice is None
        ):
            return ()
        sequences = self._best_sequences(state, state.turn.remaining_pips)
        candidates = [
            sequence[0] for sequence in sequences if sequence
        ]
        return tuple(dict.fromkeys(candidates))

    def _best_sequences(
        self,
        state: GameState,
        remaining_pips: tuple[int, ...],
    ) -> tuple[tuple[Move, ...], ...]:
        """Return all optimal move sequences from the current position."""

        @lru_cache(maxsize=None)
        def _walk(
            branch_state: GameState,
            branch_pips: tuple[int, ...],
        ) -> tuple[tuple[Move, ...], ...]:
            sequences: list[tuple[Move, ...]] = []
            for index, die_value in enumerate(branch_pips):
                if die_value in branch_pips[:index]:
                    continue
                moves = self._moves_for_die(
                    branch_state,
                    branch_state.current_player,
                    die_value,
                )
                if not moves:
                    continue
                next_pips = self._remove_single(branch_pips, index)
                for move in moves:
                    next_state = self._ruleset._relocate_checker(  # noqa: SLF001
                        branch_state,
                        move,
                    )
                    tails = _walk(next_state, next_pips)
                    if not tails:
                        sequences.append((move,))
                        continue
                    for tail in tails:
                        sequences.append((move,) + tail)

            if not sequences:
                return ((),)
            return self._select_best_sequences(sequences)

        return _walk(state, tuple(remaining_pips))

    def _moves_for_die(
        self,
        state: GameState,
        player: Player,
        die_value: int,
    ) -> tuple[Move, ...]:
        """Generate all legal moves for one die value."""
        if state.bar_for(player) > 0:
            return self._bar_reentry_moves(state, player, die_value)

        direction = self._ruleset.direction_for(player)
        candidates: list[Move] = []
        for point_number in range(1, BOARD_POINT_COUNT + 1):
            point = state.point(point_number)
            if point.owner is not player or point.checkers == 0:
                continue
            target = point_number + direction * die_value
            if 1 <= target <= BOARD_POINT_COUNT:
                if not self._ruleset.can_land_on_point(
                    state,
                    player,
                    target,
                ):
                    continue
                target_point = state.point(target)
                candidates.append(
                    Move(
                        player=player,
                        source=point_number,
                        target=target,
                        die_value=die_value,
                        captures=(
                            target_point.owner is player.opponent
                            and target_point.checkers == 1
                        ),
                    )
                )
                continue
            if self._ruleset.can_bear_off_from(
                state,
                player,
                point_number,
                die_value,
            ):
                candidates.append(
                    Move(
                        player=player,
                        source=point_number,
                        target=OFF_POSITION,
                        die_value=die_value,
                        bears_off=True,
                    )
                )
        return tuple(candidates)

    def _bar_reentry_moves(
        self,
        state: GameState,
        player: Player,
        die_value: int,
    ) -> tuple[Move, ...]:
        """Generate a re-entry move from the bar when possible."""
        if self._ruleset.direction_for(player) < 0:
            target = BOARD_POINT_COUNT + 1 - die_value
        else:
            target = die_value
        if not self._ruleset.can_land_on_point(state, player, target):
            return ()
        target_point = state.point(target)
        return (
            Move(
                player=player,
                source=BAR_POSITION,
                target=target,
                die_value=die_value,
                captures=(
                    target_point.owner is player.opponent
                    and target_point.checkers == 1
                ),
            ),
        )

    @staticmethod
    def _remove_single(values: Sequence[int], index: int) -> tuple[int, ...]:
        """Return a tuple with one value removed by position."""
        values_list = list(values)
        del values_list[index]
        return tuple(values_list)

    @staticmethod
    def _select_best_sequences(
        sequences: Sequence[tuple[Move, ...]],
    ) -> tuple[tuple[Move, ...], ...]:
        """Filter move sequences by mandatory maximum dice usage rules."""
        max_steps = max(len(sequence) for sequence in sequences)
        longest = [
            sequence for sequence in sequences if len(sequence) == max_steps
        ]
        max_pips = max(
            sum(move.die_value for move in sequence)
            for sequence in longest
        )
        best = [
            sequence
            for sequence in longest
            if sum(move.die_value for move in sequence) == max_pips
        ]
        return tuple(best)
