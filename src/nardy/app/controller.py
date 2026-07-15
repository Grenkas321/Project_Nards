"""Application controller coordinating screens and domain actions."""

from __future__ import annotations

import queue
import threading
from collections.abc import Callable
from dataclasses import replace
from typing import Literal

import pygame

from nardy.app.presentation import present_game_state, present_victory
from nardy.domain.ai import NardyAI, Difficulty
from nardy.domain.engine import GameEngine
from nardy.domain.models import GameMode, GameState, Move, Player, TurnPhase
from nardy.i18n import Localizer, gettext_noop as _
from nardy.ui.game_screen import GameScreen
from nardy.ui.menu_screens import (
    TitleScreen, PlayModeScreen, AIMenuScreen,
    NetworkMenuScreen, LocalMenuScreen, RulesScreen,
)
from nardy.ui.runtime import Scheduler, Screen
from nardy.ui.victory_screen import VictoryScreen

ScreenName = Literal["menu", "game", "victory"]


def _get_rules_for_mode(mode: GameMode):
    """Return a ruleset instance for the given mode."""
    from nardy.domain.rules_long import LongNardyRules
    from nardy.domain.rules_short import ShortNardyRules
    if mode is GameMode.LONG:
        return LongNardyRules()
    return ShortNardyRules()


