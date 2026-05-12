"""Pure presentation helpers for application screens."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from nardy.domain.models import GameMode, GameState, Player, TurnPhase
from nardy.i18n import Localizer, gettext_noop as _


@dataclass(frozen=True, slots=True)
class GameScreenData:
    """Prepared strings and flags required by the game screen."""

    title: str
    subtitle: str
    status: str
    dice: str
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
    return GameScreenData(
        title=translate(_("Nardy")),
        subtitle=(
            f"{translate(_('Mode'))}: "
            f"{translate(_mode_label(state.mode))}"
        ),
        status=status_override or _status_message(translate, state),
        dice=f"{translate(_('Dice'))}: {_dice_text(state)}",
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


def _status_message(
    translate: Callable[[str], str],
    state: GameState,
) -> str:
    """Return a default status message for the current game phase."""
    player = translate(_player_label(state.current_player))
    if state.turn.phase is TurnPhase.WAITING_FOR_ROLL:
        return translate(_("{player}: roll dice.")).format(
            player=player
        )
    if state.turn.phase is TurnPhase.READY_TO_MOVE:
        return translate(_("{player}: choose a highlighted checker.")).format(
            player=player
        )
    return translate(_("{player}: turn finished.")).format(
        player=player
    )


def _dice_text(state: GameState) -> str:
    """Render dice information for the status area."""
    if state.turn.dice is None:
        return "-"
    rolled = ",".join(str(value) for value in state.turn.dice.values)
    remaining = ",".join(str(value) for value in state.turn.remaining_pips)
    return f"{rolled} [{remaining or '-'}]"
