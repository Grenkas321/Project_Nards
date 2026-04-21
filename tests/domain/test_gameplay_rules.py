"""Gameplay-focused unit tests for long and short nardy rules."""

from __future__ import annotations

from dataclasses import replace

from nardy.domain.engine import GameEngine
from nardy.domain.models import (
    DiceRoll,
    GameMode,
    GameState,
    Player,
    PointState,
    TurnPhase,
    TurnState,
    build_board,
)
from nardy.domain.rules_long import LongNardyRules
from nardy.domain.rules_short import ShortNardyRules


def test_long_mode_initial_layout_matches_classic_head_start() -> None:
    """Long mode should place each side on its starting edge."""
    state = LongNardyRules().initial_state()
    assert state.point(24).owner is Player.WHITE
    assert state.point(24).checkers == 15
    assert state.point(1).owner is Player.BLACK
    assert state.point(1).checkers == 15


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
        ),
    )


def _sequence_randint(values: list[int]):
    """Return deterministic dice values for tests."""
    iterator = iter(values)

    def _randint(_low: int, _high: int) -> int:
        return next(iterator)

    return _randint
