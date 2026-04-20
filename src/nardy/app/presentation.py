"""Pure presentation helpers for application screens."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from nardy.domain.models import GameMode, GameState, Move, Player, TurnPhase
from nardy.i18n import Localizer, gettext_noop as _


@dataclass(frozen=True, slots=True)
class GameScreenData:
    """Prepared strings and flags required by the game screen."""

    title: str
    subtitle: str
    current_player: str
    turn_phase: str
    dice: str
    status: str
    move_lines: tuple[str, ...]
    board_lines: tuple[str, ...]
    can_roll: bool
    can_undo: bool


@dataclass(frozen=True, slots=True)
class VictoryScreenData:
    """Prepared strings for the victory screen."""

    title: str
    summary: str


def present_game_state(
    localizer: Localizer,
    state: GameState,
    can_undo: bool,
    status_override: str | None = None,
) -> GameScreenData:
    """Convert a domain state into UI-friendly strings."""
    translate = localizer.gettext
    dice_value = (
        "-"
        if state.turn.dice is None
        else ", ".join(str(value) for value in state.turn.dice.values)
    )
    move_lines = tuple(
        _format_move(move) for move in state.turn.legal_moves
    ) or (translate(_("No legal moves yet.")),)
    board_lines = tuple(
        _format_board_line(translate, state, point)
        for point in range(24, 0, -1)
        if state.point(point).checkers
    ) or (translate(_("Board is empty.")),)

    return GameScreenData(
        title=translate(_("Nardy")),
        subtitle=(
            f"{translate(_('Mode'))}: "
            f"{translate(_mode_label(state.mode))}"
        ),
        current_player=(
            f"{translate(_('Current player'))}: "
            f"{translate(_player_label(state.current_player))}"
        ),
        turn_phase=(
            f"{translate(_('Turn phase'))}: "
            f"{translate(_phase_label(state.turn.phase))}"
        ),
        dice=f"{translate(_('Dice'))}: {dice_value}",
        status=status_override or translate(_status_message(state.turn.phase)),
        move_lines=move_lines,
        board_lines=board_lines,
        can_roll=state.turn.phase is TurnPhase.WAITING_FOR_ROLL,
        can_undo=can_undo,
    )


def present_victory(localizer: Localizer, state: GameState) -> VictoryScreenData:
    """Build the copy for the victory screen."""
    translate = localizer.gettext
    winner = state.winner or state.current_player
    return VictoryScreenData(
        title=translate(_("Victory")),
        summary=translate(_("{player} wins.")).format(
            player=translate(_player_label(winner))
        ),
    )


def _format_move(move: Move) -> str:
    """Render a legal move into a compact human-readable form."""
    suffix = ""
    if move.captures:
        suffix = " x"
    if move.bears_off:
        suffix = " off"
    return f"{move.source} -> {move.target} ({move.die_value}){suffix}"


def _format_board_line(
    translate: Callable[[str], str],
    state: GameState,
    point_number: int,
) -> str:
    """Render one occupied board point."""
    point = state.point(point_number)
    owner = translate(_player_label(point.owner))
    return f"{point_number:>2}: {owner} x{point.checkers}"


def _mode_label(mode: GameMode) -> str:
    """Return a translatable label for a game mode."""
    return _("Long backgammon") if mode is GameMode.LONG else _("Short backgammon")


def _player_label(player: Player | None) -> str:
    """Return a translatable label for a player."""
    if player is Player.WHITE:
        return _("White")
    if player is Player.BLACK:
        return _("Black")
    return _("Unknown player")


def _phase_label(phase: TurnPhase) -> str:
    """Return a translatable label for a turn phase."""
    if phase is TurnPhase.WAITING_FOR_ROLL:
        return _("Waiting for roll")
    if phase is TurnPhase.READY_TO_MOVE:
        return _("Ready to move")
    return _("Turn complete")


def _status_message(phase: TurnPhase) -> str:
    """Return a default status message for the turn phase."""
    if phase is TurnPhase.WAITING_FOR_ROLL:
        return _("Roll the dice to begin the turn.")
    if phase is TurnPhase.READY_TO_MOVE:
        return _("Select a legal move once board interaction is implemented.")
    return _("Turn is complete.")
