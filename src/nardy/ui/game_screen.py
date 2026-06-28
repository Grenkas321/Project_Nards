"""Interactive Tkinter game screen with realistic board rendering."""

from __future__ import annotations

import math
import random
import tkinter as tk
from collections import defaultdict, deque
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
from nardy.i18n import Localizer, gettext_noop as N_
from nardy.domain.rules_long import LongNardyRules
from nardy.domain.rules_short import ShortNardyRules
from nardy.ui.sounds import play_checker_place, play_dice_roll
from nardy.ui.textures import (
    checker_photo, shadow_photo, die_photo,
    bark_texture, board_surface,
    triangle_image, center_ornament,
)
from PIL import ImageTk

BASE_WIDTH = 940
BASE_HEIGHT = 500
LEFT_MARGIN = 30
CENTER_LANE_WIDTH = 60
POINT_WIDTH = 58
CHECKER_RADIUS = 22
BORDER_WIDTH = 18


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
        on_undo_move: Callable[[], None] | None = None,
        on_back_to_menu: Callable[[], None] = lambda: None,
    ) -> None:
        """Create the board and bind player actions."""
        super().__init__(master, padding=10)
        self._translate = localizer.gettext
        self._state = state
        self._on_roll_dice_callback = on_roll_dice
        self._on_move_selected = on_apply_move
        self._on_undo_move = on_undo_move
        self._selected_source: int | None = None
        self._moves_by_source: dict[int, tuple[Move, ...]] = {}
        self._possible_targets_by_source: dict[int, set[int]] = {}
        self._can_roll = data.can_roll
        self._can_undo_move = data.can_undo_move

        self._dice_anim_id: str | None = None
        self._dice_anim_step = 0
        self._dice_anim_max_steps = 14
        self._destroyed = False
        self._pending_sequence: list[Move] | None = None
        self._seq_index = 0
        self._anim_hide_point: int | None = None
        self._photo_refs: list[ImageTk.PhotoImage] = []
        self._board_bg: ImageTk.PhotoImage | None = None
        self._tri_cache: dict = {}
        self._last_board_size: tuple[int, int] = (0, 0)
        self._last_theme_ver: int = -1

        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=0)
        self.rowconfigure(0, weight=1)

        self._data = data

        self._canvas = tk.Canvas(
            self, bg="#2a1508", highlightthickness=0,
        )
        self._canvas.grid(row=0, column=0, sticky="nsew")
        self._canvas.bind("<Configure>", self._on_resize)
        self._canvas.bind("<Button-1>", self._on_canvas_click)

        # Right side panel — off zones + status
        self._side_panel = tk.Canvas(
            self, bg="#2a1508", highlightthickness=0, width=200,
        )
        self._side_panel.grid(row=0, column=1, sticky="nsew")
        self.columnconfigure(1, weight=0, minsize=200)

        controls = ttk.Frame(self)
        controls.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(2, 0))
        controls.columnconfigure(0, weight=1)
        controls.columnconfigure(1, weight=1)

        self._undo_move_button = ttk.Button(
            controls, text=self._translate(N_("Undo")),
            command=self._on_undo_move_click,
        )
        self._undo_move_button.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(
            controls, text=self._translate(N_("Back to menu")),
            command=on_back_to_menu,
        ).grid(row=0, column=1, sticky="ew", padx=(4, 0))

        self._update_moves_cache()
        self._draw_board()
        self._draw_checkers()
        self._draw_highlights()
        self._draw_dice_or_roll_btn()
        self._update_undo_button()

        if last_move is not None:
            self.after(20, lambda: self._animate_move(last_move))

    def update_state(
        self, data: GameScreenData, state: GameState,
        last_move: Move | None, can_roll: bool,
    ) -> None:
        """Update screen in-place without widget recreation."""
        self._state = state
        self._data = data
        self._can_roll = can_roll
        self._can_undo_move = data.can_undo_move
        self._selected_source = None
        if last_move is not None:
            self._anim_hide_point = last_move.target
        else:
            self._anim_hide_point = None
        self._update_moves_cache()
        self._draw_checkers()
        self._draw_highlights()
        self._draw_dice_or_roll_btn()
        self._draw_status_overlay()
        self._update_undo_button()
        if last_move is not None:
            self.after(20, lambda: self._animate_move(last_move))

    def _update_undo_button(self) -> None:
        if self._destroyed:
            return
        try:
            st = tk.NORMAL if self._can_undo_move else tk.DISABLED
            self._undo_move_button.config(state=st)
        except tk.TclError:
            pass

    def _on_undo_move_click(self) -> None:
        if self._on_undo_move:
            self._on_undo_move()

    # ---------- Moves cache ----------

    def _update_moves_cache(self) -> None:
        moves = self._state.turn.legal_moves
        self._moves_by_source = self._index_moves(moves)
        self._possible_targets_by_source = self._compute_reachable_targets()

    def _compute_reachable_targets(self) -> dict[int, set[int]]:
        if self._state.mode == GameMode.LONG:
            rules = LongNardyRules()
        else:
            rules = ShortNardyRules()
        result: dict[int, set[int]] = defaultdict(set)
        remaining_pips = list(self._state.turn.remaining_pips)
        for source in self._moves_by_source:
            queue: deque[tuple[GameState, int, list[int]]] = deque()
            queue.append((self._state, source, list(remaining_pips)))
            visited: set[tuple[GameState, int, tuple[int, ...]]] = set()
            while queue:
                cur_state, cur_pos, pips = queue.popleft()
                legal = rules.legal_moves(cur_state)
                for move in legal:
                    if move.source != cur_pos or move.die_value not in pips:
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
        return {s: tuple(m) for s, m in grouped.items()}

    # ---------- Layout ----------

    def _sc(self) -> tuple[float, float, float, float]:
        w = max(self._canvas.winfo_width(), 200)
        h = max(self._canvas.winfo_height(), 200)
        return w / BASE_WIDTH, h / BASE_HEIGHT, w, h

    def _board_metrics(self) -> tuple[float, float, float]:
        """Return (bw, pw, cl) scaled to fill canvas width."""
        sx, sy, w, h = self._sc()
        bw = BORDER_WIDTH * sx
        cl = CENTER_LANE_WIDTH * sx
        pw = (w - 2 * bw - cl) / 12
        return bw, pw, cl

    def _point_rect(self, point: int) -> tuple[float, float, float, float]:
        sx, sy, w, h = self._sc()
        bw, pw, cl = self._board_metrics()
        mid = h / 2

        if point >= 13:
            row = 0
            idx = point - 13
        else:
            row = 1
            idx = 12 - point

        if idx < 6:
            x1 = bw + idx * pw
        else:
            x1 = bw + 6 * pw + cl + (idx - 6) * pw
        x2 = x1 + pw

        gap = 40 * sy
        if row == 0:
            return x1, bw, x2, mid - gap
        return x1, mid + gap, x2, h - bw

    def _point_triangle(self, point: int) -> list[float]:
        x1, y1, x2, y2 = self._point_rect(point)
        cx = (x1 + x2) / 2
        if point >= 13:
            return [x1, y1, x2, y1, cx, y2]
        return [x1, y2, x2, y2, cx, y1]

    def _on_resize(self, event: tk.Event) -> None:
        self._draw_board()
        self._draw_checkers()
        self._draw_highlights()
        self._draw_dice_or_roll_btn()

    # ---------- Hit-test for canvas clicks ----------

    def _hit_test_point(self, mx: float, my: float) -> int | None:
        """Return point number (1-24), BAR_POSITION, or None."""
        # Bar zone
        if self._state.mode is GameMode.SHORT:
            b = self._bar_zone_rect()
            if b[0] <= mx <= b[2] and b[1] <= my <= b[3]:
                return BAR_POSITION

        # Points
        for point in range(1, 25):
            x1, y1, x2, y2 = self._point_rect(point)
            if x1 <= mx <= x2 and y1 <= my <= y2:
                return point

        return None

    def _on_canvas_click(self, event: tk.Event) -> None:
        mx, my = event.x, event.y

        # Check roll button
        if self._can_roll and self._dice_anim_id is None:
            cx, cy = self._dice_center()
            sx, sy, _, _ = self._sc()
            r = 65 * min(sx, sy)
            if (mx - cx) ** 2 + (my - cy) ** 2 <= r * r:
                self._on_roll_button_click()
                return

        point = self._hit_test_point(mx, my)
        if point is not None:
            self._on_point_click(point)

    # ---------- Board drawing ----------

    def _draw_board(self) -> None:
        self._canvas.delete("board")
        sx, sy, w, h = self._sc()
        bw, pw, cl = self._board_metrics()
        iw, ih = int(w), int(h)

        from nardy.ui.textures import _theme_change_counter
        # Rebuild on size change or theme change
        if (iw, ih) != self._last_board_size or self._last_theme_ver != _theme_change_counter:
            self._last_board_size = (iw, ih)
            self._last_theme_ver = _theme_change_counter
            self._photo_refs.clear()
            self._tri_cache.clear()
            self._build_board_bg(iw, ih, bw, pw, cl)

        if self._board_bg:
            self._canvas.create_image(0, 0, anchor="nw", image=self._board_bg, tags=("board",))

        # Checker grooves at triangle bases
        groove_r = pw / 2.5
        for point in range(1, 25):
            x1g, y1g, x2g, y2g = self._point_rect(point)
            gcx = (x1g + x2g) / 2
            if point >= 13:
                gy = y1g + 2
                self._canvas.create_oval(
                    gcx - groove_r, gy - groove_r * 0.4,
                    gcx + groove_r, gy + groove_r * 0.8,
                    fill="#8a7a60", outline="#6a5a40", width=1,
                    tags=("board",),
                )
            else:
                gy = y2g - 2
                self._canvas.create_oval(
                    gcx - groove_r, gy - groove_r * 0.8,
                    gcx + groove_r, gy + groove_r * 0.4,
                    fill="#8a7a60", outline="#6a5a40", width=1,
                    tags=("board",),
                )

        # Triangles as PIL images
        for point in range(1, 25):
            x1, y1, x2, y2 = self._point_rect(point)
            tw = max(4, int(x2 - x1))
            th = max(4, int(abs(y2 - y1)))
            ct = "dark" if point % 2 == 0 else "light"
            pt_dir = "down" if point >= 13 else "up"
            key = (tw, th, ct, pt_dir)
            if key not in self._tri_cache:
                tri_img = triangle_image(tw, th, ct, pt_dir)
                self._tri_cache[key] = ImageTk.PhotoImage(tri_img)
            photo = self._tri_cache[key]
            self._canvas.create_image(
                int(x1), int(y1), anchor="nw", image=photo, tags=("board",),
            )

        # Point numbers
        for point in range(1, 25):
            x1, y1, x2, y2 = self._point_rect(point)
            cx_p = (x1 + x2) / 2
            ty = y1 - 6 * sy if point >= 13 else y2 + 6 * sy
            self._canvas.create_text(
                cx_p, ty, text=str(point),
                fill="#f0e8d8", font=("Segoe UI", max(7, int(8 * sy)), "bold"),
                tags=("board",),
            )

        # Center ornaments (one per half, between triangles)
        orn_size = max(40, int(min(pw * 5, 80 * sy)))
        left_half_cx = int(bw + 3 * pw)
        right_half_cx = int(bw + 6 * pw + cl + 3 * pw)
        mid_y = int(h / 2)
        orn_key = orn_size
        if orn_key not in self._tri_cache:
            orn_img = center_ornament(orn_size, orn_size)
            self._tri_cache[orn_key] = ImageTk.PhotoImage(orn_img)
        orn_photo = self._tri_cache[orn_key]
        for ox in (left_half_cx, right_half_cx):
            self._canvas.create_image(
                ox, mid_y, image=orn_photo, tags=("board",),
            )

        if self._state.mode is GameMode.SHORT:
            bar = self._bar_zone_rect()
            self._canvas.create_rectangle(
                *bar, fill="#d8ccb4", outline="#b8a88c", width=2, tags=("board",),
            )

        # Draw side panel zones
        self._draw_side_panel()

        # Border — ends at field edge
        ibw = int(bw)
        fr = int(bw + 12 * pw + cl + bw)
        self._canvas.create_rectangle(2, 2, fr, int(h) - 2, outline="#2a1508", width=3, tags=("board",))
        self._canvas.create_rectangle(ibw - 1, ibw - 1, fr - ibw + 1, ih - ibw + 1, outline="#4a3018", width=2, tags=("board",))

        # Status text on the frame
        self._draw_status_overlay()

    def _draw_side_panel(self) -> None:
        self._side_panel.delete("panel")
        pw = max(self._side_panel.winfo_width(), 80)
        ph = max(self._side_panel.winfo_height(), 200)
        for top in (True, False):
            zone = self._off_zone_rect(top=top)
            self._side_panel.create_rectangle(
                *zone, fill="#3a2515", outline="#5a3a20", width=1,
                tags=("panel",),
            )

    def _draw_status_overlay(self) -> None:
        self._side_panel.delete("status_text")
        top_zone = self._off_zone_rect(top=True)
        bot_zone = self._off_zone_rect(top=False)
        cx_info = (top_zone[0] + top_zone[2]) / 2
        gap_top = top_zone[3]
        gap_bot = bot_zone[1]
        gap_mid = (gap_top + gap_bot) / 2
        text_w = max(40, top_zone[2] - top_zone[0] - 4)
        fsz = max(9, min(14, int((gap_bot - gap_top) / 4)))
        self._side_panel.create_text(
            cx_info, gap_mid, anchor="center",
            text=f"{self._data.status}\n{self._data.subtitle}",
            fill="#d4c0a0", font=("Georgia", fsz),
            width=text_w, justify="center",
            tags=("status_text",),
        )

    def _build_board_bg(self, w: int, h: int, bw: float, pw: float, cl: float) -> None:
        """Compose board: bark frame, playing surface, dark border between."""
        from PIL import ImageDraw as IDraw
        board = bark_texture(w, h)
        ibw = int(bw)
        field_right = int(bw + 12 * pw + cl)
        fw = max(1, field_right - ibw)
        fh = max(1, h - 2 * ibw)
        field = board_surface(fw, fh)
        board.paste(field, (ibw, ibw))

        bar_x = int(bw + 6 * pw)
        bar_w = max(1, int(cl))
        bar_strip = board_surface(bar_w, fh)
        board.paste(bar_strip, (bar_x, ibw))

        # Dark border lines
        bd = IDraw.Draw(board)
        border_col = (40, 25, 12)
        bw_line = max(2, ibw // 5)
        # Left half
        bd.rectangle([ibw - bw_line, ibw - bw_line, bar_x, h - ibw + bw_line],
                     fill=None, outline=border_col, width=bw_line)
        # Right half
        bd.rectangle([bar_x + bar_w, ibw - bw_line, field_right + bw_line, h - ibw + bw_line],
                     fill=None, outline=border_col, width=bw_line)
        # Bar zone
        bd.rectangle([bar_x - bw_line, ibw - bw_line, bar_x + bar_w + bw_line, h - ibw + bw_line],
                     fill=None, outline=border_col, width=bw_line)

        self._board_bg = ImageTk.PhotoImage(board)

    # ---------- Checkers ----------

    def _draw_checkers(self) -> None:
        self._canvas.delete("checker")
        self._side_panel.delete("checker")
        self._photo_refs.clear()
        for point in range(1, 25):
            ps = self._state.point(point)
            if ps.checkers:
                self._draw_stack(point, ps.owner, ps.checkers)
        self._draw_bar_stack(Player.WHITE, self._state.bar_for(Player.WHITE), True)
        self._draw_bar_stack(Player.BLACK, self._state.bar_for(Player.BLACK), False)
        self._draw_off_counter(Player.WHITE, self._state.borne_off_for(Player.WHITE), True)
        self._draw_off_counter(Player.BLACK, self._state.borne_off_for(Player.BLACK), False)

    def _draw_stack(self, point: int, owner: Player | None, count: int) -> None:
        if owner is None or count == 0:
            return
        if self._anim_hide_point == point:
            count -= 1
            if count <= 0:
                return
        sx, sy, _, _ = self._sc()
        x1, y1, x2, y2 = self._point_rect(point)
        cx = (x1 + x2) / 2
        r = min(CHECKER_RADIUS * sy, (x2 - x1) / 2 - 2)

        avail = abs(y2 - y1) - r
        ideal_step = r * 1.6
        step = min(ideal_step, avail / max(count, 1)) if count > 1 else 0

        for idx in range(count):
            if point >= 13:
                cy = y1 + r + idx * step
            else:
                cy = y2 - r - idx * step
            self._draw_3d_checker(cx, cy, r, owner)

    def _draw_3d_checker(
        self, cx: float, cy: float, r: float, owner: Player,
        canvas: tk.Canvas | None = None,
    ) -> None:
        c = canvas or self._canvas
        d = max(6, int(r * 2))
        is_white = owner is Player.WHITE

        sh = shadow_photo(d)
        self._photo_refs.append(sh)
        c.create_image(int(cx) + 2, int(cy) + 3, image=sh, tags=("checker",))

        ch = checker_photo(d, is_white)
        self._photo_refs.append(ch)
        c.create_image(int(cx), int(cy), image=ch, tags=("checker",))

    def _draw_bar_stack(self, player: Player, count: int, top: bool) -> None:
        if self._state.mode is not GameMode.SHORT or count <= 0:
            return
        sx, sy, _, h = self._sc()
        bar = self._bar_zone_rect()
        cx = (bar[0] + bar[2]) / 2
        r = CHECKER_RADIUS * sy * 0.7
        base_y = bar[1] + r + 4 if top else bar[3] - r - 4
        step = r * 1.4
        for idx in range(min(count, 5)):
            cy = base_y + idx * step if top else base_y - idx * step
            self._draw_3d_checker(cx, cy, r, player)
        if count > 5:
            ty = base_y + 5 * step + 8 if top else base_y - 5 * step - 8
            self._canvas.create_text(cx, ty, text=str(count), fill="#c8a87a", font=("Segoe UI", max(7, int(9 * sy)), "bold"), tags=("checker",))

    def _draw_off_counter(self, player: Player, count: int, top: bool) -> None:
        if count == 0:
            return
        zone = self._off_zone_rect(top=top)
        cx = (zone[0] + zone[2]) / 2
        r = min(14, (zone[2] - zone[0]) / 2.5)
        zone_h = abs(zone[3] - zone[1])
        step = min(r * 0.9, zone_h / max(count, 1)) if count > 1 else 0
        for idx in range(count):
            if top:
                cy = zone[1] + r + 4 + idx * step
            else:
                cy = zone[3] - r - 4 - idx * step
            self._draw_3d_checker(cx, cy, r, player, canvas=self._side_panel)

    # ---------- Highlights ----------

    def _draw_highlights(self) -> None:
        self._canvas.delete("highlight")
        self._side_panel.delete("highlight")
        for source in self._moves_by_source:
            if source == BAR_POSITION:
                if self._state.mode is GameMode.SHORT:
                    bar = self._bar_zone_rect()
                    self._canvas.create_rectangle(bar[0] - 2, bar[1] - 2, bar[2] + 2, bar[3] + 2, outline="#44dd66", width=3, tags=("highlight",))
                continue
            tri = self._point_triangle(source)
            self._canvas.create_polygon(*tri, fill="", outline="#44dd66", width=3, tags=("highlight",))

        if self._selected_source is None:
            return

        if self._selected_source != BAR_POSITION:
            tri = self._point_triangle(self._selected_source)
            self._canvas.create_polygon(*tri, fill="", outline="#ffaa22", width=4, tags=("highlight",))

        targets = self._possible_targets_by_source.get(self._selected_source, set())
        for target in targets:
            if target == OFF_POSITION:
                off = self._off_zone_rect(top=self._state.current_player is Player.WHITE)
                self._side_panel.create_rectangle(*off, outline="#4488ff", width=3, tags=("highlight",))
                continue
            tri = self._point_triangle(target)
            self._canvas.create_polygon(*tri, fill="", outline="#4488ff", width=3, tags=("highlight",))

    # ---------- Utility ----------

    def _bar_zone_rect(self) -> tuple[float, float, float, float]:
        sx, sy, _, h = self._sc()
        bw, pw, cl = self._board_metrics()
        bar_x1 = bw + 6 * pw + 4 * sx
        bar_x2 = bar_x1 + cl - 8 * sx
        return bar_x1, bw + 4 * sy, bar_x2, h - bw - 4 * sy

    def _off_zone_rect(self, top: bool) -> tuple[float, float, float, float]:
        """Off-zone coords in side panel space."""
        pw = max(self._side_panel.winfo_width(), 80)
        ph = max(self._side_panel.winfo_height(), 200)
        m = 6
        zone_h = (ph / 2 - 25) * 0.80
        if top:
            return m, m, pw - m, m + zone_h
        return m, ph - m - zone_h, pw - m, ph - m

    def _dice_center(self) -> tuple[float, float]:
        sx, sy, w, h = self._sc()
        bw, pw, cl = self._board_metrics()
        return bw + 6 * pw + cl / 2, h / 2

    # ---------- Move logic ----------

    def _find_sequence_to_target(self, source: int, target: int) -> list[Move] | None:
        rules = LongNardyRules() if self._state.mode == GameMode.LONG else ShortNardyRules()
        initial_pips = list(self._state.turn.remaining_pips)
        queue: deque[tuple[GameState, list[Move], int, list[int]]] = deque()
        queue.append((self._state, [], source, initial_pips))
        visited: set[tuple[GameState, int, tuple[int, ...]]] = set()
        while queue:
            cur_state, path, cur_pos, pips = queue.popleft()
            if cur_pos == target:
                return path
            legal = rules.legal_moves(cur_state)
            for move in legal:
                if move.source != cur_pos or move.die_value not in pips:
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
        self.after(500, self._process_next_in_sequence)

    # ---------- Click handling ----------

    def _on_point_click(self, point: int) -> None:
        if not self._moves_by_source:
            return
        if self._selected_source is None:
            if point in self._moves_by_source:
                self._selected_source = point
                self._draw_highlights()
            return

        direct_moves = self._moves_by_source.get(self._selected_source, ())
        direct = next(
            (m for m in direct_moves if m.target == point or
             (point == OFF_POSITION and m.target == OFF_POSITION)), None,
        )
        if direct is not None:
            self._on_move_selected(direct)
            self._selected_source = None
            return

        seq = self._find_sequence_to_target(self._selected_source, point)
        if seq:
            self._apply_sequence(seq)
            self._selected_source = None
            return

        if point in self._moves_by_source and point != self._selected_source:
            self._selected_source = point
            self._draw_highlights()
            return

        self._selected_source = None
        self._draw_highlights()

    # ---------- Roll button & dice on board ----------

    def _draw_dice_or_roll_btn(self) -> None:
        """Draw either the roll button or the dice values on the center lane."""
        if self._destroyed:
            return
        self._canvas.delete("dice")
        self._canvas.delete("rollbtn")

        if self._can_roll and self._dice_anim_id is None:
            self._draw_roll_button()
        else:
            dice = self._state.turn.dice
            if dice is not None:
                self._draw_dice_on_board(dice.values[0], dice.values[1])

    def _draw_roll_button(self) -> None:
        cx, cy = self._dice_center()
        sx, sy, _, _ = self._sc()
        r = 65 * min(sx, sy)
        c = self._canvas
        # Shadow
        c.create_oval(cx - r + 3, cy - r + 4, cx + r + 3, cy + r + 4,
                      fill="#0a0604", outline="", tags=("rollbtn",))
        # Gradient body
        for i in range(10):
            t = i / 9
            cr = r * (1.0 - t * 0.02)
            red = int(150 + t * 50)
            grn = int(28 + t * 28)
            blu = int(22 + t * 22)
            c.create_oval(cx - cr, cy - cr, cx + cr, cy + cr,
                          fill=f"#{min(255, red):02x}{grn:02x}{blu:02x}",
                          outline="", tags=("rollbtn",))
        # Rim
        c.create_oval(cx - r, cy - r, cx + r, cy + r,
                      fill="", outline="#7a1a12", width=max(2, int(r * 0.07)),
                      tags=("rollbtn",))
        # Top shine
        c.create_oval(cx - r * 0.5, cy - r * 0.6, cx + r * 0.5, cy - r * 0.05,
                      fill="#e85a4a", outline="", tags=("rollbtn",))
        # Text centered
        font_sz = max(9, int(13 * min(sx, sy)))
        c.create_text(cx, cy,
                      text=self._translate(N_("Roll dice")),
                      fill="#ffffff", font=("Georgia", font_sz, "bold"),
                      tags=("rollbtn",))

    def _draw_dice_on_board(self, v1: int, v2: int, ox: float = 0, oy: float = 0) -> None:
        self._canvas.delete("dice")
        cx, cy = self._dice_center()
        sx, sy, _, _ = self._sc()
        die_sz = min(32 * sx, 32 * sy)
        gap = 6 * sy
        self._draw_single_die(cx + ox, cy - die_sz - gap / 2 + oy, die_sz, v1)
        self._draw_single_die(cx + ox, cy + gap / 2 + oy, die_sz, v2)

    def _draw_single_die(self, x: float, y: float, sz: float, value: int) -> None:
        isz = max(8, int(sz))
        photo = die_photo(isz, value)
        self._photo_refs.append(photo)
        self._canvas.create_image(
            int(x), int(y + sz / 2), image=photo, tags=("dice",),
        )

    def _on_roll_button_click(self) -> None:
        if self._dice_anim_id is not None or self._destroyed or not self._can_roll:
            return
        self._can_roll = False
        self._canvas.delete("rollbtn")
        self._start_dice_animation()

    def _start_dice_animation(self) -> None:
        cx, cy = self._dice_center()
        sx, sy, _, h = self._sc()
        bw, pw, cl = self._board_metrics()
        die_sz = min(28 * sx, 28 * sy)

        lane_l = bw + 6 * pw + 4
        lane_r = lane_l + cl - 8
        lane_t = bw + 10
        lane_b = h - bw - 10

        dice_phys = [
            {"x": cx - 5, "y": lane_t + die_sz,
             "vx": random.uniform(-6, 6), "vy": random.uniform(6, 12),
             "face": random.randint(1, 6), "bounces": 0},
            {"x": cx + 5, "y": lane_b - die_sz,
             "vx": random.uniform(-6, 6), "vy": random.uniform(-12, -6),
             "face": random.randint(1, 6), "bounces": 0},
        ]
        frame_count = [0]
        play_dice_roll()

        def step() -> None:
            if self._destroyed:
                return
            self._canvas.delete("dice")

            all_slow = True
            for d in dice_phys:
                d["x"] += d["vx"]
                d["y"] += d["vy"]

                bounced = False
                if d["x"] - die_sz / 2 < lane_l:
                    d["x"] = lane_l + die_sz / 2
                    d["vx"] = abs(d["vx"]) * 0.75
                    bounced = True
                elif d["x"] + die_sz / 2 > lane_r:
                    d["x"] = lane_r - die_sz / 2
                    d["vx"] = -abs(d["vx"]) * 0.75
                    bounced = True
                if d["y"] - die_sz / 2 < lane_t:
                    d["y"] = lane_t + die_sz / 2
                    d["vy"] = abs(d["vy"]) * 0.75
                    bounced = True
                elif d["y"] + die_sz / 2 > lane_b:
                    d["y"] = lane_b - die_sz / 2
                    d["vy"] = -abs(d["vy"]) * 0.75
                    bounced = True

                if bounced:
                    d["bounces"] += 1
                    d["face"] = random.randint(1, 6)

                d["vx"] *= 0.96
                d["vy"] *= 0.96

                speed = (d["vx"] ** 2 + d["vy"] ** 2) ** 0.5
                if speed > 0.8:
                    all_slow = False
                    if frame_count[0] % 4 == 0:
                        d["face"] = random.randint(1, 6)

                self._draw_single_die(d["x"], d["y"] - die_sz / 2, die_sz, d["face"])

            frame_count[0] += 1

            if (all_slow and frame_count[0] > 15) or frame_count[0] >= 80:
                self._dice_anim_id = None
                self._on_roll_dice_callback()
                return

            self._dice_anim_id = self.after(20, step)

        step()

    # ---------- Move animation ----------

    def _animate_move(self, move: Move) -> None:
        self._anim_hide_point = move.target
        start = self._point_center(move.source, move.player)
        end = self._point_center(move.target, move.player)
        sx, sy, _, _ = self._sc()
        r = CHECKER_RADIUS * sy
        d = max(6, int(r * 2))
        is_white = move.player is Player.WHITE

        sh_photo = shadow_photo(d)
        ch_photo = checker_photo(d, is_white)
        self._photo_refs.append(sh_photo)
        self._photo_refs.append(ch_photo)

        shadow = self._canvas.create_image(
            int(start[0]) + 2, int(start[1]) + 3,
            image=sh_photo, tags=("anim",),
        )
        token = self._canvas.create_image(
            int(start[0]), int(start[1]),
            image=ch_photo, tags=("anim",),
        )
        steps = 16
        dur = 400

        def _ease(t: float) -> float:
            return t * t * (3 - 2 * t)

        def _step(idx: int) -> None:
            if self._destroyed:
                return
            if idx > steps:
                self._canvas.delete(shadow)
                self._canvas.delete(token)
                play_checker_place()
                if self._pending_sequence is None:
                    self._anim_hide_point = None
                    self._draw_checkers()
                if move.captures or move.bears_off:
                    self._explode(end)
                return
            t = _ease(idx / steps)
            nx = start[0] + (end[0] - start[0]) * t
            ny = start[1] + (end[1] - start[1]) * t
            arc = -25 * (4 * t * (1 - t))
            ny += arc
            self._canvas.coords(shadow, int(nx) + 2, int(ny) + 3)
            self._canvas.coords(token, int(nx), int(ny))
            self.after(dur // steps, lambda: _step(idx + 1))

        _step(0)

    def _explode(self, center: tuple[float, float]) -> None:
        if self._destroyed:
            return
        particles = []
        for _ in range(12):
            angle = random.uniform(0, 2 * math.pi)
            speed = random.uniform(15, 40)
            dx = speed * math.cos(angle)
            dy = speed * math.sin(angle)
            p = self._canvas.create_oval(center[0] - 3, center[1] - 3, center[0] + 3, center[1] + 3,
                                         fill=random.choice(["#ff8800", "#ffcc00", "#ff5500", "#ffdd44"]),
                                         outline="", tags=("anim",))
            particles.append((p, dx, dy))
        ring = self._canvas.create_oval(center[0] - 5, center[1] - 5, center[0] + 5, center[1] + 5,
                                        fill="", outline="#ffaa33", width=3, tags=("anim",))

        def _anim(step: int = 0) -> None:
            if self._destroyed or step > 8:
                for p, _, _ in particles:
                    self._canvas.delete(p)
                self._canvas.delete(ring)
                return
            expansion = (step + 1) * 6
            self._canvas.coords(ring, center[0] - expansion, center[1] - expansion, center[0] + expansion, center[1] + expansion)
            for p, dx, dy in particles:
                self._canvas.move(p, dx * 0.35, dy * 0.35)
            self.after(35, lambda: _anim(step + 1))

        _anim()

    def _point_center(self, point: int, player: Player) -> tuple[float, float]:
        if point == BAR_POSITION:
            bar = self._bar_zone_rect()
            _, _, _, h = self._sc()
            return (bar[0] + bar[2]) / 2, h * 0.3 if player is Player.WHITE else h * 0.7
        if point == OFF_POSITION:
            _, _, w, h = self._sc()
            return w - 10, h * 0.3 if player is Player.WHITE else h * 0.7
        x1, y1, x2, y2 = self._point_rect(point)
        _, sy, _, _ = self._sc()
        cx = (x1 + x2) / 2
        r = CHECKER_RADIUS * sy
        if point >= 13:
            return cx, y1 + r
        return cx, y2 - r

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
