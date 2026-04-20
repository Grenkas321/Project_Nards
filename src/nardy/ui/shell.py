"""Tkinter application shell and screen host."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class ApplicationShell:
    """Wrap the root Tk window and active screen lifecycle."""

    def __init__(self) -> None:
        """Create the root window with a responsive layout."""
        self._root = tk.Tk()
        self._root.geometry("1024x720")
        self._root.minsize(900, 640)
        self._root.rowconfigure(0, weight=1)
        self._root.columnconfigure(0, weight=1)
        ttk.Style(self._root).theme_use("clam")
        self._screen: ttk.Frame | None = None

    @property
    def root(self) -> tk.Tk:
        """Expose the root widget for screen construction."""
        return self._root

    def set_title(self, title: str) -> None:
        """Update the window title."""
        self._root.title(title)

    def show(self, screen: ttk.Frame) -> None:
        """Display a new screen and destroy the previous one."""
        if self._screen is not None:
            self._screen.destroy()
        self._screen = screen
        self._screen.grid(row=0, column=0, sticky="nsew")

    def run(self) -> None:
        """Enter the Tk main loop."""
        self._root.mainloop()

    def close(self) -> None:
        """Close the Tk root window."""
        self._root.destroy()
