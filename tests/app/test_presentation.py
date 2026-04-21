"""Tests for pure application presentation helpers."""

from __future__ import annotations

from dataclasses import replace

from nardy.app.presentation import present_game_state, present_victory
from nardy.domain.models import Player
from nardy.domain.rules_long import LongNardyRules
from nardy.i18n import Localizer


def test_present_game_state_exposes_mode_and_action_hint() -> None:
    """The game presenter should provide compact labels for the screen."""
    localizer = Localizer()
    state = LongNardyRules().initial_state()

    data = present_game_state(localizer, state=state, can_undo=False)

    assert data.subtitle == "Mode: Long backgammon"
    assert data.status == "White: roll dice."
    assert data.can_roll is True
    assert data.can_undo is False


def test_present_victory_formats_the_winner_message() -> None:
    """The victory presenter should include the translated winner name."""
    localizer = Localizer()
    state = replace(LongNardyRules().initial_state(), winner=Player.WHITE)

    data = present_victory(localizer, state)

    assert data.title == "Victory"
    assert data.summary == "White wins."
