"""Interactive Tkinter game screen for local two-player gameplay."""

from __future__ import annotations

import random
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
        self._on_roll_dice_callback = on_roll_dice
        self._on_move_selected = on_apply_move
        self._selected_source: int | None = None
        self._moves_by_source = self._index_moves(state.turn.legal_moves)

        # Animation attributes
        self._dice_anim_id: str | None = None
        self._dice_anim_step = 0
        self._dice_anim_max_steps = 12
        self._destroyed = False  # флаг для предотвращения ошибок после уничтожения

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
            text=f"{data.status}",
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

        # Dice display area (custom drawing)
        self._dice_canvas = tk.Canvas(
            header,
            width=160,
            height=80,
            bg="#f0e0c0",
            highlightthickness=1,
            highlightbackground="#8a755c",
        )
        self._dice_canvas.grid(row=0, column=2, rowspan=2, padx=(20, 0), pady=(4, 0))
        self._draw_dice_from_state()

        controls = ttk.Frame(self)
        controls.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        controls.columnconfigure(0, weight=1)
        controls.columnconfigure(1, weight=1)
        controls.columnconfigure(2, weight=1)

        self._roll_button = ttk.Button(
            controls,
            text=self._translate(_("Roll dice")),
            command=self._on_roll_button_click,
            state=tk.NORMAL if data.can_roll else tk.DISABLED,
        )
        self._roll_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))
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

    def destroy(self) -> None:
        """Clean up animations and destroy the widget."""
        self._destroyed = True
        if self._dice_anim_id is not None:
            try:
                self.after_cancel(self._dice_anim_id)
            except Exception:
                pass
        super().destroy()

    def _on_roll_button_click(self) -> None:
        """Handle roll button click with dice animation."""
        if self._dice_anim_id is not None or self._destroyed:
            return
        try:
            self._roll_button.config(state=tk.DISABLED)
        except tk.TclError:
            return  # кнопка уже уничтожена
        self._start_dice_animation()

    def _start_dice_animation(self) -> None:
        """Start dice rolling animation with explosion at the end."""
        self._dice_anim_step = 0

        def step() -> None:
            if self._destroyed:
                return
            d1 = random.randint(1, 6)
            d2 = random.randint(1, 6)
            self._draw_dice_on_canvas(d1, d2)
            self._dice_anim_step += 1
            if self._dice_anim_step < self._dice_anim_max_steps:
                self._dice_anim_id = self.after(70, step)
            else:
                self._dice_anim_id = None
                # Взрывная вспышка на кубиках
                self._dice_explosion()
                # Реальный бросок через движок
                self._on_roll_dice_callback()
                # Восстанавливаем кнопку только если виджет ещё жив
                if not self._destroyed:
                    try:
                        self._roll_button.config(state=tk.NORMAL)
                    except tk.TclError:
                        pass
                self.after(50, self._draw_dice_from_state)

        step()

    def _dice_explosion(self) -> None:
        """Show an explosion effect on the dice canvas."""
        if self._destroyed:
            return
        try:
            flash = self._dice_canvas.create_rectangle(
                0, 0, 160, 80,
                fill="#ffaa33", outline="", stipple="gray50",
                tags="dice_flash",
            )
            sparks = []
            for _ in range(25):
                x = random.randint(10, 150)
                y = random.randint(10, 70)
                spark = self._dice_canvas.create_oval(
                    x - 5, y - 5, x + 5, y + 5,
                    fill=random.choice(["#ff8800", "#ff5500", "#ffcc00"]),
                    outline="#ff3300", tags="dice_flash",
                )
                sparks.append(spark)
            # Удалить через 500 мс
            self.after(500, lambda: self._dice_canvas.delete("dice_flash"))
        except tk.TclError:
            pass

    def _draw_dice_on_canvas(self, value1: int, value2: int) -> None:
        """Draw two dice with pips on the dice canvas."""
        if self._destroyed:
            return
        try:
            self._dice_canvas.delete("dice")
        except tk.TclError:
            return
        w = 60
        h = 60
        margin = 10
        x1 = margin
        y1 = (80 - h) // 2
        self._draw_single_die(x1, y1, w, h, value1)
        x2 = x1 + w + margin
        self._draw_single_die(x2, y1, w, h, value2)

    def _draw_single_die(self, x: int, y: int, w: int, h: int, value: int) -> None:
        """Draw one die with rounded corners and pips."""
        try:
            self._dice_canvas.create_rectangle(
                x, y, x + w, y + h,
                fill="#ffffff", outline="#333333", width=2,
                tags="dice",
            )
            self._dice_canvas.create_rectangle(
                x + 2, y + 2, x + w - 2, y + h - 2,
                fill="#fafafa", outline="", tags="dice",
            )
            pip_positions = {
                1: [(w//2, h//2)],
                2: [(w//4, h//4), (3*w//4, 3*h//4)],
                3: [(w//4, h//4), (w//2, h//2), (3*w//4, 3*h//4)],
                4: [(w//4, h//4), (3*w//4, h//4), (w//4, 3*h//4), (3*w//4, 3*h//4)],
                5: [(w//4, h//4), (3*w//4, h//4), (w//2, h//2), (w//4, 3*h//4), (3*w//4, 3*h//4)],
                6: [(w//4, h//4), (3*w//4, h//4), (w//4, h//2), (3*w//4, h//2), (w//4, 3*h//4), (3*w//4, 3*h//4)],
            }
            for cx, cy in pip_positions[value]:
                self._dice_canvas.create_oval(
                    x + cx - 6, y + cy - 6,
                    x + cx + 6, y + cy + 6,
                    fill="#222222", outline="#111111", tags="dice",
                )
                self._dice_canvas.create_oval(
                    x + cx - 4, y + cy - 4,
                    x + cx + 2, y + cy + 2,
                    fill="#555555", outline="", tags="dice",
                )
        except tk.TclError:
            pass

    def _draw_dice_from_state(self) -> None:
        """Redraw dice from current game state."""
        if self._destroyed:
            return
        dice = self._state.turn.dice
        if dice is None:
            try:
                self._dice_canvas.delete("dice")
            except tk.TclError:
                pass
            return
        d1, d2 = dice.values
        self._draw_dice_on_canvas(d1, d2)

    @staticmethod
    def _index_moves(moves: tuple[Move, ...]) -> dict[int, tuple[Move, ...]]:
        """Group legal moves by source point for click handling."""
        grouped: defaultdict[int, list[Move]] = defaultdict(list)
        for move in moves:
            grouped[move.source].append(move)
        return {source: tuple(source_moves) for source, source_moves in grouped.items()}

    def _draw_board(self) -> None:
        """Draw static board geometry and clickable hitboxes with better visuals."""
        self._canvas.delete("board")
        self._canvas.create_rectangle(
            0, 0, CANVAS_WIDTH, CANVAS_HEIGHT,
            fill="#e8d5b0", outline="", tags=("board",),
        )
        for i in range(0, CANVAS_WIDTH, 40):
            self._canvas.create_line(
                i, 0, i + 20, CANVAS_HEIGHT,
                fill="#d4be8a", width=1, tags=("board",),
            )
        self._canvas.create_line(
            0, CANVAS_HEIGHT / 2, CANVAS_WIDTH, CANVAS_HEIGHT / 2,
            fill="#8a755c", width=4, tags=("board",),
        )
        self._canvas.create_rectangle(
            4, 4, CANVAS_WIDTH - 4, CANVAS_HEIGHT - 4,
            outline="#5c4733", width=4, tags=("board",),
        )

        for point in range(1, 25):
            x1, y1, x2, y2 = self._point_rect(point)
            fill = "#e7d0ab" if (point % 2 == 0) else "#dbbc87"
            self._canvas.create_rectangle(
                x1, y1, x2, y2,
                fill=fill, outline="#7b6247", width=2,
                tags=("board", f"point_{point}"),
            )
            self._canvas.create_rectangle(
                x1 + 2, y1 + 2, x2 - 2, y2 - 2,
                fill="", outline="#cbaa77", width=1, tags=("board",),
            )
            self._canvas.create_text(
                (x1 + x2) / 2,
                y1 - 10 if point >= 13 else y2 + 10,
                text=str(point),
                fill="#3e3024",
                font=("Segoe UI", 9, "bold"),
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
                bar_x1, 16, bar_x2, CANVAS_HEIGHT - 16,
                fill="#cdb089", outline="#6b5137", width=2,
                tags=("board", "bar_zone"),
            )
            self._canvas.tag_bind(
                "bar_zone",
                "<Button-1>",
                lambda _event: self._on_point_click(BAR_POSITION),
            )
        top_off = self._off_zone_rect(top=True)
        bottom_off = self._off_zone_rect(top=False)
        for zone, label in ((top_off, "off_top"), (bottom_off, "off_bottom")):
            self._canvas.create_rectangle(
                *zone, fill="#d9c3a0", outline="#6b5137", width=2,
                tags=("board", label),
            )
        self._canvas.tag_bind(
            "off_top", "<Button-1>", lambda _event: self._on_point_click(OFF_POSITION),
        )
        self._canvas.tag_bind(
            "off_bottom", "<Button-1>", lambda _event: self._on_point_click(OFF_POSITION),
        )

    def _draw_checkers(self) -> None:
        """Render point stacks, bar checkers and borne-off counters with improved 3D look."""
        self._canvas.delete("checker")
        for point in range(1, 25):
            point_state = self._state.point(point)
            if point_state.checkers == 0:
                continue
            self._draw_stack(point, point_state.owner, point_state.checkers)

        self._draw_bar_stack(Player.WHITE, self._state.bar_for(Player.WHITE), True)
        self._draw_bar_stack(Player.BLACK, self._state.bar_for(Player.BLACK), False)
        self._draw_off_counter(Player.WHITE, self._state.borne_off_for(Player.WHITE), True)
        self._draw_off_counter(Player.BLACK, self._state.borne_off_for(Player.BLACK), False)

    def _draw_stack(self, point: int, owner: Player | None, count: int) -> None:
        """Draw a checker stack for one board point with 3D effect."""
        if owner is None:
            return
        x1, y1, x2, y2 = self._point_rect(point)
        center_x = (x1 + x2) / 2
        step = CHECKER_SIZE + 2
        max_visible = min(5, count)
        color_base = "#fcfcfc" if owner is Player.WHITE else "#2c2c2c"
        color_rim = "#dddddd" if owner is Player.WHITE else "#555555"
        for index in range(max_visible):
            if point >= 13:
                cy = y1 + 14 + index * step
            else:
                cy = y2 - 14 - index * step
            self._canvas.create_oval(
                center_x - CHECKER_SIZE / 2 + 2,
                cy - CHECKER_SIZE / 2 + 2,
                center_x + CHECKER_SIZE / 2 + 2,
                cy + CHECKER_SIZE / 2 + 2,
                fill="#a09070", outline="", tags=("checker",),
            )
            self._canvas.create_oval(
                center_x - CHECKER_SIZE / 2,
                cy - CHECKER_SIZE / 2,
                center_x + CHECKER_SIZE / 2,
                cy + CHECKER_SIZE / 2,
                fill=color_base, outline=color_rim, width=2,
                tags=("checker",),
            )
            self._canvas.create_oval(
                center_x - CHECKER_SIZE / 4,
                cy - CHECKER_SIZE / 3,
                center_x + CHECKER_SIZE / 4,
                cy,
                fill="#ffffff" if owner is Player.WHITE else "#888888",
                outline="", tags=("checker",),
            )
        if count > max_visible:
            self._canvas.create_text(
                center_x,
                y1 + 18 if point >= 13 else y2 - 18,
                text=f"x{count}",
                fill="#aa2e2e", font=("Segoe UI", 9, "bold"),
                tags=("checker",),
            )

    def _draw_bar_stack(self, player: Player, count: int, top: bool) -> None:
        """Draw bar checkers for one player with 3D effect."""
        if self._state.mode is not GameMode.SHORT:
            return
        if count <= 0:
            return
        bar_x1, _, bar_x2, _ = self._bar_zone_rect()
        center_x = (bar_x1 + bar_x2) / 2
        base_y = 70 if top else CANVAS_HEIGHT - 70
        step = CHECKER_SIZE + 2
        max_visible = min(count, 4)
        color_base = "#fcfcfc" if player is Player.WHITE else "#2c2c2c"
        color_rim = "#dddddd" if player is Player.WHITE else "#555555"
        for index in range(max_visible):
            cy = base_y + index * step if top else base_y - index * step
            self._canvas.create_oval(
                center_x - CHECKER_SIZE / 2 + 2,
                cy - CHECKER_SIZE / 2 + 2,
                center_x + CHECKER_SIZE / 2 + 2,
                cy + CHECKER_SIZE / 2 + 2,
                fill="#a09070", outline="", tags=("checker",),
            )
            self._canvas.create_oval(
                center_x - CHECKER_SIZE / 2,
                cy - CHECKER_SIZE / 2,
                center_x + CHECKER_SIZE / 2,
                cy + CHECKER_SIZE / 2,
                fill=color_base, outline=color_rim, width=2,
                tags=("checker",),
            )
            self._canvas.create_oval(
                center_x - CHECKER_SIZE / 4,
                cy - CHECKER_SIZE / 3,
                center_x + CHECKER_SIZE / 4,
                cy,
                fill="#ffffff" if player is Player.WHITE else "#888888",
                outline="", tags=("checker",),
            )
        self._canvas.create_text(
            center_x, 24 if top else CANVAS_HEIGHT - 24,
            text=f"bar {count}", fill="#3b2b1f", font=("Segoe UI", 9, "bold"),
            tags=("checker",),
        )

    def _draw_off_counter(self, player: Player, count: int, top: bool) -> None:
        """Draw borne-off counter for one player."""
        text = self._translate(_("White")) if player is Player.WHITE else self._translate(_("Black"))
        zone = self._off_zone_rect(top=top)
        self._canvas.create_text(
            (zone[0] + zone[2]) / 2,
            (zone[1] + zone[3]) / 2,
            text=f"{text}: {count}", fill="#33261b", font=("Segoe UI", 10, "bold"),
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
                        outline="#2f9954", width=4, tags=("highlight",),
                    )
                continue
            x1, y1, x2, y2 = self._point_rect(source)
            self._canvas.create_rectangle(
                x1 + 2, y1 + 2, x2 - 2, y2 - 2,
                outline="#2f9954", width=4, tags=("highlight",),
            )

        if self._selected_source is None:
            return
        if self._selected_source != BAR_POSITION:
            x1, y1, x2, y2 = self._point_rect(self._selected_source)
            self._canvas.create_rectangle(
                x1 + 4, y1 + 4, x2 - 4, y2 - 4,
                outline="#f3a531", width=4, tags=("highlight",),
            )
        for move in self._moves_by_source.get(self._selected_source, ()):
            if move.target == OFF_POSITION:
                off_zone = self._off_zone_rect(top=move.player is Player.WHITE)
                self._canvas.create_rectangle(
                    *off_zone, outline="#1a73c8", width=4, tags=("highlight",),
                )
                continue
            x1, y1, x2, y2 = self._point_rect(move.target)
            self._canvas.create_rectangle(
                x1 + 8, y1 + 8, x2 - 8, y2 - 8,
                outline="#1a73c8", width=4, tags=("highlight",),
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
                if move.target == point or (point == OFF_POSITION and move.target == OFF_POSITION)
            ),
            None,
        )
        if candidate is None and point in self._moves_by_source and point != self._selected_source:
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
            start[0] - 8, start[1] - 8, start[0] + 8, start[1] + 8,
            fill="#e64b3a", outline="#ffffff", width=2, tags=("anim",),
        )
        steps = 9

        def _step(index: int) -> None:
            if self._destroyed:
                return
            if index > steps:
                self._canvas.delete(token)
                if move.captures or move.bears_off:
                    self._explode(end)
                return
            progress = index / steps
            nx = start[0] + (end[0] - start[0]) * progress
            ny = start[1] + (end[1] - start[1]) * progress
            self._canvas.coords(token, nx - 8, ny - 8, nx + 8, ny + 8)
            self.after(20, lambda: _step(index + 1))

        _step(0)

    def _explode(self, center: tuple[float, float]) -> None:
        """Render an enhanced explosion effect (more sparks, flash, screen shake)."""
        if self._destroyed:
            return
        # Вспышка в центре
        flash = self._canvas.create_oval(
            center[0] - 40, center[1] - 40, center[0] + 40, center[1] + 40,
            fill="#ffdd77", outline="#ff8800", width=4, tags=("anim",),
        )
        # Множество искр
        sparks = []
        for _ in range(40):
            angle = random.uniform(0, 2 * 3.14159)
            dist = random.uniform(10, 45)
            dx = dist * (random.choice([-1, 1]) * abs(random.gauss(0, 1)))
            dy = dist * (random.choice([-1, 1]) * abs(random.gauss(0, 1)))
            spark = self._canvas.create_line(
                center[0], center[1], center[0] + dx, center[1] + dy,
                fill=random.choice(["#ffaa33", "#ff6633", "#ff3333", "#ffcc00"]),
                width=random.randint(3, 6), tags=("anim",),
            )
            sparks.append(spark)
        # Эффект дрожания доски (изменение цвета фона на короткое время)
        original_bg = self._canvas["bg"]
        self._canvas.config(bg="#ffcc88")
        self.after(200, lambda: self._canvas.config(bg=original_bg))

        def _fade(step: int = 0) -> None:
            if self._destroyed:
                return
            if step > 10:
                self._canvas.delete(flash)
                for s in sparks:
                    self._canvas.delete(s)
                return
            self._canvas.itemconfig(flash, outline="#ffaa44" if step % 2 == 0 else "#ff4400")
            self.after(50, lambda: _fade(step + 1))

        _fade()

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
            x1 = LEFT_MARGIN + (6 * POINT_SIZE) + CENTER_LANE_WIDTH + right_index * POINT_SIZE
        x2 = x1 + POINT_SIZE - POINT_RECT_PADDING
        if row == 0:
            return (x1, 24, x2, CANVAS_HEIGHT / 2 - 6)
        return (x1, CANVAS_HEIGHT / 2 + 6, x2, CANVAS_HEIGHT - 24)

    def _point_center(self, point: int, player: Player) -> tuple[float, float]:
        """Return animation center for source or target point."""
        if point == BAR_POSITION:
            bar_x1, _, bar_x2, _ = self._bar_zone_rect()
            return ((bar_x1 + bar_x2) / 2, TOP_Y if player is Player.WHITE else BOTTOM_Y)
        if point == OFF_POSITION:
            off_zone = self._off_zone_rect(top=player is Player.WHITE)
            return ((off_zone[0] + off_zone[2]) / 2, (off_zone[1] + off_zone[3]) / 2)
        x1, y1, x2, y2 = self._point_rect(point)
        return ((x1 + x2) / 2, y1 + 24 if point >= 13 else y2 - 24)

    def _off_zone_rect(self, top: bool) -> tuple[float, float, float, float]:
        """Return top or bottom borne-off tray rectangle."""
        lane_start = LEFT_MARGIN + 6 * POINT_SIZE
        if self._state.mode is GameMode.LONG:
            x1 = lane_start + (CENTER_LANE_WIDTH - 104) / 2
            x2 = x1 + 104
        else:
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
        return (x1, 16 - y_padding, x2, CANVAS_HEIGHT - 16 + y_padding)
