"""Tests for application controller behavior without real Tk widgets."""

from __future__ import annotations

from dataclasses import replace

from nardy.app.controller import AppController
from nardy.domain.engine import build_default_engine
from nardy.domain.models import GameMode, TurnPhase
from nardy.domain.rules_long import LongNardyRules
from nardy.i18n import Localizer


class DummyRoot:
    """Small stand-in for Tk root scheduling methods."""

    def __init__(self) -> None:
        """Create scheduler state."""
        self.cancelled: list[str] = []

    def after(self, _delay: int, _callback):
        """Return an opaque job id without running callback."""
        return "job-id"

    def after_cancel(self, job_id: str) -> None:
        """Record cancelled job ids."""
        self.cancelled.append(job_id)


class DummyShell:
    """Test shell that captures rendered screens."""

    def __init__(self) -> None:
        """Initialize fields used by assertions."""
        self._root = DummyRoot()
        self.last_screen = None
        self.closed = False
        self.title = ""

    @property
    def root(self) -> DummyRoot:
        """Expose dummy root object."""
        return self._root

    def set_title(self, title: str) -> None:
        """Capture the window title."""
        self.title = title

    def show(self, screen) -> None:
        """Capture the last rendered screen object."""
        self.last_screen = screen

    def run(self) -> None:
        """No-op run for controller tests."""

    def close(self) -> None:
        """Mark shell as closed."""
        self.closed = True


class DummyGameScreen:
    """Capture constructor kwargs passed by controller."""

    def __init__(self, *args, **kwargs) -> None:
        """Store positional and keyword arguments."""
        self.args = args
        self.kwargs = kwargs


def test_controller_disables_roll_when_controlled_player_is_waiting(
    monkeypatch,
) -> None:
    """Game screen should lock controls when it is opponent's turn."""
    monkeypatch.setattr("nardy.app.controller.GameScreen", DummyGameScreen)

    shell = DummyShell()
    controller = AppController(
        shell=shell,
        engine=build_default_engine(),
        localizer=Localizer(),
        controlled_player=LongNardyRules().initial_state().current_player.opponent,
    )

    controller.start_game(GameMode.LONG)

    data = shell.last_screen.kwargs["data"]
    assert data.can_roll is False
    assert data.can_undo is False


def test_controller_allows_roll_for_active_controlled_player(monkeypatch) -> None:
    """Game screen should keep roll enabled for active player."""
    monkeypatch.setattr("nardy.app.controller.GameScreen", DummyGameScreen)

    shell = DummyShell()
    controller = AppController(
        shell=shell,
        engine=build_default_engine(),
        localizer=Localizer(),
        controlled_player=LongNardyRules().initial_state().current_player,
    )

    controller.start_game(GameMode.LONG)

    data = shell.last_screen.kwargs["data"]
    assert data.can_roll is True


def test_controller_applies_remote_state_animation_hint(monkeypatch) -> None:
    """Incoming remote move should be passed as ``last_move`` to screen."""
    monkeypatch.setattr("nardy.app.controller.GameScreen", DummyGameScreen)

    shell = DummyShell()
    controller = AppController(
        shell=shell,
        engine=build_default_engine(),
        localizer=Localizer(),
    )

    rules = LongNardyRules()
    state = rules.initial_state()
    started = rules.start_turn(state)
    legal_move = rules.legal_moves(started)[0]
    moved = rules.apply_move(started, legal_move)
    remote_state = replace(
        moved,
        turn=replace(
            moved.turn,
            phase=TurnPhase.READY_TO_MOVE,
            moves=(legal_move,),
        ),
    )

    controller._show_game(remote_state)
    controller._last_move = None
    controller._apply_remote_state(remote_state)

    assert shell.last_screen.kwargs["last_move"] == legal_move


def test_controller_close_cancels_poll_and_closes_engine(monkeypatch) -> None:
    """Controller close should cancel scheduled jobs and close dependencies."""

    class DummyEngine:
        """Small engine object exposing ``close``."""

        def __init__(self) -> None:
            """Initialize closing marker."""
            self.closed = False

        def close(self) -> None:
            """Mark close call."""
            self.closed = True

    shell = DummyShell()
    engine = DummyEngine()
    controller = AppController(
        shell=shell,
        engine=engine,
        localizer=Localizer(),
    )
    controller._poll_job = "job-1"

    controller.close()

    assert shell.root.cancelled == ["job-1"]
    assert engine.closed is True
    assert shell.closed is True
