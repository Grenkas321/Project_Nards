"""Victory screen skeleton for completed games."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from nardy.app.presentation import VictoryScreenData
from nardy.i18n import Localizer, gettext_noop as _


class VictoryScreen(ttk.Frame):
    """Render the game over state and return control to the menu."""

    def __init__(
        self,
        master: tk.Misc,
        localizer: Localizer,
        data: VictoryScreenData,
        on_back_to_menu: Callable[[], None],
    ) -> None:
        """Create the victory widgets from presentation data."""
        super().__init__(master, padding=32)
        translate = localizer.gettext

        self.columnconfigure(0, weight=1)

        ttk.Label(
            self,
            text=data.title,
            font=("Segoe UI", 28, "bold"),
            anchor=tk.CENTER,
        ).grid(row=0, column=0, sticky="ew", pady=(0, 16))

        ttk.Label(
            self,
            text=data.summary,
            anchor=tk.CENTER,
        ).grid(row=1, column=0, sticky="ew", pady=(0, 24))

        ttk.Button(
            self,
            text=translate(_("Back to menu")),
            command=on_back_to_menu,
        ).grid(row=2, column=0)
