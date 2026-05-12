"""Application controller coordinating screens and domain actions."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import replace
from typing import Literal

from nardy.app.presentation import present_game_state, present_victory
from nardy.domain.engine import GameEngine
from nardy.domain.models import GameMode, GameState, Move, Player, TurnPhase
from nardy.i18n import Localizer, gettext_noop as _
from nardy.ui.game_screen import GameScreen
from nardy.ui.main_menu import MainMenuScreen
from nardy.ui.shell import ApplicationShell
from nardy.ui.victory_screen import VictoryScreen

ScreenName = Literal["menu", "game", "victory"]


class AppController:
    """Coordinate application flow between engine, localization and UI."""

    def __init__(
        self,
        shell: ApplicationShell,
        engine: GameEngine,
        localizer: Localizer,
        controlled_player: Player | None = None,
        state_poller: Callable[[], GameState | None] | None = None,
        state_waiter: Callable[[], GameState | None] | None = None,
    ) -> None:
        """Store the application dependencies."""
        self._shell = shell
        self._engine = engine
        self._localizer = localizer
        self._controlled_player = controlled_player
        self._state_poller = state_poller
        self._state_waiter = state_waiter
        self._current_screen: ScreenName = "menu"
        self._status_message: str | None = None
        self._last_move: Move | None = None
        self._poll_job: str | None = None
        self._remote_thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def run(self) -> None:
        """Render the main menu and start the Tk event loop."""
        self._show_main_menu()
        self._start_remote_waiter()
        self._schedule_poll()
        self._shell.run()

    def set_locale(self, locale_code: str) -> None:
        """Switch the active locale and redraw the current screen."""
        self._localizer = Localizer(locale_code=locale_code)
        self._render_current_screen()

    def start_game(self, mode: GameMode) -> None:
        """Start a fresh game in the selected mode."""
        self._status_message = None
        self._last_move = None
        state = self._engine.start_new_game(mode)
        self._show_game(state)

    def roll_dice(self) -> None:
        """Roll the dice for the current turn."""
        self._perform_game_action(self._engine.roll_dice)

    def undo(self) -> None:
        """Undo the latest state transition when available."""
        requester = self._engine.state.current_player.opponent
        if not self._engine.can_undo(requester):
            self._status_message = self._localizer.gettext(_("Undo is unavailable."))
            self._render_current_screen()
            return
        self._last_move = None
        self._perform_game_action(lambda: self._engine.undo(requester))

    def apply_move(self, move: Move) -> None:
        """Apply a move selected on the game board."""
        self._last_move = move
        self._perform_game_action(lambda: self._engine.apply_move(move))

    def back_to_menu(self) -> None:
        """Return to the main menu screen."""
        self._status_message = None
        self._show_main_menu()

    def close(self) -> None:
        """Close the application window."""
        if self._poll_job is not None:
            self._shell.root.after_cancel(self._poll_job)
            self._poll_job = None
        self._stop_event.set()
        close_method = getattr(self._engine, "close", None)
        if callable(close_method):
            close_method()
        if self._remote_thread is not None and self._remote_thread.is_alive():
            self._remote_thread.join(timeout=0.3)
        self._shell.close()

    def _start_remote_waiter(self) -> None:
        """Start a background listener for remote updates."""
        if self._state_waiter is None:
            return
        self._remote_thread = threading.Thread(
            target=self._remote_wait_loop,
            daemon=True,
        )
        self._remote_thread.start()

    def _remote_wait_loop(self) -> None:
        """Wait for network updates and refresh UI on change."""
        if self._state_waiter is None:
            return
        while not self._stop_event.is_set():
            try:
                state = self._state_waiter()
            except Exception:
                if self._stop_event.is_set():
                    return
                continue
            if state is None:
                continue
            self._shell.root.after(0, lambda s=state: self._apply_remote_state(s))

    def _apply_remote_state(self, state: GameState) -> None:
        """Apply one remote state update on the UI thread."""
        if self._current_screen not in ("menu", "game", "victory"):
            return
        if (
            self._current_screen == "game"
            and state.turn.phase is TurnPhase.READY_TO_MOVE
            and state.turn.moves
        ):
            self._last_move = state.turn.moves[-1]
        if state.winner is not None:
            self._show_victory(state)
            return
        self._show_game(state)

    def _schedule_poll(self) -> None:
        """Start periodic network state polling when configured."""
        if self._state_poller is None:
            return
        self._poll_job = self._shell.root.after(300, self._poll_remote_state)

    def _poll_remote_state(self) -> None:
        """Refresh UI from remote state snapshots."""
        if self._state_poller is None:
            return
        try:
            state = self._state_poller()
        except Exception:
            self._poll_job = self._shell.root.after(500, self._poll_remote_state)
            return
        if state is not None and self._current_screen in ("menu", "game"):
            self._show_game(state)
        if state is not None and state.winner is not None:
            self._show_victory(state)
        self._poll_job = self._shell.root.after(300, self._poll_remote_state)

    def _perform_game_action(self, action: Callable[[], GameState]) -> None:
        """Execute a state-changing action and refresh the current screen."""
        try:
            state = action()
        except Exception as exc:
            self._status_message = str(exc)
            self._render_current_screen()
            return
        self._status_message = None
        if state.winner is not None:
            self._show_victory(state)
            return
        self._show_game(state)

    def _render_current_screen(self) -> None:
        """Redraw the active screen after locale or status changes."""
        if self._current_screen == "menu":
            self._show_main_menu()
            return

        try:
            state = self._engine.state
        except RuntimeError:
            self._show_main_menu()
            return

        if self._current_screen == "victory" and state.winner is not None:
            self._show_victory(state)
            return
        self._show_game(state)

    def _show_main_menu(self) -> None:
        """Create and display the main menu screen."""
        translate = self._localizer.gettext
        self._current_screen = "menu"
        self._shell.set_title(translate(_("Nardy")))
        self._shell.show(
            MainMenuScreen(
                master=self._shell.root,
                localizer=self._localizer,
                on_start_long=lambda: self.start_game(GameMode.LONG),
                on_start_short=lambda: self.start_game(GameMode.SHORT),
                on_set_locale=self.set_locale,
                on_exit=self.close,
            )
        )

    def _show_game(self, state: GameState) -> None:
        """Create and display the game screen."""
        displayed_state = state
        status_override = self._status_message
        player_locked = False
        if (
            self._controlled_player is not None
            and state.current_player is not self._controlled_player
        ):
            player_locked = True
            displayed_state = replace(
                state,
                turn=state.turn.with_legal_moves(()),
            )
            if status_override is None:
                status_override = self._localizer.gettext(_("Waiting for opponent."))
        screen_data = present_game_state(
            self._localizer,
            state=displayed_state,
            can_undo=self._engine.can_undo(state.current_player.opponent),
            status_override=status_override,
        )
        if player_locked:
            screen_data = replace(
                screen_data,
                can_roll=False,
                can_undo=screen_data.can_undo,
            )
        self._current_screen = "game"
        self._shell.set_title(self._localizer.gettext(_("Nardy")))
        self._shell.show(
            GameScreen(
                master=self._shell.root,
                localizer=self._localizer,
                data=screen_data,
                state=displayed_state,
                last_move=self._last_move,
                on_roll_dice=self.roll_dice,
                on_apply_move=self.apply_move,
                on_undo=self.undo,
                on_back_to_menu=self.back_to_menu,
            )
        )
        self._last_move = None

    def _show_victory(self, state: GameState) -> None:
        """Create and display the victory screen."""
        self._current_screen = "victory"
        self._shell.set_title(self._localizer.gettext(_("Victory")))
        self._shell.show(
            VictoryScreen(
                master=self._shell.root,
                localizer=self._localizer,
                data=present_victory(self._localizer, state),
                on_back_to_menu=self.back_to_menu,
            )
        )
