"""Gameplay-focused unit tests for long and short nardy rules."""

from __future__ import annotations

from dataclasses import replace

import pytest

from nardy.domain.engine import GameEngine
from nardy.domain.models import (
    DiceRoll,
    GameMode,
    GameState,
    Move,
    OFF_POSITION,
    Player,
    PointState,
    TurnPhase,
    TurnState,
    build_board,
)
from nardy.domain.rules_base import RuleViolationError
from nardy.domain.rules_long import LongNardyRules
from nardy.domain.rules_short import ShortNardyRules


def test_long_mode_initial_layout_matches_classic_head_start() -> None:
    """Long mode should place each side on its starting edge."""
    state = LongNardyRules().initial_state()
    assert state.point(24).owner is Player.WHITE
    assert state.point(24).checkers == 15
    assert state.point(12).owner is Player.BLACK
    assert state.point(12).checkers == 15


def test_short_mode_initial_layout_matches_backgammon() -> None:
    """Short mode should provide the standard backgammon setup."""
    state = ShortNardyRules().initial_state()
    assert state.point(24).checkers == 2
    assert state.point(13).checkers == 5
    assert state.point(8).checkers == 3
    assert state.point(6).checkers == 5
    assert state.point(1).owner is Player.BLACK


def test_short_mode_capture_moves_checker_to_bar() -> None:
    """Landing on a blot should capture and move the checker to the bar."""
    rules = ShortNardyRules()
    state = _ready_state(
        mode=GameMode.SHORT,
        player=Player.WHITE,
        layout={8: (Player.WHITE, 1), 6: (Player.BLACK, 1)},
        remaining_pips=(2,),
    )

    move = next(move for move in rules.legal_moves(state) if move.target == 6)
    after = rules.apply_move(state, move)

    assert move.captures is True
    assert after.point(6).owner is Player.WHITE
    assert after.point(6).checkers == 1
    assert after.bar_for(Player.BLACK) == 1


def test_short_mode_forbids_move_to_closed_point() -> None:
    """A point with two enemy checkers should be blocked."""
    rules = ShortNardyRules()
    state = _ready_state(
        mode=GameMode.SHORT,
        player=Player.WHITE,
        layout={8: (Player.WHITE, 1), 6: (Player.BLACK, 2)},
        remaining_pips=(2,),
    )

    legal_targets = {move.target for move in rules.legal_moves(state)}
    assert 6 not in legal_targets


def test_long_mode_forbids_landing_on_enemy_point() -> None:
    """In long nardy there is no capture and no landing on enemy points."""
    rules = LongNardyRules()
    state = _ready_state(
        mode=GameMode.LONG,
        player=Player.WHITE,
        layout={8: (Player.WHITE, 1), 6: (Player.BLACK, 1)},
        remaining_pips=(2,),
    )

    legal_targets = {move.target for move in rules.legal_moves(state)}
    assert 6 not in legal_targets


def test_rules_reject_wrong_mode_state() -> None:
    """Ruleset should reject states created for another game mode."""
    rules = LongNardyRules()
    state = ShortNardyRules().initial_state()

    with pytest.raises(RuleViolationError, match="does not match"):
        rules.legal_moves(state)


def test_rules_reject_starting_already_started_turn() -> None:
    """A turn cannot be rolled twice."""
    rules = LongNardyRules()
    state = _ready_state(
        mode=GameMode.LONG,
        player=Player.WHITE,
        layout={24: (Player.WHITE, 15)},
        remaining_pips=(1,),
    )

    with pytest.raises(RuleViolationError, match="already started"):
        rules.start_turn(state)


def test_rules_reject_ending_unfinished_turn() -> None:
    """A player cannot end a turn while moves remain unresolved."""
    rules = LongNardyRules()
    state = rules.initial_state()

    with pytest.raises(RuleViolationError, match="cannot end"):
        rules.end_turn(state)


def test_rules_reject_inactive_player_move() -> None:
    """Only the current player may move."""
    rules = LongNardyRules()
    state = _ready_state(
        mode=GameMode.LONG,
        player=Player.WHITE,
        layout={24: (Player.WHITE, 15)},
        remaining_pips=(1,),
    )
    move = Move(Player.BLACK, 12, 11, 1)

    with pytest.raises(RuleViolationError, match="active player"):
        rules.validate_move(state, move)


