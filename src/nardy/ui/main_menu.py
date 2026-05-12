"""Main menu screen for choosing the game mode and locale."""

from __future__ import annotations

import subprocess
import sys
import tkinter as tk
from collections.abc import Callable
from tkinter import messagebox, ttk

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

        # LAN section
        lan_frame = ttk.LabelFrame(self, text=translate(_("LAN Game")), padding=20)
        lan_frame.grid(row=2, column=1, sticky="nsew", padx=(12, 0))
        lan_frame.columnconfigure(0, weight=1)

        ttk.Button(
            lan_frame,
            text=translate(_("Host Game")),
            command=self._host_game_dialog,
        ).grid(row=0, column=0, sticky="ew", pady=(0, 12))
        ttk.Button(
            lan_frame,
            text=translate(_("Join Game")),
            command=self._join_game_dialog,
        ).grid(row=1, column=0, sticky="ew")

        locale_frame = ttk.LabelFrame(self, text=translate(_("Language")), padding=20)
        locale_frame.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(16, 0))
        locale_frame.columnconfigure(0, weight=1)
        locale_frame.columnconfigure(1, weight=1)

        ttk.Button(
            locale_frame,
            text=translate(_("English")),
            command=lambda: on_set_locale("en"),
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ttk.Button(
            locale_frame,
            text=translate(_("Russian")),
            command=lambda: on_set_locale("ru"),
        ).grid(row=0, column=1, sticky="ew", padx=(6, 0))

        ttk.Button(
            self,
            text=translate(_("Exit")),
            command=on_exit,
        ).grid(row=4, column=0, columnspan=2, pady=(24, 0))

        self._localizer = localizer
        self._on_exit = on_exit
        self._root = master

    def _host_game_dialog(self) -> None:
        """Ask for port and relaunch as server."""
        dialog = tk.Toplevel(self)
        dialog.title(self._localizer.gettext(_("Host LAN Game")))
        dialog.transient(self)
        dialog.grab_set()

        ttk.Label(dialog, text=self._localizer.gettext(_("Port:"))).grid(row=0, column=0, padx=10, pady=10)
        port_entry = ttk.Entry(dialog)
        port_entry.grid(row=0, column=1, padx=10, pady=10)
        port_entry.insert(0, "8765")

        def do_host() -> None:
            port = port_entry.get().strip()
            if not port.isdigit():
                messagebox.showerror("Error", "Port must be a number")
                return
            dialog.destroy()
            self._restart_as_server(port)

        ttk.Button(dialog, text=self._localizer.gettext(_("Host")), command=do_host).grid(row=1, column=0, columnspan=2, pady=10)

    def _join_game_dialog(self) -> None:
        """Ask for IP and port and relaunch as client."""
        dialog = tk.Toplevel(self)
        dialog.title(self._localizer.gettext(_("Join LAN Game")))
        dialog.transient(self)
        dialog.grab_set()

        ttk.Label(dialog, text=self._localizer.gettext(_("Host IP:"))).grid(row=0, column=0, padx=10, pady=5)
        ip_entry = ttk.Entry(dialog, width=20)
        ip_entry.grid(row=0, column=1, padx=10, pady=5)
        ip_entry.insert(0, "192.168.1.")

        ttk.Label(dialog, text=self._localizer.gettext(_("Port:"))).grid(row=1, column=0, padx=10, pady=5)
        port_entry = ttk.Entry(dialog)
        port_entry.grid(row=1, column=1, padx=10, pady=5)
        port_entry.insert(0, "8765")

        def do_join() -> None:
            ip = ip_entry.get().strip()
            port = port_entry.get().strip()
            if not ip or not port.isdigit():
                messagebox.showerror("Error", "Valid IP and port required")
                return
            dialog.destroy()
            self._restart_as_client(ip, port)

        ttk.Button(dialog, text=self._localizer.gettext(_("Join")), command=do_join).grid(row=2, column=0, columnspan=2, pady=10)

    def _restart_as_server(self, port: str) -> None:
        """Close current app and launch new instance in server mode."""
        args = [sys.executable, "-m", "nardy", "--server", "--socket-port", port, "--locale", self._localizer.locale_code]
        self._launch_and_exit(args)

    def _restart_as_client(self, host: str, port: str) -> None:
        """Close current app and launch new instance in client mode."""
        args = [sys.executable, "-m", "nardy", "--join", "--socket-host", host, "--socket-port", port, "--locale", self._localizer.locale_code]
        self._launch_and_exit(args)

    def _launch_and_exit(self, args: list[str]) -> None:
        """Start a new process and close the current one."""
        try:
            subprocess.Popen(args)
        except Exception as e:
            messagebox.showerror("Error", f"Cannot start new process: {e}")
            return
        self._on_exit()
