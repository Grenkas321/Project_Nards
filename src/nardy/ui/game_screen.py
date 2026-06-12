"""Interactive Tkinter game screen with adaptive layout and complex moves."""

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
from nardy.domain.rules_long import LongNardyRules
from nardy.domain.rules_short import ShortNardyRules

# Базовые пропорции (при исходном размере холста)
BASE_WIDTH = 940
BASE_HEIGHT = 480
LEFT_MARGIN = 26
CENTER_LANE_WIDTH = 140
POINT_RECT_PADDING = 6
CHECKER_SIZE = 20
BASE_POINT_SIZE = 62


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
        self._moves_by_source: dict[int, tuple[Move, ...]] = {}
        self._possible_targets_by_source: dict[int, set[int]] = {}

        # Animation attributes
        self._dice_anim_id: str | None = None
        self._dice_anim_step = 0
        self._dice_anim_max_steps = 12
        self._destroyed = False
        self._pending_sequence: list[Move] | None = None
        self._seq_index = 0

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
            bg="#f6e5c8",
            highlightthickness=1,
            highlightbackground="#4a3b2f",
        )
        self._canvas.grid(row=0, column=0, sticky="nsew")
        self._canvas.bind("<Configure>", self._on_resize)

        # Привязываем события один раз (не при каждой перерисовке)
        self._bind_events()

        # Dice display area
        self._dice_canvas = tk.Canvas(
            header,
            width=160,
            height=80,
            bg="#f0e0c0",
            highlightthickness=1,
            highlightbackground="#8a755c",
        )
        self._dice_canvas.grid(row=0, column=2, rowspan=2, padx=(20, 0), pady=(4, 0))

        controls = ttk.Frame(self)
        controls.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        controls.columnconfigure(0, weight=1)
        controls.columnconfigure(1, weight=1)
        controls.columnconfigure(2, weight=1)

        self._roll_button = ttk.Button(
            controls,
            text=self._translate(_("Roll dice")),
            command=self._on_roll_button_click,
        )
        self._roll_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ttk.Button(
            controls,
            text=self._translate(_("Undo")),
            command=on_undo,
        ).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(
            controls,
            text=self._translate(_("Back to menu")),
            command=on_back_to_menu,
        ).grid(row=0, column=2, sticky="ew", padx=(6, 0))

        self._update_moves_cache()
        self._draw_board()
        self._draw_checkers()
        self._draw_highlights()
        self._draw_dice_from_state()
        self._update_roll_button_state(data.can_roll)

        if last_move is not None:
            self.after(20, lambda: self._animate_move(last_move))

    def _bind_events(self) -> None:
        """Bind click events to canvas tags once (to avoid duplication on resize)."""
        for point in range(1, 25):
            self._canvas.tag_bind(f"point_{point}", "<Button-1>", lambda e, p=point: self._on_point_click(p))
        self._canvas.tag_bind("bar_zone", "<Button-1>", lambda e: self._on_point_click(BAR_POSITION))
        self._canvas.tag_bind("off_top", "<Button-1>", lambda e: self._on_point_click(OFF_POSITION))
        self._canvas.tag_bind("off_bottom", "<Button-1>", lambda e: self._on_point_click(OFF_POSITION))

    def _update_roll_button_state(self, can_roll: bool) -> None:
        if not self._destroyed:
            try:
                self._roll_button.config(state=tk.NORMAL if can_roll else tk.DISABLED)
            except tk.TclError:
                pass

    def _update_moves_cache(self) -> None:
        moves = self._state.turn.legal_moves
        self._moves_by_source = self._index_moves(moves)
        self._possible_targets_by_source = self._compute_reachable_targets()

    def _compute_reachable_targets(self) -> dict[int, set[int]]:
        """For each source, compute all target points reachable via any sequence of moves."""
        if self._state.mode == GameMode.LONG:
            rules = LongNardyRules()
        else:
            rules = ShortNardyRules()

        result = defaultdict(set)
        remaining_pips = list(self._state.turn.remaining_pips)

        from collections import deque

        for source in self._moves_by_source.keys():
            queue = deque()
            queue.append((self._state, source, list(remaining_pips)))
            visited = set()
            while queue:
                cur_state, cur_pos, pips = queue.popleft()
                legal = rules.legal_moves(cur_state)
                for move in legal:
                    if move.source != cur_pos:
                        continue
                    if move.die_value not in pips:
                        continue
                    try:
                        next_state = rules.apply_move(cur_state, move)
                    except Exception:
                        continue
                    new_pips = pips.copy()
                    new_pips.remove(move.die_value)
                    result[source].add(move.target)
                    key = (next_state, move.target, tuple(new_pips))
                    if key not in visited:
                        visited.add(key)
                        queue.append((next_state, move.target, new_pips))
        return dict(result)

    @staticmethod
    def _index_moves(moves: tuple[Move, ...]) -> dict[int, tuple[Move, ...]]:
        grouped: defaultdict[int, list[Move]] = defaultdict(list)
        for move in moves:
            grouped[move.source].append(move)
        return {source: tuple(source_moves) for source, source_moves in grouped.items()}

    # ---------- Layout and scaling ----------
    def _get_scaled_coords(self) -> dict[str, float]:
        w = self._canvas.winfo_width()
        h = self._canvas.winfo_height()
        if w < 100:
            w = BASE_WIDTH
        if h < 100:
            h = BASE_HEIGHT
        return {"scale_x": w / BASE_WIDTH, "scale_y": h / BASE_HEIGHT, "width": w, "height": h}

    def _scale_point_rect(self, point: int) -> tuple[float, float, float, float]:
        scale = self._get_scaled_coords()
        sx, sy = scale["scale_x"], scale["scale_y"]
        w, h = scale["width"], scale["height"]
        left_margin = LEFT_MARGIN * sx
        point_size = BASE_POINT_SIZE * sx
        center_lane = CENTER_LANE_WIDTH * sx
        rect_padding = POINT_RECT_PADDING * sx
        half_height = h / 2

        if point >= 13:
            row = 0
            index = point - 13
        else:
            row = 1
            index = 12 - point

        if index < 6:
            x1 = left_margin + index * point_size
        else:
            right_index = index - 6
            x1 = left_margin + 6 * point_size + center_lane + right_index * point_size
        x2 = x1 + point_size - rect_padding
        if row == 0:
            return (x1, 24 * sy, x2, half_height - 6 * sy)
        return (x1, half_height + 6 * sy, x2, h - 24 * sy)

    def _on_resize(self, event: tk.Event) -> None:
        # При изменении размера перерисовываем только графику, привязки не трогаем
        self._draw_board()
        self._draw_checkers()
        self._draw_highlights()

    # ---------- Drawing ----------
    def _draw_board(self) -> None:
        """Draw board geometry (rectangles, text) without re-binding events."""
        self._canvas.delete("board")
        scale = self._get_scaled_coords()
        w, h = scale["width"], scale["height"]
        sx, sy = scale["scale_x"], scale["scale_y"]

        self._canvas.create_rectangle(0, 0, w, h, fill="#e8d5b0", outline="", tags=("board",))
        for i in range(0, int(w), int(40 * sx)):
            self._canvas.create_line(i, 0, i + 20 * sx, h, fill="#d4be8a", width=1, tags=("board",))
        self._canvas.create_line(0, h / 2, w, h / 2, fill="#8a755c", width=int(4 * sy), tags=("board",))
        self._canvas.create_rectangle(4 * sx, 4 * sy, w - 4 * sx, h - 4 * sy, outline="#5c4733", width=int(4 * sy), tags=("board",))

        for point in range(1, 25):
            x1, y1, x2, y2 = self._scale_point_rect(point)
            fill = "#e7d0ab" if (point % 2 == 0) else "#dbbc87"
            self._canvas.create_rectangle(x1, y1, x2, y2, fill=fill, outline="#7b6247", width=2, tags=("board", f"point_{point}"))
            self._canvas.create_rectangle(x1 + 2, y1 + 2, x2 - 2, y2 - 2, fill="", outline="#cbaa77", width=1, tags=("board",))
            text_y = y1 - 10 * sy if point >= 13 else y2 + 10 * sy
            self._canvas.create_text((x1 + x2) / 2, text_y, text=str(point), fill="#3e3024", font=("Segoe UI", int(9 * sy), "bold"), tags=("board",))

        if self._state.mode is GameMode.SHORT:
            bar = self._bar_zone_rect(scale)
            self._canvas.create_rectangle(bar[0], bar[1], bar[2], bar[3], fill="#cdb089", outline="#6b5137", width=2, tags=("board", "bar_zone"))

        top_off = self._off_zone_rect(scale, top=True)
        bottom_off = self._off_zone_rect(scale, top=False)
        for zone, label in ((top_off, "off_top"), (bottom_off, "off_bottom")):
            self._canvas.create_rectangle(*zone, fill="#d9c3a0", outline="#6b5137", width=2, tags=("board", label))

    def _draw_checkers(self) -> None:
        self._canvas.delete("checker")
        for point in range(1, 25):
            ps = self._state.point(point)
            if ps.checkers:
                self._draw_stack(point, ps.owner, ps.checkers)
        self._draw_bar_stack(Player.WHITE, self._state.bar_for(Player.WHITE), True)
        self._draw_bar_stack(Player.BLACK, self._state.bar_for(Player.BLACK), False)
        self._draw_off_counter(Player.WHITE, self._state.borne_off_for(Player.WHITE), True)
        self._draw_off_counter(Player.BLACK, self._state.borne_off_for(Player.BLACK), False)

    def _draw_stack(self, point: int, owner: Player | None, count: int) -> None:
        if owner is None:
            return
        scale = self._get_scaled_coords()
        sx, sy = scale["scale_x"], scale["scale_y"]
        x1, y1, x2, y2 = self._scale_point_rect(point)
        center_x = (x1 + x2) / 2
        step = CHECKER_SIZE * sy + 2
        checker_r = CHECKER_SIZE * sy / 2
        max_visible = min(5, count)
        color_base = "#fcfcfc" if owner is Player.WHITE else "#2c2c2c"
        color_rim = "#dddddd" if owner is Player.WHITE else "#555555"

        # Текст количества фишек – между стопкой и центром доски
        if point >= 13:
            # Верхняя половина: стопка растёт вниз, текст снизу стопки (ближе к центру)
            text_y = y2 - 14 * sy
            cy_start = y1 + 14 * sy
        else:
            # Нижняя половина: стопка растёт вверх, текст сверху стопки (ближе к центру)
            text_y = y1 + 6 * sy
            cy_start = y2 - 14 * sy

        for idx in range(max_visible):
            cy = cy_start + idx * step if point >= 13 else cy_start - idx * step
            # тень
            self._canvas.create_oval(center_x - checker_r + 2, cy - checker_r + 2,
                                     center_x + checker_r + 2, cy + checker_r + 2,
                                     fill="#a09070", outline="", tags=("checker",))
            # основная фишка
            self._canvas.create_oval(center_x - checker_r, cy - checker_r,
                                     center_x + checker_r, cy + checker_r,
                                     fill=color_base, outline=color_rim, width=2, tags=("checker",))
            # блик
            self._canvas.create_oval(center_x - checker_r / 2, cy - checker_r / 1.5,
                                     center_x, cy,
                                     fill="#ffffff" if owner is Player.WHITE else "#888888", outline="", tags=("checker",))

        if count > 1:
            self._canvas.create_text(center_x, text_y, text=f"x{count}", fill="#aa2e2e",
                                     font=("Segoe UI", int(10 * sy), "bold"), tags=("checker",))

    def _draw_bar_stack(self, player: Player, count: int, top: bool) -> None:
        if self._state.mode is not GameMode.SHORT or count <= 0:
            return
        scale = self._get_scaled_coords()
        sx, sy = scale["scale_x"], scale["scale_y"]
        bar = self._bar_zone_rect(scale)
        center_x = (bar[0] + bar[2]) / 2
        base_y = 70 * sy if top else scale["height"] - 70 * sy
        step = CHECKER_SIZE * sy + 2
        max_visible = min(count, 4)
        color_base = "#fcfcfc" if player is Player.WHITE else "#2c2c2c"
        color_rim = "#dddddd" if player is Player.WHITE else "#555555"
        for idx in range(max_visible):
            cy = base_y + idx * step if top else base_y - idx * step
            self._canvas.create_oval(center_x - CHECKER_SIZE * sy / 2 + 2, cy - CHECKER_SIZE * sy / 2 + 2,
                                     center_x + CHECKER_SIZE * sy / 2 + 2, cy + CHECKER_SIZE * sy / 2 + 2,
                                     fill="#a09070", outline="", tags=("checker",))
            self._canvas.create_oval(center_x - CHECKER_SIZE * sy / 2, cy - CHECKER_SIZE * sy / 2,
                                     center_x + CHECKER_SIZE * sy / 2, cy + CHECKER_SIZE * sy / 2,
                                     fill=color_base, outline=color_rim, width=2, tags=("checker",))
        if count > max_visible:
            self._canvas.create_text(center_x, 24 * sy if top else scale["height"] - 24 * sy,
                                     text=f"bar {count}", fill="#3b2b1f", font=("Segoe UI", int(9 * sy), "bold"), tags=("checker",))

    def _draw_off_counter(self, player: Player, count: int, top: bool) -> None:
        text = self._translate(_("White")) if player is Player.WHITE else self._translate(_("Black"))
        scale = self._get_scaled_coords()
        zone = self._off_zone_rect(scale, top=top)
        self._canvas.create_text((zone[0] + zone[2]) / 2, (zone[1] + zone[3]) / 2,
                                 text=f"{text}: {count}", fill="#33261b",
                                 font=("Segoe UI", int(10 * scale["scale_y"]), "bold"), tags=("checker",))

    def _draw_highlights(self) -> None:
        self._canvas.delete("highlight")
        scale = self._get_scaled_coords()
        # Подсветка источников
        for source in self._moves_by_source:
            if source == BAR_POSITION:
                if self._state.mode is GameMode.SHORT:
                    bar = self._bar_zone_rect(scale, y_padding=2)
                    self._canvas.create_rectangle(*bar, outline="#2f9954", width=4, tags=("highlight",))
                continue
            x1, y1, x2, y2 = self._scale_point_rect(source)
            self._canvas.create_rectangle(x1 + 2, y1 + 2, x2 - 2, y2 - 2, outline="#2f9954", width=4, tags=("highlight",))

        if self._selected_source is None:
            return

        # Подсветка выбранного источника
        if self._selected_source != BAR_POSITION:
            x1, y1, x2, y2 = self._scale_point_rect(self._selected_source)
            self._canvas.create_rectangle(x1 + 4, y1 + 4, x2 - 4, y2 - 4, outline="#f3a531", width=4, tags=("highlight",))

        # Подсветка всех возможных целей (включая сложные)
        targets = self._possible_targets_by_source.get(self._selected_source, set())
        for target in targets:
            if target == OFF_POSITION:
                off = self._off_zone_rect(scale, top=self._state.current_player is Player.WHITE)
                self._canvas.create_rectangle(*off, outline="#1a73c8", width=4, tags=("highlight",))
                continue
            x1, y1, x2, y2 = self._scale_point_rect(target)
            self._canvas.create_rectangle(x1 + 8, y1 + 8, x2 - 8, y2 - 8, outline="#1a73c8", width=4, tags=("highlight",))

    # ---------- Utility rectangles ----------
    def _bar_zone_rect(self, scale: dict, y_padding: int = 0) -> tuple[float, float, float, float]:
        sx, sy = scale["scale_x"], scale["scale_y"]
        lane_start = LEFT_MARGIN * sx + 6 * BASE_POINT_SIZE * sx
        x1 = lane_start + CENTER_LANE_WIDTH * sx - 42 * sx
        x2 = lane_start + CENTER_LANE_WIDTH * sx - 6 * sx
        return (x1, 16 * sy - y_padding, x2, scale["height"] - 16 * sy + y_padding)

    def _off_zone_rect(self, scale: dict, top: bool) -> tuple[float, float, float, float]:
        sx, sy = scale["scale_x"], scale["scale_y"]
        lane_start = LEFT_MARGIN * sx + 6 * BASE_POINT_SIZE * sx
        if self._state.mode is GameMode.LONG:
            x1 = lane_start + (CENTER_LANE_WIDTH * sx - 104 * sx) / 2
            x2 = x1 + 104 * sx
        else:
            x1 = lane_start + 8 * sx
            x2 = x1 + 70 * sx
        if top:
            return (x1, 18 * sy, x2, 104 * sy)
        return (x1, scale["height"] - 104 * sy, x2, scale["height"] - 18 * sy)

    # ---------- Move logic (complex moves) ----------
    def _find_sequence_to_target(self, source: int, target: int) -> list[Move] | None:
        if self._state.mode == GameMode.LONG:
            rules = LongNardyRules()
        else:
            rules = ShortNardyRules()

        from collections import deque
        initial_pips = list(self._state.turn.remaining_pips)
        queue = deque()
        queue.append((self._state, [], source, initial_pips))
        visited = set()

        while queue:
            cur_state, path, cur_pos, pips = queue.popleft()
            if cur_pos == target:
                return path
            legal = rules.legal_moves(cur_state)
            for move in legal:
                if move.source != cur_pos:
                    continue
                if move.die_value not in pips:
                    continue
                try:
                    next_state = rules.apply_move(cur_state, move)
                except Exception:
                    continue
                new_pips = pips.copy()
                new_pips.remove(move.die_value)
                new_path = path + [move]
                key = (next_state, move.target, tuple(new_pips))
                if key not in visited:
                    visited.add(key)
                    queue.append((next_state, new_path, move.target, new_pips))
        return None

    def _apply_sequence(self, sequence: list[Move]) -> None:
        self._pending_sequence = sequence
        self._seq_index = 0
        self._process_next_in_sequence()

    def _process_next_in_sequence(self) -> None:
        if self._pending_sequence is None or self._seq_index >= len(self._pending_sequence):
            self._pending_sequence = None
            return
        move = self._pending_sequence[self._seq_index]
        self._seq_index += 1
        self._on_move_selected(move)
        self.after(300, self._process_next_in_sequence)

    # ---------- Click handling ----------
    def _on_point_click(self, point: int) -> None:
        if not self._moves_by_source:
            return
        if self._selected_source is None:
            if point in self._moves_by_source:
                self._selected_source = point
                self._draw_highlights()
            return

        # Прямой ход
        direct_moves = self._moves_by_source.get(self._selected_source, ())
        direct = next((m for m in direct_moves if m.target == point or (point == OFF_POSITION and m.target == OFF_POSITION)), None)
        if direct is not None:
            self._submit_move(direct)
            self._selected_source = None
            return

        # Сложная последовательность
        seq = self._find_sequence_to_target(self._selected_source, point)
        if seq:
            self._apply_sequence(seq)
            self._selected_source = None
            return

        # Переключение источника
        if point in self._moves_by_source and point != self._selected_source:
            self._selected_source = point
            self._draw_highlights()
            return

        # Отмена
        self._selected_source = None
        self._draw_highlights()

    def _submit_move(self, move: Move) -> None:
        self._on_move_selected(move)

    # ---------- Dice animation and explosion ----------
    def _on_roll_button_click(self) -> None:
        if self._dice_anim_id is not None or self._destroyed:
            return
        try:
            self._roll_button.config(state=tk.DISABLED)
        except tk.TclError:
            return
        self._start_dice_animation()

    def _start_dice_animation(self) -> None:
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
                self._dice_explosion()
                self._on_roll_dice_callback()
                if not self._destroyed:
                    try:
                        self._roll_button.config(state=tk.NORMAL)
                    except tk.TclError:
                        pass
                self.after(50, self._draw_dice_from_state)

        step()

    def _dice_explosion(self) -> None:
        if self._destroyed:
            return
        try:
            self._dice_canvas.create_rectangle(0, 0, 160, 80, fill="#ffaa33", outline="", stipple="gray50", tags="dice_flash")
            for _ in range(25):
                x = random.randint(10, 150)
                y = random.randint(10, 70)
                self._dice_canvas.create_oval(x - 5, y - 5, x + 5, y + 5,
                                              fill=random.choice(["#ff8800", "#ff5500", "#ffcc00"]),
                                              outline="#ff3300", tags="dice_flash")
            self.after(500, lambda: self._dice_canvas.delete("dice_flash"))
        except tk.TclError:
            pass

    def _draw_dice_on_canvas(self, value1: int, value2: int) -> None:
        if self._destroyed:
            return
        try:
            self._dice_canvas.delete("dice")
        except tk.TclError:
            return
        w, h = 60, 60
        margin = 10
        x1 = margin
        y1 = (80 - h) // 2
        self._draw_single_die(x1, y1, w, h, value1)
        x2 = x1 + w + margin
        self._draw_single_die(x2, y1, w, h, value2)

    def _draw_single_die(self, x: int, y: int, w: int, h: int, value: int) -> None:
        try:
            self._dice_canvas.create_rectangle(x, y, x + w, y + h, fill="#ffffff", outline="#333333", width=2, tags="dice")
            self._dice_canvas.create_rectangle(x + 2, y + 2, x + w - 2, y + h - 2, fill="#fafafa", outline="", tags="dice")
            pip_positions = {
                1: [(w//2, h//2)],
                2: [(w//4, h//4), (3*w//4, 3*h//4)],
                3: [(w//4, h//4), (w//2, h//2), (3*w//4, 3*h//4)],
                4: [(w//4, h//4), (3*w//4, h//4), (w//4, 3*h//4), (3*w//4, 3*h//4)],
                5: [(w//4, h//4), (3*w//4, h//4), (w//2, h//2), (w//4, 3*h//4), (3*w//4, 3*h//4)],
                6: [(w//4, h//4), (3*w//4, h//4), (w//4, h//2), (3*w//4, h//2), (w//4, 3*h//4), (3*w//4, 3*h//4)],
            }
            for cx, cy in pip_positions[value]:
                self._dice_canvas.create_oval(x + cx - 6, y + cy - 6, x + cx + 6, y + cy + 6, fill="#222222", outline="#111111", tags="dice")
                self._dice_canvas.create_oval(x + cx - 4, y + cy - 4, x + cx + 2, y + cy + 2, fill="#555555", outline="", tags="dice")
        except tk.TclError:
            pass

    def _draw_dice_from_state(self) -> None:
        if self._destroyed:
            return
        dice = self._state.turn.dice
        if dice is None:
            try:
                self._dice_canvas.delete("dice")
            except tk.TclError:
                pass
            return
        self._draw_dice_on_canvas(dice.values[0], dice.values[1])

    # ---------- Move animation and explosion ----------
    def _animate_move(self, move: Move) -> None:
        start = self._point_center(move.source, move.player)
        end = self._point_center(move.target, move.player)
        token = self._canvas.create_oval(start[0] - 8, start[1] - 8, start[0] + 8, start[1] + 8,
                                         fill="#e64b3a", outline="#ffffff", width=2, tags=("anim",))
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
        if self._destroyed:
            return
        flash = self._canvas.create_oval(center[0] - 40, center[1] - 40, center[0] + 40, center[1] + 40,
                                         fill="#ffdd77", outline="#ff8800", width=4, tags=("anim",))
        sparks = []
        for _ in range(40):
            dx = random.uniform(-45, 45)
            dy = random.uniform(-45, 45)
            spark = self._canvas.create_line(center[0], center[1], center[0] + dx, center[1] + dy,
                                             fill=random.choice(["#ffaa33", "#ff6633", "#ff3333", "#ffcc00"]),
                                             width=random.randint(3, 6), tags=("anim",))
            sparks.append(spark)
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

    def _point_center(self, point: int, player: Player) -> tuple[float, float]:
        if point == BAR_POSITION:
            scale = self._get_scaled_coords()
            bar = self._bar_zone_rect(scale)
            return ((bar[0] + bar[2]) / 2, 54 * scale["scale_y"] if player is Player.WHITE else scale["height"] - 54 * scale["scale_y"])
        if point == OFF_POSITION:
            scale = self._get_scaled_coords()
            off = self._off_zone_rect(scale, top=player is Player.WHITE)
            return ((off[0] + off[2]) / 2, (off[1] + off[3]) / 2)
        x1, y1, x2, y2 = self._scale_point_rect(point)
        return ((x1 + x2) / 2, y1 + 24 * self._get_scaled_coords()["scale_y"] if point >= 13 else y2 - 24 * self._get_scaled_coords()["scale_y"])

    # ---------- Lifecycle ----------
    def destroy(self) -> None:
        """Destroy."""
        self._destroyed = True
        if self._dice_anim_id is not None:
            try:
                self.after_cancel(self._dice_anim_id)
            except Exception:
                pass
        super().destroy()