class AppController:
    """Coordinate application flow between engine, localization and UI."""

    def __init__(
        self,
        engine: GameEngine,
        localizer: Localizer,
        controlled_player: Player | None = None,
        state_poller: Callable[[], GameState | None] | None = None,
        state_waiter: Callable[[], GameState | None] | None = None,
        ai: NardyAI | None = None,
        ai_player: Player | None = None,
    ) -> None:
        """Store the application dependencies."""
        self._engine = engine
        self._localizer = localizer
        self._controlled_player = controlled_player
        self._state_poller = state_poller
        self._state_waiter = state_waiter
        self._ai = ai
        self._ai_player = ai_player
        self._current_screen: ScreenName = "menu"
        self._game_screen: GameScreen | None = None
        self._screen: Screen | None = None
        self._last_displayed_state: GameState | None = None
        self._status_message: str | None = None
        self._last_move: Move | None = None
        self._remote_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._scheduler = Scheduler()
        self._poll_active = False
        self._poll_accum_ms = 0.0
        self._remote_queue: queue.Queue[GameState] = queue.Queue()
        self.running = True
        self._rematch: Callable[[], None] | None = None

    def start(self) -> None:
        """Show the main menu and start background workers."""
        self._show_main_menu()
        if self._controlled_player is not None:
            # Network client: if the host already started the game, jump
            # straight to the board instead of stranding the player in a menu.
            try:
                state = self._engine.state
            except Exception:
                state = None
            if state is not None:
                self._show_game(state)
        self._start_remote_waiter()
        self._poll_active = self._state_poller is not None

    def set_locale(self, locale_code: str) -> None:
        """Switch the active locale and redraw the current screen."""
        self._localizer = Localizer(locale_code=locale_code)
        self._render_current_screen()

    def start_game(self, mode: GameMode) -> None:
        """Start a fresh game in the selected mode."""
        self._status_message = None
        self._last_move = None
        self._rematch = lambda: self.start_game(mode)
        state = self._engine.start_new_game(mode)
        self._show_game(state)
        self._maybe_ai_turn()

    def start_ai_game(
        self, mode: GameMode, difficulty: Difficulty,
        player_color: Player = Player.WHITE,
    ) -> None:
        """Start a game against AI."""
        from nardy.domain.engine import build_default_engine
        self._engine = build_default_engine()
        self._ai = NardyAI(difficulty)
        self._ai_player = player_color.opponent
        self._controlled_player = player_color
        self.start_game(mode)
        self._rematch = lambda: self.start_ai_game(mode, difficulty, player_color)

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

    def undo_move(self) -> None:
        """Undo the last move within the current turn."""
        can_undo = getattr(self._engine, "can_undo_last_move", None)
        if can_undo is None or not can_undo():
            return
        self._last_move = None
        self._perform_game_action(self._engine.undo_last_move)

    def apply_move(self, move: Move) -> None:
        """Apply a move selected on the game board."""
        self._last_move = move
        self._perform_game_action(lambda: self._engine.apply_move(move))

    def back_to_menu(self) -> None:
        """Return to the main menu screen."""
        self._status_message = None
        self._show_main_menu()

    def close(self) -> None:
        """Signal the main loop to stop and release background resources."""
        self.running = False
        self._stop_event.set()
        close_method = getattr(self._engine, "close", None)
        if callable(close_method):
            close_method()
        if self._remote_thread is not None and self._remote_thread.is_alive():
            self._remote_thread.join(timeout=0.3)

    # ---------- Main-loop hooks ----------

    def handle_event(self, event: pygame.event.Event) -> None:
        """Forward an event to the active screen."""
        if self._screen is not None:
            self._screen.handle_event(event)

    def update(self, dt_ms: int) -> None:
        """Advance the active screen, scheduler, and remote polling."""
        self._scheduler.update(dt_ms)
        self._drain_remote_queue()
        if self._poll_active:
            self._poll_accum_ms += dt_ms
            if self._poll_accum_ms >= 300:
                self._poll_accum_ms = 0.0
                self._poll_remote_state()
        if self._screen is not None:
            self._screen.update(dt_ms)

    def draw(self, surface: pygame.Surface) -> None:
        """Render the active screen."""
        if self._screen is not None:
            self._screen.draw(surface)

    # ---------- Remote/network ----------

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
        """Wait for network updates and queue them for the main thread."""
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
            self._remote_queue.put(state)

    def _drain_remote_queue(self) -> None:
        """Apply any remote state updates queued by the waiter thread."""
        while True:
            try:
                state = self._remote_queue.get_nowait()
            except queue.Empty:
                return
            self._apply_remote_state(state)

    def _apply_remote_state(self, state: GameState) -> None:
        """Apply one remote state update on the main thread."""
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

    def _poll_remote_state(self) -> None:
        """Refresh UI from remote state snapshots."""
        if self._state_poller is None:
            return
        try:
            state = self._state_poller()
        except Exception:
            return
        if state is not None and self._current_screen in ("menu", "game"):
            self._show_game(state)
        if state is not None and state.winner is not None:
            self._show_victory(state)

    # ---------- AI ----------

    def _maybe_ai_turn(self) -> None:
        """Trigger AI play if it's the AI's turn."""
        if self._ai is None or self._ai_player is None:
            return
        try:
            state = self._engine.state
        except RuntimeError:
            return
        if state.winner is not None or state.current_player is not self._ai_player:
            return
        if state.turn.phase is TurnPhase.WAITING_FOR_ROLL:
            self._scheduler.schedule(600, self._ai_roll)
        elif state.turn.phase is TurnPhase.READY_TO_MOVE:
            self._scheduler.schedule(400, self._ai_move)

    def _ai_roll(self) -> None:
        """AI rolls dice — triggers visual animation on the board."""
        if self._ai is None:
            return
        try:
            state = self._engine.state
        except RuntimeError:
            return
        if state.current_player is not self._ai_player:
            return
        if state.turn.phase is not TurnPhase.WAITING_FOR_ROLL:
            return
        if self._game_screen is not None:
            self._game_screen.trigger_roll()

    def _ai_move(self) -> None:
        """AI makes its moves one by one."""
        if self._ai is None:
            return
        try:
            state = self._engine.state
        except RuntimeError:
            return
        if state.current_player is not self._ai_player:
            return
        if state.turn.phase is not TurnPhase.READY_TO_MOVE:
            return

        rules = _get_rules_for_mode(state.mode)
        moves = self._ai.choose_moves(state, rules)
        if not moves:
            return
        self._ai_play_sequence(moves, 0)

    def _ai_play_sequence(self, moves: list[Move], idx: int) -> None:
        """Apply AI moves one at a time with animation."""
        if idx >= len(moves):
            self._maybe_ai_turn()
            return
        move = moves[idx]
        self._last_move = move
        try:
            state = self._engine.apply_move(move)
        except Exception:
            return
        self._status_message = None
        if state.winner is not None:
            self._show_victory(state)
            return
        self._show_game(state)
        self._scheduler.schedule(600, lambda: self._ai_play_sequence(moves, idx + 1))

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
        if self._ai is not None and state.current_player is self._ai_player:
            self._scheduler.schedule(600, self._maybe_ai_turn)

    # ---------- Screen transitions ----------

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
        """Show the title screen."""
        self._current_screen = "menu"
        self._game_screen = None
        self._last_displayed_state = None
        self._ai = None
        self._ai_player = None
        self._rematch = None
        self._screen = TitleScreen(
            localizer=self._localizer,
            on_play=self._show_play_menu,
            on_rules=self._show_rules,
            on_set_locale=self.set_locale,
            on_exit=self.close,
        )

    def _show_play_menu(self) -> None:
        """Show play mode selection."""
        self._current_screen = "menu"
        self._screen = PlayModeScreen(
            localizer=self._localizer,
            on_network=self._show_network_menu,
            on_ai=self._show_ai_menu,
            on_local=self._show_local_menu,
            on_back=self._show_main_menu,
        )

    def _show_ai_menu(self) -> None:
        """Show AI difficulty selection."""
        self._current_screen = "menu"
        self._screen = AIMenuScreen(
            localizer=self._localizer,
            on_start=self._start_ai_from_menu,
            on_back=self._show_play_menu,
        )

    def _start_ai_from_menu(self, mode_str: str, difficulty: str,
                            color: str = "white") -> None:
        """Start AI game from menu selection."""
        mode = GameMode.LONG if mode_str == "long" else GameMode.SHORT
        player = Player.WHITE if color == "white" else Player.BLACK
        self.start_ai_game(mode, difficulty, player_color=player)

    def _show_network_menu(self) -> None:
        """Show network play menu."""
        self._current_screen = "menu"
        self._screen = NetworkMenuScreen(
            localizer=self._localizer,
            on_back=self._show_play_menu,
        )

    def _show_local_menu(self) -> None:
        """Show local game menu."""
        self._current_screen = "menu"
        self._screen = LocalMenuScreen(
            localizer=self._localizer,
            on_start_long=lambda: self.start_game(GameMode.LONG),
            on_start_short=lambda: self.start_game(GameMode.SHORT),
            on_back=self._show_play_menu,
        )

    def _show_rules(self) -> None:
        """Show rules screen."""
        self._current_screen = "menu"
        self._screen = RulesScreen(
            localizer=self._localizer,
            on_back=self._show_main_menu,
        )

    def _show_game(self, state: GameState) -> None:
        """Update existing game screen or create a new one."""
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
        can_undo_move_fn = getattr(self._engine, "can_undo_last_move", None)
        can_undo_move = bool(can_undo_move_fn and can_undo_move_fn())
        screen_data = present_game_state(
            self._localizer,
            state=displayed_state,
            can_undo=self._engine.can_undo(state.current_player.opponent),
            can_undo_move=can_undo_move,
            status_override=status_override,
        )
        if player_locked:
            screen_data = replace(
                screen_data,
                can_roll=False,
                can_undo=screen_data.can_undo,
            )

        if (
            displayed_state == self._last_displayed_state
            and self._last_move is None
            and self._current_screen == "game"
        ):
            return
        self._last_displayed_state = displayed_state

        if self._current_screen == "game" and self._game_screen is not None:
            self._game_screen.update_state(
                data=screen_data,
                state=displayed_state,
                last_move=self._last_move,
                can_roll=screen_data.can_roll,
            )
            self._last_move = None
            return

        self._current_screen = "game"
        self._game_screen = GameScreen(
            localizer=self._localizer,
            data=screen_data,
            state=displayed_state,
            last_move=self._last_move,
            on_roll_dice=self.roll_dice,
            on_apply_move=self.apply_move,
            on_undo=self.undo,
            on_undo_move=self.undo_move,
            on_back_to_menu=self.back_to_menu,
        )
        self._screen = self._game_screen
        self._last_move = None

    def _show_victory(self, state: GameState) -> None:
        """Create and display the victory screen."""
        self._current_screen = "victory"
        self._game_screen = None
        self._last_displayed_state = None
        self._screen = VictoryScreen(
            localizer=self._localizer,
            data=present_victory(self._localizer, state),
            on_back_to_menu=self.back_to_menu,
            on_rematch=self._rematch,
        )