def test_rules_reject_move_before_roll() -> None:
    """Moves are forbidden before dice are rolled."""
    rules = LongNardyRules()
    state = rules.initial_state()
    move = Move(Player.WHITE, 24, 23, 1)

    with pytest.raises(RuleViolationError, match="after rolling"):
        rules.validate_move(state, move)


def test_rules_reject_move_not_in_current_legal_set() -> None:
    """Move must match currently generated legal moves."""
    rules = LongNardyRules()
    state = _ready_state(
        mode=GameMode.LONG,
        player=Player.WHITE,
        layout={24: (Player.WHITE, 15)},
        remaining_pips=(1,),
    )
    move = Move(Player.WHITE, 24, 22, 2)

    with pytest.raises(RuleViolationError, match="not legal"):
        rules.validate_move(state, move)


def test_rules_reject_relocation_from_empty_bar() -> None:
    """Private relocation guard should reject missing bar checkers."""
    rules = ShortNardyRules()
    state = _ready_state(
        mode=GameMode.SHORT,
        player=Player.WHITE,
        layout={24: (Player.WHITE, 1)},
        remaining_pips=(1,),
    )
    move = Move(Player.WHITE, 0, 24, 1)

    with pytest.raises(RuleViolationError, match="bar"):
        rules._relocate_checker(state, move)


def test_rules_reject_relocation_from_empty_point() -> None:
    """Private relocation guard should reject empty source points."""
    rules = LongNardyRules()
    state = _ready_state(
        mode=GameMode.LONG,
        player=Player.WHITE,
        layout={24: (Player.WHITE, 1)},
        remaining_pips=(1,),
    )
    move = Move(Player.WHITE, 23, 22, 1)

    with pytest.raises(RuleViolationError, match="source point"):
        rules._relocate_checker(state, move)


def test_rules_reject_capture_without_blot_permission() -> None:
    """Relocation should not capture blocked enemy points."""
    rules = ShortNardyRules()
    state = _ready_state(
        mode=GameMode.SHORT,
        player=Player.WHITE,
        layout={8: (Player.WHITE, 1), 6: (Player.BLACK, 2)},
        remaining_pips=(2,),
    )
    move = Move(Player.WHITE, 8, 6, 2, captures=True)

    with pytest.raises(RuleViolationError, match="blocked opposing"):
        rules._relocate_checker(state, move)


def test_short_rules_black_home_and_bear_off() -> None:
    """Short black player should bear off toward point 25."""
    rules = ShortNardyRules()
    state = _ready_state(
        mode=GameMode.SHORT,
        player=Player.BLACK,
        layout={19: (Player.BLACK, 1), 24: (Player.BLACK, 14)},
        remaining_pips=(6,),
    )

    move = next(move for move in rules.legal_moves(state) if move.bears_off)
    after = rules.apply_move(state, move)

    assert move.source == 19
    assert move.target == OFF_POSITION
    assert after.borne_off_for(Player.BLACK) == 1


def test_bear_off_requires_home_board_and_clear_bar() -> None:
    """Bearing off should fail while bar or outside-home checkers remain."""
    rules = LongNardyRules()
    with_bar = _ready_state(
        mode=GameMode.LONG,
        player=Player.WHITE,
        layout={6: (Player.WHITE, 15)},
        remaining_pips=(6,),
    )
    with_bar = with_bar.with_bar(Player.WHITE, 1)
    outside_home = _ready_state(
        mode=GameMode.LONG,
        player=Player.WHITE,
        layout={8: (Player.WHITE, 1), 6: (Player.WHITE, 14)},
        remaining_pips=(6,),
    )

    assert rules.can_bear_off_from(with_bar, Player.WHITE, 6, 6) is False
    assert rules.can_bear_off_from(outside_home, Player.WHITE, 6, 6) is False
    assert rules.can_bear_off_from(outside_home, Player.WHITE, 8, 6) is False


