"""AI opponent for backgammon with four difficulty levels."""

from __future__ import annotations

import random
from dataclasses import replace
from typing import Literal

from nardy.domain.models import (
    BOARD_POINT_COUNT,
    TOTAL_CHECKERS,
    GameMode,
    GameState,
    Move,
    Player,
    TurnPhase,
)
from nardy.domain.move_generator import MoveGenerator
from nardy.domain.rules_base import BaseRuleset
from nardy.domain.rules_long import LongNardyRules
from nardy.domain.rules_short import ShortNardyRules

Difficulty = Literal["easy", "medium", "hard", "pro"]


class NardyAI:
    """Select moves for the AI player at a given difficulty."""

    def __init__(self, difficulty: Difficulty = "medium") -> None:
        """Store difficulty setting."""
        self._difficulty = difficulty

    @property
    def difficulty(self) -> Difficulty:
        """Return current difficulty."""
        return self._difficulty

    def choose_moves(self, state: GameState, rules: BaseRuleset) -> list[Move]:
        """Return a full sequence of moves for the current turn."""
        if state.turn.phase is not TurnPhase.READY_TO_MOVE:
            return []

        if self._difficulty == "easy":
            return self._play_random(state, rules)
        if self._difficulty == "medium":
            return self._play_greedy(state, rules)
        return self._play_expectimax(state, rules)

    def _play_random(self, state: GameState, rules: BaseRuleset) -> list[Move]:
        """Pick random legal moves until turn ends."""
        moves_made: list[Move] = []
        current = state
        while current.turn.phase is TurnPhase.READY_TO_MOVE:
            legal = rules.legal_moves(current)
            if not legal:
                break
            move = random.choice(legal)
            current = rules.apply_move(current, move)
            moves_made.append(move)
        return moves_made

    def _play_greedy(self, state: GameState, rules: BaseRuleset) -> list[Move]:
        """Pick the move sequence that maximises position evaluation."""
        sequences = self._generate_all_sequences(state, rules)
        if not sequences:
            return []
        player = state.current_player
        best = max(sequences, key=lambda seq: _evaluate(seq[-1][1], player))
        return [move for move, _ in best]

    def _play_expectimax(self, state: GameState, rules: BaseRuleset) -> list[Move]:
        """Expectimax search — evaluate opponent's likely responses."""
        sequences = self._generate_all_sequences(state, rules)
        if not sequences:
            return []

        player = state.current_player
        depth = 3 if self._difficulty == "pro" else 2

        best_score = float("-inf")
        best_seq: list[tuple[Move, GameState]] = []

        for seq in sequences:
            final_state = seq[-1][1]
            score = _evaluate(final_state, player)
            if depth >= 2:
                score -= _opponent_response_score(final_state, rules, player) * 0.4
            if depth >= 3:
                score += _second_look(final_state, rules, player) * 0.15
            if score > best_score:
                best_score = score
                best_seq = seq

        return [move for move, _ in best_seq]

    def _generate_all_sequences(
        self,
        state: GameState,
        rules: BaseRuleset,
    ) -> list[list[tuple[Move, GameState]]]:
        """Generate all possible move sequences from current position."""
        results: list[list[tuple[Move, GameState]]] = []
        self._walk(state, rules, [], results)
        return results

    def _walk(
        self,
        state: GameState,
        rules: BaseRuleset,
        path: list[tuple[Move, GameState]],
        results: list[list[tuple[Move, GameState]]],
    ) -> None:
        """Recursive walk of all move sequences."""
        if state.turn.phase is not TurnPhase.READY_TO_MOVE:
            if path:
                results.append(list(path))
            return

        legal = rules.legal_moves(state)
        if not legal:
            if path:
                results.append(list(path))
            return

        seen_targets: set[tuple[int, int]] = set()
        for move in legal:
            key = (move.source, move.target)
            if key in seen_targets:
                continue
            seen_targets.add(key)
            try:
                next_state = rules.apply_move(state, move)
            except Exception:
                continue
            path.append((move, next_state))
            self._walk(next_state, rules, path, results)
            path.pop()


