"""Beautiful main menu with photo background and floating buttons."""

from __future__ import annotations

import subprocess
import sys
import tkinter as tk
from collections.abc import Callable
from tkinter import messagebox, ttk

from nardy.i18n import Localizer, gettext_noop as _

try:
    from nardy.ui.textures import menu_background, set_theme, THEMES
    from PIL import ImageEnhance, ImageTk
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False


class MainMenuScreen(ttk.Frame):
    """Main menu with photo background and separated floating buttons."""

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
        super().__init__(master)
        translate = localizer.gettext

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self._canvas = tk.Canvas(self, highlightthickness=0, bg="#2a1508")
        self._canvas.grid(row=0, column=0, sticky="nsew")
        self._canvas.bind("<Configure>", self._on_resize)
        self._bg_photo = None
        self._photo_refs: list = []

        # Title bar
        title_frame = tk.Frame(self._canvas, bg="#4a2a15", padx=24, pady=8)
        title_frame.place(relx=0.5, rely=0.08, anchor="n")
        tk.Label(
            title_frame, text=translate(_("Nardy")),
            font=("Georgia", 32, "bold"), fg="#f0dfc0", bg="#4a2a15",
        ).pack()
        tk.Label(
            title_frame, text=translate(_("Choose a mode")),
            font=("Georgia", 11), fg="#b89870", bg="#4a2a15",
        ).pack()

        # Individual floating buttons
        btn_kw = {
            "font": ("Georgia", 15, "bold"), "fg": "#f0dfc0",
            "bg": "#5a3820", "activebackground": "#6a4830",
            "activeforeground": "#ffe8c0",
            "relief": "raised", "bd": 2, "padx": 28, "pady": 10,
            "cursor": "hand2",
        }
        small_kw = {**btn_kw, "font": ("Georgia", 12), "padx": 18, "pady": 6}

        self._btn_long = tk.Button(
            self._canvas, text=translate(_("Long backgammon")),
            command=on_start_long, **btn_kw,
        )
        self._btn_long.place(relx=0.5, rely=0.35, anchor="center")

        self._btn_short = tk.Button(
            self._canvas, text=translate(_("Short backgammon")),
            command=on_start_short, **btn_kw,
        )
        self._btn_short.place(relx=0.5, rely=0.47, anchor="center")

        self._btn_host = tk.Button(
            self._canvas, text=translate(_("Host Game")),
            command=self._host_game_dialog, **small_kw,
        )
        self._btn_host.place(relx=0.35, rely=0.60, anchor="center")

        self._btn_join = tk.Button(
            self._canvas, text=translate(_("Join Game")),
            command=self._join_game_dialog, **small_kw,
        )
        self._btn_join.place(relx=0.65, rely=0.60, anchor="center")

        # Language buttons — small, at bottom
        lang_kw = {
            "font": ("Georgia", 10), "fg": "#d4c0a0",
            "bg": "#3a2012", "activebackground": "#4a3020",
            "relief": "flat", "bd": 0, "padx": 10, "pady": 3,
            "cursor": "hand2",
        }
        lang_frame = tk.Frame(self._canvas, bg="#3a2012")
        lang_frame.place(relx=0.5, rely=0.75, anchor="center")
        for text, code in [("Русский", "ru"), ("English", "en"), ("Հայերեն", "hy")]:
            tk.Button(
                lang_frame, text=text,
                command=lambda c=code: on_set_locale(c), **lang_kw,
            ).pack(side="left", padx=6)

        # Theme selector
        if _HAS_PIL:
            from nardy.ui.textures import get_theme
            theme_frame = tk.Frame(self._canvas, bg="#3a2012")
            theme_frame.place(relx=0.5, rely=0.82, anchor="center")
            tk.Label(
                theme_frame, text="Стиль:",
                font=("Georgia", 10), fg="#a08860", bg="#3a2012",
            ).pack(side="left", padx=(0, 8))
            _theme_labels = {"bone": translate(_("Bone")), "wood": translate(_("Wood"))}
            self._theme_btns: dict[str, tk.Button] = {}
            for key, theme in THEMES.items():
                active = key == get_theme()
                btn = tk.Button(
                    theme_frame, text=_theme_labels.get(key, theme["label"]),
                    command=lambda k=key: self._select_theme(k),
                    font=("Georgia", 10, "bold" if active else ""),
                    fg="#ffe8c0" if active else "#a08860",
                    bg="#6a4830" if active else "#3a2012",
                    activebackground="#6a4830", relief="raised" if active else "flat",
                    bd=2 if active else 0, padx=12, pady=3, cursor="hand2",
                )
                btn.pack(side="left", padx=4)
                self._theme_btns[key] = btn

        # Exit
        tk.Button(
            self._canvas, text=translate(_("Exit")),
            command=on_exit,
            font=("Georgia", 11), fg="#a06040", bg="#2a1508",
            activebackground="#3a2518", relief="flat", bd=0,
            padx=16, pady=2, cursor="hand2",
        ).place(relx=0.5, rely=0.90, anchor="center")

        self._localizer = localizer
        self._on_exit = on_exit
        self._root = master

    def _select_theme(self, key: str) -> None:
        from nardy.ui.textures import get_theme
        set_theme(key)
        for k, btn in self._theme_btns.items():
            active = k == get_theme()
            btn.config(
                font=("Georgia", 10, "bold" if active else ""),
                fg="#ffe8c0" if active else "#a08860",
                bg="#6a4830" if active else "#3a2012",
                relief="raised" if active else "flat",
                bd=2 if active else 0,
            )

    def _on_resize(self, event: tk.Event) -> None:
        if not _HAS_PIL:
            return
        w = max(event.width, 100)
        h = max(event.height, 100)
        try:
            bg = menu_background(w, h)
            bg = ImageEnhance.Brightness(bg).enhance(0.55)
            self._bg_photo = ImageTk.PhotoImage(bg)
            self._canvas.delete("bg")
            self._canvas.create_image(0, 0, anchor="nw", image=self._bg_photo, tags=("bg",))
            self._canvas.tag_lower("bg")
        except Exception:
            pass

    def _host_game_dialog(self) -> None:
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
            args = [sys.executable, "-m", "nardy", "--server", "--socket-port", port, "--locale", self._localizer.locale_code]
            self._launch_and_exit(args)

        ttk.Button(dialog, text=self._localizer.gettext(_("Host")), command=do_host).grid(row=1, column=0, columnspan=2, pady=10)

    def _join_game_dialog(self) -> None:
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
            args = [sys.executable, "-m", "nardy", "--join", "--socket-host", ip, "--socket-port", port, "--locale", self._localizer.locale_code]
            self._launch_and_exit(args)

        ttk.Button(dialog, text=self._localizer.gettext(_("Join")), command=do_join).grid(row=2, column=0, columnspan=2, pady=10)

    def _launch_and_exit(self, args: list[str]) -> None:
        try:
            subprocess.Popen(args)
        except Exception as e:
            messagebox.showerror("Error", f"Cannot start new process: {e}")
            return
        self._on_exit()