def test_bear_off_overshoot_requires_farthest_home_checker() -> None:
    """Overshoot is legal only from the farthest occupied home point."""
    rules = LongNardyRules()
    state = _ready_state(
        mode=GameMode.LONG,
        player=Player.WHITE,
        layout={6: (Player.WHITE, 1), 1: (Player.WHITE, 14)},
        remaining_pips=(6,),
    )

    assert rules.can_bear_off_from(state, Player.WHITE, 1, 6) is False
    assert rules.can_bear_off_from(state, Player.WHITE, 6, 6) is True


def test_long_mode_black_moves_counterclockwise_from_head() -> None:
    """Black checkers should move from point 12 toward point 11."""
    rules = LongNardyRules()
    state = _ready_state(
        mode=GameMode.LONG,
        player=Player.BLACK,
        layout={12: (Player.BLACK, 15)},
        remaining_pips=(1,),
    )

    legal_moves = rules.legal_moves(state)

    assert MoveTarget(source=12, target=11) in _move_targets(legal_moves)


def test_long_mode_black_wraps_from_point_one_to_twenty_four() -> None:
    """Black circular path should continue from point 1 to point 24."""
    rules = LongNardyRules()
    state = _ready_state(
        mode=GameMode.LONG,
        player=Player.BLACK,
        layout={1: (Player.BLACK, 1)},
        remaining_pips=(1,),
    )

    legal_moves = rules.legal_moves(state)

    assert MoveTarget(source=1, target=24) in _move_targets(legal_moves)


def test_long_mode_black_home_and_bear_off_follow_counterclockwise_path() -> None:
    """Black should bear off from points 13..18 after full circle."""
    rules = LongNardyRules()
    state = _ready_state(
        mode=GameMode.LONG,
        player=Player.BLACK,
        layout={18: (Player.BLACK, 1), 13: (Player.BLACK, 14)},
        remaining_pips=(6,),
    )

    move = next(move for move in rules.legal_moves(state) if move.bears_off)
    after = rules.apply_move(state, move)

    assert set(rules.home_points_for(Player.BLACK)) == {13, 14, 15, 16, 17, 18}
    assert move.source == 18
    assert after.borne_off_for(Player.BLACK) == 1


def test_bearing_off_is_available_when_all_checkers_are_home() -> None:
    """Bearing off should work once every checker is in the home board."""
    rules = LongNardyRules()
    state = _ready_state(
        mode=GameMode.LONG,
        player=Player.WHITE,
        layout={6: (Player.WHITE, 1), 1: (Player.WHITE, 14)},
        remaining_pips=(6,),
    )

    move = next(move for move in rules.legal_moves(state) if move.bears_off)
    after = rules.apply_move(state, move)

    assert move.target == 25
    assert after.borne_off_for(Player.WHITE) == 1


def test_doubles_expand_to_four_pips() -> None:
    """A double roll should give four moves of the same die value."""
    engine = GameEngine(
        {
            GameMode.LONG: LongNardyRules(randint=_sequence_randint([4, 4])),
            GameMode.SHORT: ShortNardyRules(randint=_sequence_randint([1, 2])),
        }
    )

    engine.start_new_game(GameMode.LONG)
    state = engine.roll_dice()

    assert state.turn.remaining_pips == (4, 4, 4, 4)


def test_if_only_one_die_is_playable_higher_die_is_forced() -> None:
    """When only one die can be used, legal moves must use the higher die."""
    rules = LongNardyRules()
    state = _ready_state(
        mode=GameMode.LONG,
        player=Player.WHITE,
        layout={8: (Player.WHITE, 1), 7: (Player.BLACK, 2)},
        remaining_pips=(1, 6),
    )

    legal_moves = rules.legal_moves(state)

    assert legal_moves
    assert {move.die_value for move in legal_moves} == {6}


