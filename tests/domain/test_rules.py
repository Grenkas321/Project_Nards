"""Tests for the ruleset skeletons."""

from __future__ import annotations

from nardy.domain.models import GameMode, Player
from nardy.domain.rules_long import LongNardyRules
from nardy.domain.rules_short import ShortNardyRules


def test_long_rules_build_expected_initial_state() -> None:
    """Long rules should create the starting stacks."""
    state = LongNardyRules().initial_state()
    assert state.mode is GameMode.LONG
    assert state.point(24).owner is Player.WHITE
    assert state.point(24).checkers == 15
    assert state.point(1).owner is Player.BLACK
    assert state.point(1).checkers == 15


def test_short_rules_build_classic_setup() -> None:
    """Short rules should create the classical backgammon layout."""
    state = ShortNardyRules().initial_state()
    assert state.mode is GameMode.SHORT
    assert state.point(24).checkers == 2
    assert state.point(13).checkers == 5
    assert state.point(1).owner is Player.BLACK
