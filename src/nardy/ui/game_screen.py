"""Interactive Tkinter game screen for local two-player gameplay."""

from __future__ import annotations

import tkinter as tk
from collections import defaultdict
from collections.abc import Callable
from tkinter import ttk

from nardy.app.presentation import GameScreenData
from nardy.domain.models import (
    BAR_POSITION,
    OFF_POSITION,
    GameMode,
    GameState,
    Move,
    Player,
)
from nardy.i18n import Localizer, gettext_noop as _

POINT_SIZE = 62
CHECKER_SIZE = 20
TOP_Y = 54
BOTTOM_Y = 426
CANVAS_WIDTH = 940
CANVAS_HEIGHT = 480
LEFT_MARGIN = 26
CENTER_LANE_WIDTH = 140
POINT_RECT_PADDING = 6


class GameScreen(ttk.Frame):
    """Render interactive board, controls and move hints."""

    def __init__(
        self,
        master: tk.Misc,
        localizer: Localizer,
        data: GameScreenData,
        state: GameState,
        last_move: Move | None,
        on_roll_dice: Callable[[], None],
        on_apply_move: Callable[[Move], None],
        on_undo: Callable[[], None],
        on_back_to_menu: Callable[[], None],
    ) -> None:
        """Create the board and bind player actions."""
        super().__init__(master, padding=16)
        self._translate = localizer.gettext
        self._state = state
        self._on_move_selected = on_apply_move
        self._selected_source: int | None = None
        self._moves_by_source = self._index_moves(state.turn.legal_moves)

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        header = ttk.Frame(self)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        header.columnconfigure(0, weight=1)
        header.columnconfigure(1, weight=1)
        ttk.Label(
            header,
            text=data.title,
            font=("Segoe UI", 22, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            text=data.subtitle,
            anchor=tk.E,
        ).grid(row=0, column=1, sticky="e")
        ttk.Label(
            header,
            text=f"{data.status}   {data.dice}",
            anchor=tk.W,
        ).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 0))

        board_frame = ttk.Frame(self)
        board_frame.grid(row=1, column=0, sticky="nsew")
        board_frame.columnconfigure(0, weight=1)
        board_frame.rowconfigure(0, weight=1)

        self._canvas = tk.Canvas(
            board_frame,
            width=CANVAS_WIDTH,
            height=CANVAS_HEIGHT,
            bg="#f6e5c8",
            highlightthickness=1,
            highlightbackground="#4a3b2f",
        )
        self._canvas.grid(row=0, column=0, sticky="nsew")

        self._draw_board()
        self._draw_checkers()
        self._draw_highlights()

        controls = ttk.Frame(self)
        controls.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        controls.columnconfigure(0, weight=1)
        controls.columnconfigure(1, weight=1)
        controls.columnconfigure(2, weight=1)

        ttk.Button(
            controls,
            text=self._translate(_("Roll dice")),
            command=on_roll_dice,
            state=tk.NORMAL if data.can_roll else tk.DISABLED,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ttk.Button(
            controls,
            text=self._translate(_("Undo")),
            command=on_undo,
            state=tk.NORMAL if data.can_undo else tk.DISABLED,
        ).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(
            controls,
            text=self._translate(_("Back to menu")),
            command=on_back_to_menu,
        ).grid(row=0, column=2, sticky="ew", padx=(6, 0))

        if last_move is not None:
            self.after(20, lambda: self._animate_move(last_move))

    @staticmethod
    def _index_moves(moves: tuple[Move, ...]) -> dict[int, tuple[Move, ...]]:
        """Group legal moves by source point for click handling."""
        grouped: defaultdict[int, list[Move]] = defaultdict(list)
        for move in moves:
            grouped[move.source].append(move)
        return {source: tuple(source_moves) for source, source_moves in grouped.items()}

    def _draw_board(self) -> None:
        """Draw static board geometry and clickable hitboxes."""
        self._canvas.delete("board")
        self._canvas.create_rectangle(
            0,
            0,
            CANVAS_WIDTH,
            CANVAS_HEIGHT,
            fill="#f6e5c8",
            outline="",
            tags=("board",),
        )
        self._canvas.create_line(
            0,
            CANVAS_HEIGHT / 2,
            CANVAS_WIDTH,
            CANVAS_HEIGHT / 2,
            fill="#8a755c",
            width=2,
            tags=("board",),
        )

        for point in range(1, 25):
            x1, y1, x2, y2 = self._point_rect(point)
            self._canvas.create_rectangle(
                x1,
                y1,
                x2,
                y2,
                fill="#e7d0ab",
                outline="#7b6247",
                tags=("board", f"point_{point}"),
            )
            self._canvas.create_text(
                (x1 + x2) / 2,
                y1 - 10 if point >= 13 else y2 + 10,
                text=str(point),
                fill="#3e3024",
                font=("Segoe UI", 9),
                tags=("board",),
            )
            self._canvas.tag_bind(
                f"point_{point}",
                "<Button-1>",
                lambda _event, point_number=point: self._on_point_click(point_number),
            )

        if self._state.mode is GameMode.SHORT:
            bar_x1, _, bar_x2, _ = self._bar_zone_rect()
            self._canvas.create_rectangle(
                bar_x1,
                16,
                bar_x2,
                CANVAS_HEIGHT - 16,
                fill="#cdb089",
                outline="#6b5137",
                tags=("board", "bar_zone"),
            )
            self._canvas.tag_bind(
                "bar_zone",
                "<Button-1>",
                lambda _event: self._on_point_click(BAR_POSITION),
            )
        top_off = self._off_zone_rect(top=True)
        bottom_off = self._off_zone_rect(top=False)
        self._canvas.create_rectangle(
            *top_off,
            fill="#d9c3a0",
            outline="#6b5137",
            tags=("board", "off_top"),
        )
        self._canvas.create_rectangle(
            *bottom_off,
            fill="#d9c3a0",
            outline="#6b5137",
            tags=("board", "off_bottom"),
        )
        self._canvas.tag_bind(
            "off_top",
            "<Button-1>",
            lambda _event: self._on_point_click(OFF_POSITION),
        )
        self._canvas.tag_bind(
            "off_bottom",
            "<Button-1>",
            lambda _event: self._on_point_click(OFF_POSITION),
        )

    def _draw_checkers(self) -> None:
        """Render point stacks, bar checkers and borne-off counters."""
        self._canvas.delete("checker")
        for point in range(1, 25):
            point_state = self._state.point(point)
            if point_state.checkers == 0:
                continue
            self._draw_stack(point, point_state.owner, point_state.checkers)

        self._draw_bar_stack(
            Player.WHITE,
            self._state.bar_for(Player.WHITE),
            True,
        )
        self._draw_bar_stack(
            Player.BLACK,
            self._state.bar_for(Player.BLACK),
            False,
        )
        self._draw_off_counter(
            Player.WHITE,
            self._state.borne_off_for(Player.WHITE),
            True,
        )
        self._draw_off_counter(
            Player.BLACK,
            self._state.borne_off_for(Player.BLACK),
            False,
        )

    def _draw_stack(self, point: int, owner: Player | None, count: int) -> None:
        """Draw a checker stack for one board point."""
        if owner is None:
            return
        x1, y1, x2, y2 = self._point_rect(point)
        center_x = (x1 + x2) / 2
        step = CHECKER_SIZE + 2
        max_visible = min(5, count)
        color = "#f2f2f2" if owner is Player.WHITE else "#333333"
        outline = "#4b4b4b" if owner is Player.WHITE else "#d6d6d6"
        for index in range(max_visible):
            if point >= 13:
                cy = y1 + 14 + index * step
            else:
                cy = y2 - 14 - index * step
            self._canvas.create_oval(
                center_x - CHECKER_SIZE / 2,
                cy - CHECKER_SIZE / 2,
                center_x + CHECKER_SIZE / 2,
                cy + CHECKER_SIZE / 2,
                fill=color,
                outline=outline,
                width=2,
                tags=("checker",),
            )
        if count > max_visible:
            self._canvas.create_text(
                center_x,
                y1 + 18 if point >= 13 else y2 - 18,
                text=f"x{count}",
                fill="#aa2e2e",
                font=("Segoe UI", 9, "bold"),
                tags=("checker",),
            )

    def _draw_bar_stack(self, player: Player, count: int, top: bool) -> None:
        """Draw bar checkers for one player."""
        if self._state.mode is not GameMode.SHORT:
            return
        if count <= 0:
            return
        bar_x1, _, bar_x2, _ = self._bar_zone_rect()
        center_x = (bar_x1 + bar_x2) / 2
        base_y = 70 if top else CANVAS_HEIGHT - 70
        step = CHECKER_SIZE + 2
        max_visible = min(count, 4)
        color = "#f2f2f2" if player is Player.WHITE else "#333333"
        outline = "#4b4b4b" if player is Player.WHITE else "#d6d6d6"
        for index in range(max_visible):
            cy = base_y + index * step if top else base_y - index * step
            self._canvas.create_oval(
                center_x - CHECKER_SIZE / 2,
                cy - CHECKER_SIZE / 2,
                center_x + CHECKER_SIZE / 2,
                cy + CHECKER_SIZE / 2,
                fill=color,
                outline=outline,
                width=2,
                tags=("checker",),
            )
        self._canvas.create_text(
            center_x,
            24 if top else CANVAS_HEIGHT - 24,
            text=f"{self._translate(_('Bar'))} {count}",
            fill="#3b2b1f",
            font=("Segoe UI", 9, "bold"),
            tags=("checker",),
        )

    def _draw_off_counter(self, player: Player, count: int, top: bool) -> None:
        """Draw borne-off counter for one player."""
        text = (
            self._translate(_("White"))
            if player is Player.WHITE
            else self._translate(_("Black"))
        )
        zone = self._off_zone_rect(top=top)
        self._canvas.create_text(
            (zone[0] + zone[2]) / 2,
            (zone[1] + zone[3]) / 2,
            text=f"{text}: {count}",
            fill="#33261b",
            font=("Segoe UI", 10, "bold"),
            tags=("checker",),
        )

    def _draw_highlights(self) -> None:
        """Highlight legal source and target points."""
        self._canvas.delete("highlight")
        legal_sources = set(self._moves_by_source)
        for source in legal_sources:
            if source == BAR_POSITION:
                if self._state.mode is GameMode.SHORT:
                    self._canvas.create_rectangle(
                        *self._bar_zone_rect(y_padding=2),
                        outline="#2f9954",
                        width=3,
                        tags=("highlight",),
                    )
                continue
            x1, y1, x2, y2 = self._point_rect(source)
            self._canvas.create_rectangle(
                x1 + 2,
                y1 + 2,
                x2 - 2,
                y2 - 2,
                outline="#2f9954",
                width=3,
                tags=("highlight",),
            )

        if self._selected_source is None:
            return
        if self._selected_source != BAR_POSITION:
            x1, y1, x2, y2 = self._point_rect(self._selected_source)
            self._canvas.create_rectangle(
                x1 + 4,
                y1 + 4,
                x2 - 4,
                y2 - 4,
                outline="#f3a531",
                width=3,
                tags=("highlight",),
            )
        for move in self._moves_by_source.get(self._selected_source, ()):
            if move.target == OFF_POSITION:
                off_zone = self._off_zone_rect(
                    top=move.player is Player.WHITE
                )
                self._canvas.create_rectangle(
                    *off_zone,
                    outline="#1a73c8",
                    width=3,
                    tags=("highlight",),
                )
                continue
            x1, y1, x2, y2 = self._point_rect(move.target)
            self._canvas.create_rectangle(
                x1 + 8,
                y1 + 8,
                x2 - 8,
                y2 - 8,
                outline="#1a73c8",
                width=3,
                tags=("highlight",),
            )

    def _on_point_click(self, point: int) -> None:
        """Handle source/target point click for move selection."""
        if not self._moves_by_source:
            return
        if self._selected_source is None:
            if point in self._moves_by_source:
                self._selected_source = point
                self._draw_highlights()
            return

        candidate = next(
            (
                move
                for move in self._moves_by_source.get(self._selected_source, ())
                if move.target == point
                or (point == OFF_POSITION and move.target == OFF_POSITION)
            ),
            None,
        )
        if (
            candidate is None
            and point in self._moves_by_source
            and point != self._selected_source
        ):
            self._selected_source = point
            self._draw_highlights()
            return
        if candidate is None and point == self._selected_source:
            source_moves = self._moves_by_source.get(point, ())
            if len(source_moves) == 1:
                self._submit_move(source_moves[0])
                return
            self._selected_source = None
            self._draw_highlights()
            return
        if candidate is None:
            self._selected_source = None
            self._draw_highlights()
            return
        self._submit_move(candidate)

    def _submit_move(self, move: Move) -> None:
        """Forward the selected move to the controller callback."""
        self._on_move_selected(move)

    def _animate_move(self, move: Move) -> None:
        """Draw a tiny movement animation and optional explosion marker."""
        start = self._point_center(move.source, move.player)
        end = self._point_center(move.target, move.player)
        token = self._canvas.create_oval(
            start[0] - 8,
            start[1] - 8,
            start[0] + 8,
            start[1] + 8,
            fill="#e64b3a",
            outline="#ffffff",
            width=2,
            tags=("anim",),
        )
        steps = 9

        def _step(index: int) -> None:
            if index > steps:
                self._canvas.delete(token)
                if move.captures:
                    self._explode_capture(end)
                    return
                if move.bears_off:
                    self._explode(end)
                return
            progress = index / steps
            nx = start[0] + (end[0] - start[0]) * progress
            ny = start[1] + (end[1] - start[1]) * progress
            self._canvas.coords(token, nx - 8, ny - 8, nx + 8, ny + 8)
            self.after(20, lambda: _step(index + 1))

        _step(0)

    def _explode(self, center: tuple[float, float]) -> None:
        """Render a bright expanding explosion pulse."""
        ring = self._canvas.create_oval(
            center[0],
            center[1],
            center[0],
            center[1],
            outline="#ff7a1a",
            width=3,
            tags=("anim",),
        )
        halo = self._canvas.create_oval(
            center[0],
            center[1],
            center[0],
            center[1],
            outline="#ffd166",
            width=2,
            tags=("anim",),
        )
        sparks = []
        for _spark_index in range(8):
            spark = self._canvas.create_line(
                center[0],
                center[1],
                center[0],
                center[1],
                fill="#ff533d",
                width=2,
                tags=("anim",),
            )
            sparks.append(spark)

        def _expand(radius: int) -> None:
            if radius > 28:
                self._canvas.delete(ring)
                self._canvas.delete(halo)
                for spark in sparks:
                    self._canvas.delete(spark)
                return
            self._canvas.coords(
                ring,
                center[0] - radius,
                center[1] - radius,
                center[0] + radius,
                center[1] + radius,
            )
            self._canvas.coords(
                halo,
                center[0] - radius / 2,
                center[1] - radius / 2,
                center[0] + radius / 2,
                center[1] + radius / 2,
            )
            for index, spark in enumerate(sparks):
                dx = radius * (1 if index % 2 == 0 else -1) * (0.35 + 0.1 * index)
                dy = radius * (1 if index < 4 else -1) * (0.25 + 0.08 * index)
                self._canvas.coords(
                    spark,
                    center[0],
                    center[1],
                    center[0] + dx,
                    center[1] + dy,
                )
            self.after(18, lambda: _expand(radius + 4))

        _expand(2)

    def _explode_capture(self, center: tuple[float, float]) -> None:
        """Render a stronger explosion for captured enemy checkers."""
        core = self._canvas.create_oval(
            center[0] - 4,
            center[1] - 4,
            center[0] + 4,
            center[1] + 4,
            fill="#ff3b30",
            outline="#ffe08a",
            width=2,
            tags=("anim",),
        )
        ring_outer = self._canvas.create_oval(
            center[0],
            center[1],
            center[0],
            center[1],
            outline="#ff6a00",
            width=4,
            tags=("anim",),
        )
        ring_inner = self._canvas.create_oval(
            center[0],
            center[1],
            center[0],
            center[1],
            outline="#ffd166",
            width=3,
            tags=("anim",),
        )
        sparks = []
        for _spark_index in range(12):
            spark = self._canvas.create_line(
                center[0],
                center[1],
                center[0],
                center[1],
                fill="#ff533d",
                width=2,
                tags=("anim",),
            )
            sparks.append(spark)

        def _burst(radius: int) -> None:
            if radius > 36:
                self._canvas.delete(core)
                self._canvas.delete(ring_outer)
                self._canvas.delete(ring_inner)
                for spark in sparks:
                    self._canvas.delete(spark)
                return

            # Pulsing core and two expanding rings.
            glow = 4 + (radius % 8) / 2
            self._canvas.coords(
                core,
                center[0] - glow,
                center[1] - glow,
                center[0] + glow,
                center[1] + glow,
            )
            self._canvas.coords(
                ring_outer,
                center[0] - radius,
                center[1] - radius,
                center[0] + radius,
                center[1] + radius,
            )
            self._canvas.coords(
                ring_inner,
                center[0] - radius * 0.6,
                center[1] - radius * 0.6,
                center[0] + radius * 0.6,
                center[1] + radius * 0.6,
            )

            for index, spark in enumerate(sparks):
                dx = radius * (0.2 + (index % 6) * 0.12)
                dy = radius * (0.2 + (index // 6) * 0.28)
                if index % 2:
                    dx = -dx
                if index >= 6:
                    dy = -dy
                self._canvas.coords(
                    spark,
                    center[0],
                    center[1],
                    center[0] + dx,
                    center[1] + dy,
                )

            self.after(16, lambda: _burst(radius + 5))

        _burst(2)

    def _point_rect(self, point: int) -> tuple[float, float, float, float]:
        """Return the clickable rectangle for a board point."""
        if point >= 13:
            row = 0
            index = point - 13
        else:
            row = 1
            index = 12 - point

        if index < 6:
            x1 = LEFT_MARGIN + index * POINT_SIZE
        else:
            right_index = index - 6
            x1 = (
                LEFT_MARGIN
                + (6 * POINT_SIZE)
                + CENTER_LANE_WIDTH
                + right_index * POINT_SIZE
            )
        x2 = x1 + POINT_SIZE - POINT_RECT_PADDING
        if row == 0:
            return (x1, 24, x2, CANVAS_HEIGHT / 2 - 6)
        return (x1, CANVAS_HEIGHT / 2 + 6, x2, CANVAS_HEIGHT - 24)

    def _point_center(self, point: int, player: Player) -> tuple[float, float]:
        """Return animation center for source or target point."""
        if point == BAR_POSITION:
            bar_x1, _, bar_x2, _ = self._bar_zone_rect()
            return (
                (bar_x1 + bar_x2) / 2,
                TOP_Y if player is Player.WHITE else BOTTOM_Y,
            )
        if point == OFF_POSITION:
            off_zone = self._off_zone_rect(top=player is Player.WHITE)
            return ((off_zone[0] + off_zone[2]) / 2, (off_zone[1] + off_zone[3]) / 2)
        x1, y1, x2, y2 = self._point_rect(point)
        return ((x1 + x2) / 2, y1 + 24 if point >= 13 else y2 - 24)

    def _off_zone_rect(self, top: bool) -> tuple[float, float, float, float]:
        """Return top or bottom borne-off tray rectangle."""
        lane_start = LEFT_MARGIN + 6 * POINT_SIZE
        if self._state.mode is GameMode.LONG:
            # In long mode there is no bar, so use a wider centered tray.
            x1 = lane_start + (CENTER_LANE_WIDTH - 104) / 2
            x2 = x1 + 104
        else:
            # In short mode keep trays on the left side of center lane.
            x1 = lane_start + 8
            x2 = x1 + 70
        if top:
            return (x1, 18, x2, 104)
        return (x1, CANVAS_HEIGHT - 104, x2, CANVAS_HEIGHT - 18)

    @staticmethod
    def _bar_zone_rect(y_padding: int = 0) -> tuple[float, float, float, float]:
        """Return centered bar rectangle shifted right in short mode."""
        lane_start = LEFT_MARGIN + 6 * POINT_SIZE
        x1 = lane_start + CENTER_LANE_WIDTH - 42
        x2 = lane_start + CENTER_LANE_WIDTH - 6
        return (
            x1,
            16 - y_padding,
            x2,
            CANVAS_HEIGHT - 16 + y_padding,
        )