def test_turn_is_skipped_when_player_has_no_legal_moves() -> None:
    """Engine should auto-pass when re-entry from the bar is blocked."""

    class BlockedEntryShortRules(ShortNardyRules):
        """Force a position where White cannot re-enter from the bar."""

        def initial_state(self) -> GameState:
            base_state = super().initial_state()
            board = list(base_state.board)
            board[23] = PointState(owner=Player.BLACK, checkers=2)
            board[22] = PointState(owner=Player.BLACK, checkers=2)
            return replace(base_state, board=tuple(board), bar=(1, 0))

    engine = GameEngine(
        {
            GameMode.LONG: LongNardyRules(randint=_sequence_randint([1, 1])),
            GameMode.SHORT: BlockedEntryShortRules(randint=_sequence_randint([1, 2])),
        }
    )

    engine.start_new_game(GameMode.SHORT)
    state = engine.roll_dice()

    assert state.current_player is Player.BLACK
    assert state.turn.phase is TurnPhase.WAITING_FOR_ROLL


def test_undo_rolls_back_only_last_completed_turn() -> None:
    """Undo should restore only the previous player's completed turn."""
    engine = GameEngine(
        {
            GameMode.LONG: LongNardyRules(randint=_sequence_randint([1, 1])),
            GameMode.SHORT: ShortNardyRules(randint=_sequence_randint([1, 2])),
        }
    )

    initial = engine.start_new_game(GameMode.LONG)
    engine.roll_dice()
    while engine.state.current_player is Player.WHITE:
        engine.apply_move(engine.available_moves()[0])

    assert engine.state.current_player is Player.BLACK
    assert engine.can_undo(Player.WHITE) is True
    assert engine.can_undo(Player.BLACK) is False

    restored = engine.undo(Player.WHITE)
    assert restored == initial


def _ready_state(
    mode: GameMode,
    player: Player,
    layout: dict[int, tuple[Player, int]],
    remaining_pips: tuple[int, ...],
    turn_number: int = 1,
    head_moves_this_turn: int = 0,
) -> GameState:
    """Create a state in READY_TO_MOVE phase for deterministic tests."""
    return GameState(
        mode=mode,
        board=build_board(layout),
        current_player=player,
        turn=TurnState(
            player=player,
            phase=TurnPhase.READY_TO_MOVE,
            dice=DiceRoll.from_values(remaining_pips[0], remaining_pips[-1]),
            remaining_pips=remaining_pips,
            head_moves_this_turn=head_moves_this_turn,
        ),
        turn_number=turn_number,
    )


def _sequence_randint(values: list[int]):
    """Return deterministic dice values for tests."""
    iterator = iter(values)

    def _randint(_low: int, _high: int) -> int:
        return next(iterator)

    return _randint


class MoveTarget(tuple):
    """Tiny comparable pair used to assert generated source/target points."""

    def __new__(cls, source: int, target: int) -> MoveTarget:
        """Create a source-target tuple."""
        return super().__new__(cls, (source, target))


def _move_targets(moves) -> set[MoveTarget]:
    """Return source-target pairs for moves."""
    return {MoveTarget(move.source, move.target) for move in moves}


# ---------- Head rule tests ----------


def test_long_head_rule_only_one_checker_leaves_head() -> None:
    """After one head departure, the head should be excluded from sources."""
    rules = LongNardyRules()
    state = _ready_state(
        mode=GameMode.LONG,
        player=Player.WHITE,
        layout={24: (Player.WHITE, 15)},
        remaining_pips=(1, 2),
        turn_number=3,
        head_moves_this_turn=1,
    )

    legal_sources = {move.source for move in rules.legal_moves(state)}
    assert 24 not in legal_sources


def test_long_head_rule_allows_one_from_head() -> None:
    """Before any head departure, the head should be a legal source."""
    rules = LongNardyRules()
    state = _ready_state(
        mode=GameMode.LONG,
        player=Player.WHITE,
        layout={24: (Player.WHITE, 15)},
        remaining_pips=(1, 2),
        turn_number=3,
    )

    legal_sources = {move.source for move in rules.legal_moves(state)}
    assert 24 in legal_sources


def test_long_head_rule_first_turn_doubles_66_allows_two() -> None:
    """On first turn with 6-6, two checkers may leave head."""
    rules = LongNardyRules()
    state = _ready_state(
        mode=GameMode.LONG,
        player=Player.WHITE,
        layout={24: (Player.WHITE, 15)},
        remaining_pips=(6, 6, 6, 6),
        turn_number=1,
        head_moves_this_turn=1,
    )

    legal_sources = {move.source for move in rules.legal_moves(state)}
    assert 24 in legal_sources