def _evaluate(state: GameState, player: Player) -> float:
    """Evaluate board position for a player. Higher is better."""
    score = 0.0
    opponent = player.opponent
    rules = _get_rules(state.mode)

    # Borne off — biggest reward
    score += state.borne_off_for(player) * 12.0
    score -= state.borne_off_for(opponent) * 8.0

    # Winner check
    if state.borne_off_for(player) >= TOTAL_CHECKERS:
        return 1000.0
    if state.borne_off_for(opponent) >= TOTAL_CHECKERS:
        return -1000.0

    # Bar penalty
    score -= state.bar_for(player) * 18.0
    score += state.bar_for(opponent) * 12.0

    # Board position analysis
    player_path = _path_for(player, state.mode)
    opponent_path = _path_for(opponent, state.mode)

    home_pts = set(rules.home_points_for(player))
    home_checkers = 0
    primes = 0
    prev_owned = False

    for i, pt in enumerate(player_path):
        ps = state.point(pt)
        if ps.owner is player and ps.checkers > 0:
            # Distance bonus — further along the path is better
            score += i * 0.3

            # Home board bonus
            if pt in home_pts:
                home_checkers += ps.checkers
                score += ps.checkers * 3.0

            # Prime detection (consecutive owned points)
            if prev_owned:
                primes += 1
                score += 2.5
            prev_owned = True

            # Stack penalty — too many on one point is wasteful
            if ps.checkers > 3:
                score -= (ps.checkers - 3) * 1.5
        else:
            prev_owned = False

        # Opponent blots (short nardy only)
        if state.mode is GameMode.SHORT:
            if ps.owner is opponent and ps.checkers == 1:
                score += 2.0

    score += home_checkers * 1.5

    return score


def _opponent_response_score(
    state: GameState,
    rules: BaseRuleset,
    my_player: Player,
) -> float:
    """Estimate opponent's best response (average over common rolls)."""
    opponent = my_player.opponent
    if state.current_player is not opponent:
        return 0.0

    sample_rolls = [(1, 2), (3, 4), (5, 6), (1, 1), (6, 6)]
    total = 0.0
    count = 0

    from nardy.domain.models import DiceRoll

    for d1, d2 in sample_rolls:
        try:
            dice = DiceRoll.from_values(d1, d2)
            rolled = replace(
                state,
                turn=state.turn.with_roll(dice),
            )
            rolled_with_moves = replace(
                rolled,
                turn=rolled.turn.with_legal_moves(
                    tuple(MoveGenerator(rules).generate(rolled))
                ),
            )
            legal = rolled_with_moves.turn.legal_moves
            if not legal:
                continue

            best = float("-inf")
            for move in legal:
                try:
                    ns = rules.apply_move(rolled_with_moves, move)
                    val = _evaluate(ns, opponent)
                    if val > best:
                        best = val
                except Exception:
                    continue
            if best > float("-inf"):
                total += best
                count += 1
        except Exception:
            continue

    return total / max(count, 1)


def _second_look(
    state: GameState,
    rules: BaseRuleset,
    my_player: Player,
) -> float:
    """Shallow second-ply evaluation for pro difficulty."""
    if state.current_player is my_player:
        return 0.0
    return _evaluate(state, my_player) * 0.5


def _get_rules(mode: GameMode) -> BaseRuleset:
    """Return ruleset instance for mode."""
    if mode is GameMode.LONG:
        return LongNardyRules()
    return ShortNardyRules()


def _path_for(player: Player, mode: GameMode) -> tuple[int, ...]:
    """Return movement path for player."""
    if mode is GameMode.LONG:
        return LongNardyRules._path_for(player)
    if player is Player.WHITE:
        return tuple(range(24, 0, -1))
    return tuple(range(1, BOARD_POINT_COUNT + 1))
