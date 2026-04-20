"""Game screen skeleton for the future interactive board."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from nardy.app.presentation import GameScreenData
from nardy.i18n import Localizer, gettext_noop as _


class GameScreen(ttk.Frame):
    """Render the current game summary, controls and board snapshot."""

    def __init__(
        self,
        master: tk.Misc,
        localizer: Localizer,
        data: GameScreenData,
        on_roll_dice: Callable[[], None],
        on_undo: Callable[[], None],
        on_back_to_menu: Callable[[], None],
    ) -> None:
        """Build the screen widgets from presentation data."""
        super().__init__(master, padding=24)
        translate = localizer.gettext

        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(2, weight=1)

        ttk.Label(
            self,
            text=data.title,
            font=("Segoe UI", 24, "bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))

        info_frame = ttk.LabelFrame(self, text=translate(_("Status")), padding=16)
        info_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 12), pady=(0, 12))
        for row, text in enumerate(
            (
                data.subtitle,
                data.current_player,
                data.turn_phase,
                data.dice,
                data.status,
            )
        ):
            ttk.Label(
                info_frame,
                text=text,
                justify=tk.LEFT,
                anchor=tk.W,
            ).grid(row=row, column=0, sticky="w", pady=(0, 8))

        moves_frame = ttk.LabelFrame(
            self,
            text=translate(_("Available moves")),
            padding=16,
        )
        moves_frame.grid(row=1, column=1, sticky="nsew", pady=(0, 12))
        ttk.Label(
            moves_frame,
            text="\n".join(data.move_lines),
            justify=tk.LEFT,
            anchor=tk.W,
        ).grid(row=0, column=0, sticky="nw")

        board_frame = ttk.LabelFrame(
            self,
            text=translate(_("Board snapshot")),
            padding=16,
        )
        board_frame.grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="nsew",
            pady=(0, 16),
        )
        board_frame.columnconfigure(0, weight=1)
        ttk.Label(
            board_frame,
            text="\n".join(data.board_lines),
            justify=tk.LEFT,
            anchor=tk.W,
        ).grid(row=0, column=0, sticky="nw")

        buttons = ttk.Frame(self)
        buttons.grid(row=3, column=0, columnspan=2, sticky="ew")
        buttons.columnconfigure(0, weight=1)
        buttons.columnconfigure(1, weight=1)
        buttons.columnconfigure(2, weight=1)

        ttk.Button(
            buttons,
            text=translate(_("Roll dice")),
            command=on_roll_dice,
            state=tk.NORMAL if data.can_roll else tk.DISABLED,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(
            buttons,
            text=translate(_("Undo")),
            command=on_undo,
            state=tk.NORMAL if data.can_undo else tk.DISABLED,
        ).grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Button(
            buttons,
            text=translate(_("Back to menu")),
            command=on_back_to_menu,
        ).grid(row=0, column=2, sticky="ew", padx=(8, 0))