def test_long_head_rule_first_turn_doubles_44_allows_two() -> None:
    """On first turn with 4-4, two checkers may leave head."""
    rules = LongNardyRules()
    state = _ready_state(
        mode=GameMode.LONG,
        player=Player.WHITE,
        layout={24: (Player.WHITE, 15)},
        remaining_pips=(4, 4, 4, 4),
        turn_number=1,
        head_moves_this_turn=1,
    )

    legal_sources = {move.source for move in rules.legal_moves(state)}
    assert 24 in legal_sources


def test_long_head_rule_first_turn_doubles_33_allows_two() -> None:
    """On first turn with 3-3, two checkers may leave head."""
    rules = LongNardyRules()
    state = _ready_state(
        mode=GameMode.LONG,
        player=Player.WHITE,
        layout={24: (Player.WHITE, 15)},
        remaining_pips=(3, 3, 3, 3),
        turn_number=1,
        head_moves_this_turn=1,
    )

    legal_sources = {move.source for move in rules.legal_moves(state)}
    assert 24 in legal_sources


def test_long_head_rule_first_turn_doubles_11_allows_two() -> None:
    """On first turn with any double, two checkers may leave head."""
    rules = LongNardyRules()
    state = _ready_state(
        mode=GameMode.LONG,
        player=Player.WHITE,
        layout={24: (Player.WHITE, 15)},
        remaining_pips=(1, 1, 1, 1),
        turn_number=1,
        head_moves_this_turn=1,
    )

    legal_sources = {move.source for move in rules.legal_moves(state)}
    assert 24 in legal_sources


def test_long_head_rule_non_first_turn_doubles_66_limits_to_one() -> None:
    """After the first turn, 6-6 should still limit to 1 head departure."""
    rules = LongNardyRules()
    state = _ready_state(
        mode=GameMode.LONG,
        player=Player.WHITE,
        layout={24: (Player.WHITE, 15)},
        remaining_pips=(6, 6, 6, 6),
        turn_number=5,
        head_moves_this_turn=1,
    )

    legal_sources = {move.source for move in rules.legal_moves(state)}
    assert 24 not in legal_sources


def test_long_head_rule_black_first_turn_doubles_exception() -> None:
    """Black's first turn (turn_number=2) with 4-4 allows 2 head departures."""
    rules = LongNardyRules()
    state = _ready_state(
        mode=GameMode.LONG,
        player=Player.BLACK,
        layout={12: (Player.BLACK, 15)},
        remaining_pips=(4, 4, 4, 4),
        turn_number=2,
        head_moves_this_turn=1,
    )

    legal_sources = {move.source for move in rules.legal_moves(state)}
    assert 12 in legal_sources


def test_long_head_rule_tracked_through_engine() -> None:
    """Engine should track head departures and enforce the limit."""
    engine = GameEngine(
        {
            GameMode.LONG: LongNardyRules(randint=_sequence_randint([1, 2])),
            GameMode.SHORT: ShortNardyRules(),
        }
    )
    engine.start_new_game(GameMode.LONG)
    state = engine.roll_dice()

    first_move = next(m for m in engine.available_moves() if m.source == 24)
    state = engine.apply_move(first_move)

    head_sources = {m.source for m in engine.available_moves() if m.source == 24}
    assert not head_sources


# ---------- Six-in-a-row blocking rule tests ----------


def test_long_six_consecutive_block_forbidden() -> None:
    """Creating 6 consecutive points blocking opponent path is forbidden."""
    rules = LongNardyRules()
    state = _ready_state(
        mode=GameMode.LONG,
        player=Player.WHITE,
        layout={
            23: (Player.WHITE, 2),
            22: (Player.WHITE, 1),
            21: (Player.WHITE, 1),
            20: (Player.WHITE, 1),
            19: (Player.WHITE, 1),
            12: (Player.BLACK, 15),
        },
        remaining_pips=(5,),
        turn_number=5,
    )

    legal_targets = {move.target for move in rules.legal_moves(state)}
    assert 18 not in legal_targets


