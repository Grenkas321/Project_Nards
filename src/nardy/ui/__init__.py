"""Tkinter user interface exports."""

from nardy.ui.game_screen import GameScreen
from nardy.ui.main_menu import MainMenuScreen
from nardy.ui.shell import ApplicationShell
from nardy.ui.victory_screen import VictoryScreen

__all__ = [
    "ApplicationShell",
    "GameScreen",
    "MainMenuScreen",
    "VictoryScreen",
]
