"""Application controller coordinating screens and domain actions."""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from nardy.app.presentation import present_game_state, present_victory
from nardy.domain.engine import GameEngine
from nardy.domain.models import GameMode, GameState
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
    ) -> None:
        """Store the application dependencies."""
        self._shell = shell
        self._engine = engine
        self._localizer = localizer
        self._current_screen: ScreenName = "menu"
        self._status_message: str | None = None

    def run(self) -> None:
        """Render the main menu and start the Tk event loop."""
        self._show_main_menu()
        self._shell.run()

    def set_locale(self, locale_code: str) -> None:
        """Switch the active locale and redraw the current screen."""
        self._localizer = Localizer(locale_code=locale_code)
        self._render_current_screen()

    def start_game(self, mode: GameMode) -> None:
        """Start a fresh game in the selected mode."""
        self._status_message = None
        state = self._engine.start_new_game(mode)
        self._show_game(state)

    def roll_dice(self) -> None:
        """Roll the dice for the current turn."""
        self._perform_game_action(self._engine.roll_dice)

    def undo(self) -> None:
        """Undo the latest state transition when available."""
        if not self._engine.can_undo():
            self._status_message = self._localizer.gettext(_("Undo is unavailable."))
            self._render_current_screen()
            return
        self._perform_game_action(self._engine.undo)

    def back_to_menu(self) -> None:
        """Return to the main menu screen."""
        self._status_message = None
        self._show_main_menu()

    def close(self) -> None:
        """Close the application window."""
        self._shell.close()

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
        self._current_screen = "game"
        self._shell.set_title(self._localizer.gettext(_("Nardy")))
        self._shell.show(
            GameScreen(
                master=self._shell.root,
                localizer=self._localizer,
                data=present_game_state(
                    self._localizer,
                    state=state,
                    can_undo=self._engine.can_undo(),
                    status_override=self._status_message,
                ),
                on_roll_dice=self.roll_dice,
                on_undo=self.undo,
                on_back_to_menu=self.back_to_menu,
            )
        )

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