def test_long_five_consecutive_is_allowed() -> None:
    """Building 5 consecutive is fine."""
    rules = LongNardyRules()
    state = _ready_state(
        mode=GameMode.LONG,
        player=Player.WHITE,
        layout={
            24: (Player.WHITE, 1),
            23: (Player.WHITE, 1),
            22: (Player.WHITE, 1),
            21: (Player.WHITE, 1),
            12: (Player.BLACK, 15),
        },
        remaining_pips=(4,),
        turn_number=5,
    )

    legal_targets = {move.target for move in rules.legal_moves(state)}
    assert 20 in legal_targets


def test_long_six_consecutive_allowed_when_opponent_in_home() -> None:
    """6-block is allowed when opponent has a checker in their home board."""
    rules = LongNardyRules()
    # Black's home is points 13-18. Place one Black checker there.
    state = _ready_state(
        mode=GameMode.LONG,
        player=Player.WHITE,
        layout={
            23: (Player.WHITE, 2),
            22: (Player.WHITE, 1),
            21: (Player.WHITE, 1),
            20: (Player.WHITE, 1),
            19: (Player.WHITE, 1),
            12: (Player.BLACK, 14),
            15: (Player.BLACK, 1),
        },
        remaining_pips=(5,),
        turn_number=5,
    )

    legal_targets = {move.target for move in rules.legal_moves(state)}
    assert 18 in legal_targets


def test_long_six_block_forbidden_when_opponent_not_in_home() -> None:
    """6-block forbidden when no opponent checker is in their home board."""
    rules = LongNardyRules()
    # Black has no checkers in home (13-18), all on 12
    state = _ready_state(
        mode=GameMode.LONG,
        player=Player.WHITE,
        layout={
            23: (Player.WHITE, 2),
            22: (Player.WHITE, 1),
            21: (Player.WHITE, 1),
            20: (Player.WHITE, 1),
            19: (Player.WHITE, 1),
            12: (Player.BLACK, 15),
        },
        remaining_pips=(5,),
        turn_number=5,
    )

    legal_targets = {move.target for move in rules.legal_moves(state)}
    assert 18 not in legal_targets


def test_long_blocking_rule_does_not_affect_short_nardy() -> None:
    """Short nardy should not have the 6-in-a-row restriction."""
    rules = ShortNardyRules()
    state = _ready_state(
        mode=GameMode.SHORT,
        player=Player.WHITE,
        layout={
            24: (Player.WHITE, 1),
            23: (Player.WHITE, 1),
            22: (Player.WHITE, 1),
            21: (Player.WHITE, 1),
            20: (Player.WHITE, 1),
            1: (Player.BLACK, 15),
        },
        remaining_pips=(5,),
    )

    legal_targets = {move.target for move in rules.legal_moves(state)}
    assert 19 in legal_targets


# ---------- AI tests ----------


def test_ai_easy_returns_valid_moves() -> None:
    """Easy AI should return at least one valid move."""
    from nardy.domain.ai import NardyAI

    rules = LongNardyRules(randint=_sequence_randint([3, 5]))
    state = rules.initial_state()
    rolled = rules.start_turn(state)

    ai = NardyAI("easy")
    moves = ai.choose_moves(rolled, rules)

    assert len(moves) >= 1
    assert all(isinstance(m, Move) for m in moves)


def test_ai_medium_returns_valid_moves() -> None:
    """Medium AI should return a full move sequence."""
    from nardy.domain.ai import NardyAI

    rules = LongNardyRules(randint=_sequence_randint([2, 4]))
    state = rules.initial_state()
    rolled = rules.start_turn(state)

    ai = NardyAI("medium")
    moves = ai.choose_moves(rolled, rules)

    assert len(moves) >= 1


def test_ai_hard_returns_valid_moves() -> None:
    """Hard AI should return a move sequence."""
    from nardy.domain.ai import NardyAI

    rules = LongNardyRules(randint=_sequence_randint([1, 3]))
    state = rules.initial_state()
    rolled = rules.start_turn(state)

    ai = NardyAI("hard")
    moves = ai.choose_moves(rolled, rules)

    assert len(moves) >= 1
