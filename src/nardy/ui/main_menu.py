"""Main menu screen for choosing the game mode and locale."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from nardy.i18n import Localizer, gettext_noop as _


class MainMenuScreen(ttk.Frame):
    """Render the main menu with mode and locale controls."""

    def __init__(
        self,
        master: tk.Misc,
        localizer: Localizer,
        on_start_long: Callable[[], None],
        on_start_short: Callable[[], None],
        on_set_locale: Callable[[str], None],
        on_exit: Callable[[], None],
    ) -> None:
        """Create the menu widgets and wire callbacks."""
        super().__init__(master, padding=32)
        translate = localizer.gettext

        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(2, weight=1)

        ttk.Label(
            self,
            text=translate(_("Nardy")),
            anchor=tk.CENTER,
            font=("Segoe UI", 28, "bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 12))

        ttk.Label(
            self,
            text=translate(_("Choose a mode")),
            anchor=tk.CENTER,
        ).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 24))

        mode_frame = ttk.LabelFrame(self, text=translate(_("Mode")), padding=20)
        mode_frame.grid(row=2, column=0, sticky="nsew", padx=(0, 12))
        mode_frame.columnconfigure(0, weight=1)
        ttk.Button(
            mode_frame,
            text=translate(_("Long backgammon")),
            command=on_start_long,
        ).grid(row=0, column=0, sticky="ew", pady=(0, 12))
        ttk.Button(
            mode_frame,
            text=translate(_("Short backgammon")),
            command=on_start_short,
        ).grid(row=1, column=0, sticky="ew")

        locale_frame = ttk.LabelFrame(
            self,
            text=translate(_("Language")),
            padding=20,
        )
        locale_frame.grid(row=2, column=1, sticky="nsew", padx=(12, 0))
        locale_frame.columnconfigure(0, weight=1)
        ttk.Button(
            locale_frame,
            text=translate(_("English")),
            command=lambda: on_set_locale("en"),
        ).grid(row=0, column=0, sticky="ew", pady=(0, 12))
        ttk.Button(
            locale_frame,
            text=translate(_("Russian")),
            command=lambda: on_set_locale("ru"),
        ).grid(row=1, column=0, sticky="ew")

        ttk.Button(
            self,
            text=translate(_("Exit")),
            command=on_exit,
        ).grid(row=3, column=0, columnspan=2, pady=(24, 0))
