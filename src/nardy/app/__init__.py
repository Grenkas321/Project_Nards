"""Application layer exports for the Nardy project."""

from nardy.app.presentation import (
    GameScreenData,
    VictoryScreenData,
    present_game_state,
    present_victory,
)

__all__ = [
    "GameScreenData",
    "VictoryScreenData",
    "present_game_state",
    "present_victory",
]
