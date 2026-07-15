"""Pygame game screen: board, checkers, dice physics, animations."""

from __future__ import annotations

import math
import random
from collections import defaultdict, deque
from collections.abc import Callable

import pygame
import pygame.gfxdraw
from PIL import ImageDraw as IDraw

from nardy.app.presentation import GameScreenData
from nardy.domain.models import (
    BAR_POSITION,
    OFF_POSITION,
    GameMode,
    GameState,
    Move,
    Player,
)
from nardy.domain.rules_long import LongNardyRules
from nardy.domain.rules_short import ShortNardyRules
from nardy.i18n import Localizer, gettext_noop as N_
from nardy.ui.runtime import Button, get_font
from nardy.ui.sounds import play_checker_place, play_dice_roll
from nardy.ui.textures import (
    bark_texture, board_surface, center_ornament,
    checker_photo, die_photo, pil_to_surface, shadow_photo, triangle_image,
)

BASE_WIDTH = 940
BASE_HEIGHT = 500
CENTER_LANE_WIDTH = 60
POINT_WIDTH = 58
CHECKER_RADIUS = 22
BORDER_WIDTH = 18
PANEL_WIDTH = 200


class GameScreen:
    """Render interactive board, controls and move hints."""

    def __init__(
        self,
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
        """Create the board state and bind player actions."""
        self._translate = localizer.gettext
        self._state = state
        self._data = data
        self._on_roll_dice_callback = on_roll_dice
        self._on_move_selected = on_apply_move
        self._on_undo_move = on_undo_move
        self._on_back_to_menu = on_back_to_menu

        self._selected_source: int | None = None
        self._moves_by_source: dict[int, tuple[Move, ...]] = {}
        self._possible_targets_by_source: dict[int, set[int]] = {}
        self._can_roll = data.can_roll
        self._can_undo_move = data.can_undo_move
        self._anim_hide_point: int | None = None

        self._width = BASE_WIDTH
        self._height = BASE_HEIGHT

        self._board_bg: pygame.Surface | None = None
        self._tri_cache: dict = {}
        self._last_board_size: tuple[int, int] = (0, 0)
        self._last_theme_ver: int = -1

        # Dice animation (fixed-timestep physics)
        self._dice_anim_active = False
        self._dice_phys: list[dict] = []
        self._dice_accum_ms = 0.0
        self._dice_frame_count = 0
        self._dice_anim_max_steps = 80

        # Move animation
        self._move_anim: dict | None = None
        self._pending_sequence: list[Move] | None = None
        self._seq_index = 0
        self._seq_timer_ms = 0.0

        # Explosion particles
        self._explosion: dict | None = None

        undo_text = self._translate(N_("Undo"))
        back_text = self._translate(N_("Back to menu"))
        self._undo_button = Button(
            undo_text, get_font(14, bold=True, text=undo_text), (0, 0),
            self._on_undo_move_click, boxed=True,
        )
        self._back_button = Button(
            back_text, get_font(14, bold=True, text=back_text), (0, 0),
            self._on_back_to_menu, boxed=True,
        )

        self._update_moves_cache()
        if last_move is not None:
            self._start_move_animation(last_move)

    def update_state(
        self, data: GameScreenData, state: GameState,
        last_move: Move | None, can_roll: bool,
    ) -> None:
        """Update screen state for the next frame."""
        self._state = state
        self._data = data
        self._can_roll = can_roll
        self._can_undo_move = data.can_undo_move
        self._selected_source = None
        self._anim_hide_point = last_move.target if last_move is not None else None
        self._update_moves_cache()
        if last_move is not None:
            self._start_move_animation(last_move)

    def _on_undo_move_click(self) -> None:
        if self._on_undo_move:
            self._on_undo_move()

    # ---------- Moves cache ----------

    def _update_moves_cache(self) -> None:
        moves = self._state.turn.legal_moves
        self._moves_by_source = self._index_moves(moves)
        self._possible_targets_by_source = self._compute_reachable_targets()

    def _compute_reachable_targets(self) -> dict[int, set[int]]:
        rules = LongNardyRules() if self._state.mode == GameMode.LONG else ShortNardyRules()
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

    # ---------- Layout (geometry unchanged from tkinter version) ----------

    def _sc(self) -> tuple[float, float, float, float]:
        w = max(self._width, 200)
        h = max(self._height, 200)
        return w / BASE_WIDTH, h / BASE_HEIGHT, w, h

    def _board_metrics(self) -> tuple[float, float, float]:
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

    def _point_triangle(self, point: int) -> list[tuple[float, float]]:
        x1, y1, x2, y2 = self._point_rect(point)
        cx = (x1 + x2) / 2
        if point >= 13:
            return [(x1, y1), (x2, y1), (cx, y2)]
        return [(x1, y2), (x2, y2), (cx, y1)]

    def _bar_zone_rect(self) -> tuple[float, float, float, float]:
        sx, sy, _, h = self._sc()
        bw, pw, cl = self._board_metrics()
        bar_x1 = bw + 6 * pw + 4 * sx
        bar_x2 = bar_x1 + cl - 8 * sx
        return bar_x1, bw + 4 * sy, bar_x2, h - bw - 4 * sy

    def _off_zone_rect(self, top: bool) -> tuple[float, float, float, float]:
        """Off-zone coords in side-panel-local space (origin at panel's top-left)."""
        pw = max(PANEL_WIDTH, 80)
        ph = max(self._height, 200)
        m = 6
        zone_h = (ph / 2 - 25) * 0.80
        if top:
            return m, m, pw - m, m + zone_h
        return m, ph - m - zone_h, pw - m, ph - m

    def _dice_center(self) -> tuple[float, float]:
        sx, sy, w, h = self._sc()
        bw, pw, cl = self._board_metrics()
        return bw + 6 * pw + cl / 2, h / 2

    def _point_center(self, point: int, player: Player) -> tuple[float, float]:
        if point == BAR_POSITION:
            bar = self._bar_zone_rect()
            _, _, _, h = self._sc()
            return (bar[0] + bar[2]) / 2, (h * 0.3 if player is Player.WHITE else h * 0.7)
        if point == OFF_POSITION:
            _, _, w, h = self._sc()
            return w - 10, (h * 0.3 if player is Player.WHITE else h * 0.7)
        x1, y1, x2, y2 = self._point_rect(point)
        _, sy, _, _ = self._sc()
        cx = (x1 + x2) / 2
        r = CHECKER_RADIUS * sy
        if point >= 13:
            return cx, y1 + r
        return cx, y2 - r

    # ---------- Event handling ----------

    def handle_event(self, event: pygame.event.Event) -> None:
        """Process one pygame event."""
        self._undo_button.handle_event(event)
        self._back_button.handle_event(event)

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos
            if mx >= self._width:
                # Click inside side panel — no interactive elements there besides off-zone targets
                self._on_point_click_check(OFF_POSITION, panel_local=(mx - self._width, my))
                return
            self._on_canvas_click(mx, my)

    def _on_canvas_click(self, mx: float, my: float) -> None:
        if self._can_roll and not self._dice_anim_active:
            cx, cy = self._dice_center()
            sx, sy, _, _ = self._sc()
            r = 65 * min(sx, sy)
            if (mx - cx) ** 2 + (my - cy) ** 2 <= r * r:
                self.trigger_roll()
                return

        point = self._hit_test_point(mx, my)
        if point is not None:
            self._on_point_click(point)

    def _hit_test_point(self, mx: float, my: float) -> int | None:
        if self._state.mode is GameMode.SHORT:
            b = self._bar_zone_rect()
            if b[0] <= mx <= b[2] and b[1] <= my <= b[3]:
                return BAR_POSITION
        for point in range(1, 25):
            x1, y1, x2, y2 = self._point_rect(point)
            if x1 <= mx <= x2 and y1 <= my <= y2:
                return point
        return None

    def _on_point_click_check(self, point: int, panel_local: tuple[float, float]) -> None:
        """Handle clicks landing inside the side panel (off-zone targets)."""
        self._on_point_click(point)

    def _on_point_click(self, point: int) -> None:
        if not self._moves_by_source:
            return
        if self._selected_source is None:
            if point in self._moves_by_source:
                self._selected_source = point
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
            return

        self._selected_source = None

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
        self._seq_timer_ms = 0.0
        self._process_next_in_sequence()

    def _process_next_in_sequence(self) -> None:
        if self._pending_sequence is None or self._seq_index >= len(self._pending_sequence):
            self._pending_sequence = None
            if self._move_anim is None:
                # The last hop's animation already finished while the
                # sequence was still "pending" — unhide its checker now.
                self._anim_hide_point = None
            return
        move = self._pending_sequence[self._seq_index]
        self._seq_index += 1
        self._on_move_selected(move)
        self._seq_timer_ms = 500.0

    # ---------- Per-frame update ----------

    def update(self, dt_ms: int) -> None:
        """Advance all active animations."""
        if self._dice_anim_active:
            self._update_dice_physics(dt_ms)
        if self._move_anim is not None:
            self._update_move_animation(dt_ms)
        if self._explosion is not None:
            self._update_explosion(dt_ms)
        if self._pending_sequence is not None and self._seq_timer_ms > 0:
            self._seq_timer_ms -= dt_ms
            if self._seq_timer_ms <= 0:
                self._process_next_in_sequence()

    # ---------- Draw ----------

    def draw(self, surface: pygame.Surface) -> None:
        """Render the full game screen."""
        w, h = surface.get_size()
        controls_h = 54
        self._width = w - PANEL_WIDTH
        self._height = h - controls_h

        board_surf = surface.subsurface(pygame.Rect(0, 0, self._width, self._height))
        panel_surf = surface.subsurface(pygame.Rect(self._width, 0, PANEL_WIDTH, self._height))

        board_surf.fill((42, 21, 8))
        panel_surf.fill((42, 21, 8))

        self._draw_board(board_surf)
        self._draw_side_panel(panel_surf)
        self._draw_highlights(board_surf, panel_surf)
        self._draw_checkers(board_surf, panel_surf)
        self._draw_dice_or_roll_btn(board_surf)
        self._draw_status_overlay(panel_surf)
        self._draw_move_animation(board_surf)
        self._draw_explosion(board_surf)

        # Controls bar
        controls_rect = pygame.Rect(0, h - controls_h, w, controls_h)
        pygame.draw.rect(surface, (32, 16, 6), controls_rect)
        pygame.draw.line(surface, (74, 48, 24), controls_rect.topleft, controls_rect.topright, 2)
        self._undo_button.set_center((w // 3, h - controls_h // 2))
        self._back_button.set_center((2 * w // 3, h - controls_h // 2))
        self._undo_button.enabled = self._can_undo_move
        self._undo_button.draw(surface)
        self._back_button.draw(surface)

    def _draw_board(self, surface: pygame.Surface) -> None:
        sx, sy, w, h = self._sc()
        bw, pw, cl = self._board_metrics()
        iw, ih = int(w), int(h)

        from nardy.ui.textures import _theme_change_counter
        if (iw, ih) != self._last_board_size or self._last_theme_ver != _theme_change_counter:
            self._last_board_size = (iw, ih)
            self._last_theme_ver = _theme_change_counter
            self._tri_cache.clear()
            self._build_board_bg(iw, ih, bw, pw, cl)

        if self._board_bg:
            surface.blit(self._board_bg, (0, 0))

        # Triangles
        for point in range(1, 25):
            x1, y1, x2, y2 = self._point_rect(point)
            tw = max(4, int(x2 - x1))
            th = max(4, int(abs(y2 - y1)))
            ct = "dark" if point % 2 == 0 else "light"
            pt_dir = "down" if point >= 13 else "up"
            key = (tw, th, ct, pt_dir)
            if key not in self._tri_cache:
                tri_img = triangle_image(tw, th, ct, pt_dir)
                self._tri_cache[key] = pil_to_surface(tri_img)
            surface.blit(self._tri_cache[key], (int(x1), int(y1)))

        # Point numbers — centered on the frame strip, with a dark shadow
        font = get_font(max(9, int(10 * sy)), bold=True)
        for point in range(1, 25):
            x1, y1, x2, y2 = self._point_rect(point)
            cx_p = (x1 + x2) / 2
            ty = y1 - bw / 2 if point >= 13 else y2 + bw / 2
            sh_surf = font.render(str(point), True, (20, 10, 4))
            surface.blit(sh_surf, sh_surf.get_rect(center=(cx_p + 1, ty + 1)))
            text_surf = font.render(str(point), True, (244, 226, 190))
            surface.blit(text_surf, text_surf.get_rect(center=(cx_p, ty)))

        # Center ornaments
        orn_size = max(40, int(min(pw * 5, 80 * sy)))
        left_half_cx = int(bw + 3 * pw)
        right_half_cx = int(bw + 6 * pw + cl + 3 * pw)
        mid_y = int(h / 2)
        orn_key = ("orn", orn_size)
        if orn_key not in self._tri_cache:
            orn_img = center_ornament(orn_size, orn_size)
            self._tri_cache[orn_key] = pil_to_surface(orn_img)
        orn_surf = self._tri_cache[orn_key]
        orn_rect = orn_surf.get_rect()
        for ox in (left_half_cx, right_half_cx):
            r = orn_surf.get_rect(center=(ox, mid_y))
            surface.blit(orn_surf, r)

        if self._state.mode is GameMode.SHORT:
            bar = self._bar_zone_rect()
            pygame.draw.rect(surface, (216, 204, 180), pygame.Rect(bar[0], bar[1], bar[2] - bar[0], bar[3] - bar[1]))
            pygame.draw.rect(surface, (184, 168, 140), pygame.Rect(bar[0], bar[1], bar[2] - bar[0], bar[3] - bar[1]), width=2)

        # Border
        ibw = int(bw)
        fr = int(bw + 12 * pw + cl + bw)
        pygame.draw.rect(surface, (42, 21, 8), pygame.Rect(2, 2, fr - 2, ih - 4), width=3)
        pygame.draw.rect(surface, (74, 48, 24), pygame.Rect(ibw - 1, ibw - 1, fr - 2 * ibw + 2, ih - 2 * ibw + 2), width=2)

    def _build_board_bg(self, w: int, h: int, bw: float, pw: float, cl: float) -> None:
        """Compose board: bark frame, playing surface, dark border between."""
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

        bd = IDraw.Draw(board)
        border_col = (40, 25, 12)
        bw_line = max(2, ibw // 5)
        bd.rectangle([ibw - bw_line, ibw - bw_line, bar_x, h - ibw + bw_line],
                     fill=None, outline=border_col, width=bw_line)
        bd.rectangle([bar_x + bar_w, ibw - bw_line, field_right + bw_line, h - ibw + bw_line],
                     fill=None, outline=border_col, width=bw_line)
        bd.rectangle([bar_x - bw_line, ibw - bw_line, bar_x + bar_w + bw_line, h - ibw + bw_line],
                     fill=None, outline=border_col, width=bw_line)

        self._board_bg = pil_to_surface(board)

    # ---------- Checkers ----------

    def _draw_checkers(self, board_surf: pygame.Surface, panel_surf: pygame.Surface) -> None:
        for point in range(1, 25):
            ps = self._state.point(point)
            if ps.checkers:
                self._draw_stack(board_surf, point, ps.owner, ps.checkers)
        self._draw_bar_stack(board_surf, Player.WHITE, self._state.bar_for(Player.WHITE), True)
        self._draw_bar_stack(board_surf, Player.BLACK, self._state.bar_for(Player.BLACK), False)
        self._draw_off_counter(panel_surf, Player.WHITE, self._state.borne_off_for(Player.WHITE), True)
        self._draw_off_counter(panel_surf, Player.BLACK, self._state.borne_off_for(Player.BLACK), False)

    MAX_VISIBLE_STACK = 6

    def _draw_stack(self, surface: pygame.Surface, point: int, owner: Player | None, count: int) -> None:
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

        # Tall piles collapse into an unreadable caterpillar — show at most
        # MAX_VISIBLE_STACK checkers and a count badge on the top one.
        visible = min(count, self.MAX_VISIBLE_STACK)
        avail = abs(y2 - y1) - r
        ideal_step = r * 1.6
        step = min(ideal_step, avail / max(visible, 1)) if visible > 1 else 0

        last_cy = y1 + r if point >= 13 else y2 - r
        for idx in range(visible):
            cy = (y1 + r + idx * step) if point >= 13 else (y2 - r - idx * step)
            self._draw_3d_checker(surface, cx, cy, r, owner)
            last_cy = cy

        if count > visible:
            badge_font = get_font(max(9, int(r * 0.8)), bold=True)
            badge = badge_font.render(str(count), True,
                                      (60, 40, 24) if owner is Player.WHITE else (240, 224, 196))
            surface.blit(badge, badge.get_rect(center=(int(cx), int(last_cy))))

    def _draw_3d_checker(self, surface: pygame.Surface, cx: float, cy: float, r: float, owner: Player) -> None:
        d = max(6, int(r * 2))
        is_white = owner is Player.WHITE
        sh = shadow_photo(d)
        surface.blit(sh, sh.get_rect(center=(int(cx) + 2, int(cy) + 3)))
        ch = checker_photo(d, is_white)
        surface.blit(ch, ch.get_rect(center=(int(cx), int(cy))))

    def _draw_bar_stack(self, surface: pygame.Surface, player: Player, count: int, top: bool) -> None:
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
            self._draw_3d_checker(surface, cx, cy, r, player)
        if count > 5:
            ty = base_y + 5 * step + 8 if top else base_y - 5 * step - 8
            font = get_font(max(7, int(9 * sy)), bold=True)
            text_surf = font.render(str(count), True, (200, 168, 122))
            surface.blit(text_surf, text_surf.get_rect(center=(cx, ty)))

    def _draw_off_counter(self, surface: pygame.Surface, player: Player, count: int, top: bool) -> None:
        if count == 0:
            return
        zone = self._off_zone_rect(top=top)
        cx = (zone[0] + zone[2]) / 2
        r = min(14, (zone[2] - zone[0]) / 2.5)
        # Keep clear of the panel's header strip (top) and count text (bottom).
        header_h, footer_h = 36, 30
        z_top = zone[1] + header_h
        z_bot = zone[3] - footer_h
        zone_h = max(1, z_bot - z_top)
        step = min(r * 0.9, (zone_h - 2 * r) / max(count - 1, 1)) if count > 1 else 0
        for idx in range(count):
            cy = z_top + r + idx * step
            self._draw_3d_checker(surface, cx, cy, r, player)

    # ---------- Highlights ----------

    def _draw_highlights(self, board_surf: pygame.Surface, panel_surf: pygame.Surface) -> None:
        for source in self._moves_by_source:
            if source == BAR_POSITION:
                if self._state.mode is GameMode.SHORT:
                    bar = self._bar_zone_rect()
                    r = pygame.Rect(bar[0] - 3, bar[1] - 3, bar[2] - bar[0] + 6, bar[3] - bar[1] + 6)
                    pygame.draw.rect(board_surf, (68, 221, 102), r, width=5)
                continue
            tri = self._point_triangle(source)
            _aa_polygon_outline(board_surf, (68, 221, 102), tri, width=5)

        if self._selected_source is None:
            return

        if self._selected_source != BAR_POSITION:
            tri = self._point_triangle(self._selected_source)
            _aa_polygon_outline(board_surf, (255, 170, 34), tri, width=4)

        targets = self._possible_targets_by_source.get(self._selected_source, set())
        for target in targets:
            if target == OFF_POSITION:
                off = self._off_zone_rect(top=self._state.current_player is Player.WHITE)
                r = pygame.Rect(off[0], off[1], off[2] - off[0], off[3] - off[1])
                pygame.draw.rect(panel_surf, (68, 136, 255), r, width=5)
                continue
            tri = self._point_triangle(target)
            _aa_polygon_outline(board_surf, (68, 136, 255), tri, width=5)

    # ---------- Side panel ----------

    def _draw_side_panel(self, surface: pygame.Surface) -> None:
        """Score-board panel: labeled off-zones with counts per player."""
        t = self._translate
        current = self._state.current_player
        for top in (True, False):
            player = Player.WHITE if top else Player.BLACK
            zone = self._off_zone_rect(top=top)
            r = pygame.Rect(zone[0], zone[1], zone[2] - zone[0], zone[3] - zone[1])
            pygame.draw.rect(surface, (52, 32, 18), r, border_radius=6)
            border = (212, 176, 112) if player is current else (90, 58, 32)
            pygame.draw.rect(surface, border, r, width=2, border_radius=6)

            # Header strip: player color chip + name
            name = t(N_("White")) if player is Player.WHITE else t(N_("Black"))
            font = get_font(13, bold=True, text=name)
            chip_r = 7
            name_surf = font.render(name, True,
                                    (240, 223, 192) if player is current else (168, 136, 96))
            total_w = chip_r * 2 + 6 + name_surf.get_width()
            chip_x = r.centerx - total_w // 2 + chip_r
            chip_y = r.top + 16
            chip_color = (240, 236, 226) if player is Player.WHITE else (60, 38, 24)
            pygame.gfxdraw.filled_circle(surface, chip_x, chip_y, chip_r, chip_color)
            pygame.gfxdraw.aacircle(surface, chip_x, chip_y, chip_r, (20, 12, 6))
            surface.blit(name_surf, (chip_x + chip_r + 6, chip_y - name_surf.get_height() // 2))
            pygame.draw.line(surface, (90, 58, 32),
                             (r.left + 8, r.top + 30), (r.right - 8, r.top + 30), 1)

            # Borne-off count at the bottom of the zone
            count = self._state.borne_off_for(player)
            count_font = get_font(15, bold=True)
            count_surf = count_font.render(f"{count} / 15", True, (212, 192, 160))
            surface.blit(count_surf, count_surf.get_rect(
                midbottom=(r.centerx, r.bottom - 8)))

    def _draw_status_overlay(self, surface: pygame.Surface) -> None:
        """Framed status card in the gap between the two off-zones."""
        top_zone = self._off_zone_rect(top=True)
        bot_zone = self._off_zone_rect(top=False)
        gap_top = top_zone[3]
        gap_bot = bot_zone[1]
        card = pygame.Rect(int(top_zone[0]), int(gap_top + 8),
                           int(top_zone[2] - top_zone[0]), int(gap_bot - gap_top - 16))
        pygame.draw.rect(surface, (46, 28, 16), card, border_radius=6)
        pygame.draw.rect(surface, (110, 72, 40), card, width=2, border_radius=6)

        cx_info = card.centerx
        text_w = max(40, card.width - 16)
        fsz = max(10, min(14, card.height // 7))
        font = get_font(fsz, text=self._data.status + self._data.subtitle)
        lines: list[pygame.Surface] = []
        for line in (self._data.status, self._data.subtitle):
            for wl in _wrap(line, font, int(text_w)):
                lines.append(font.render(wl, True, (222, 200, 166)))
        line_h = font.get_height() + 3
        total_h = line_h * len(lines)
        ly = card.centery - total_h // 2 + line_h // 2
        for surf_line in lines:
            surface.blit(surf_line, surf_line.get_rect(center=(cx_info, ly)))
            ly += line_h

    # ---------- Roll button & dice ----------

    def _draw_dice_or_roll_btn(self, surface: pygame.Surface) -> None:
        if self._can_roll and not self._dice_anim_active:
            self._draw_roll_button(surface)
        else:
            dice = self._state.turn.dice
            if dice is not None and not self._dice_anim_active:
                self._draw_dice_on_board(surface, dice.values[0], dice.values[1])
            elif self._dice_anim_active:
                for d in self._dice_phys:
                    self._draw_single_die(surface, d["x"], d["y"] - d["sz"] / 2, d["sz"], d["face"])

    def _draw_roll_button(self, surface: pygame.Surface) -> None:
        cx, cy = self._dice_center()
        sx, sy, _, _ = self._sc()
        r = 65 * min(sx, sy)
        cxi, cyi = int(cx), int(cy)

        _aa_filled_circle(surface, (10, 6, 4), cxi + 3, cyi + 4, int(r))
        for i in range(10):
            t = i / 9
            cr = r * (1.0 - t * 0.02)
            color = (min(255, int(150 + t * 50)), int(28 + t * 28), int(22 + t * 22))
            _aa_filled_circle(surface, color, cxi, cyi, int(cr))
        rim_w = max(2, int(r * 0.07))
        for i in range(rim_w):
            pygame.gfxdraw.aacircle(surface, cxi, cyi, int(r) - i, (122, 26, 18))

        shine_rect = pygame.Rect(0, 0, r, r * 0.55)
        shine_rect.center = (cx, cy - r * 0.32)
        pygame.gfxdraw.filled_ellipse(
            surface, int(cx), int(cy - r * 0.32), int(r / 2), int(r * 0.275), (232, 90, 74),
        )
        pygame.gfxdraw.aaellipse(
            surface, int(cx), int(cy - r * 0.32), int(r / 2), int(r * 0.275), (232, 90, 74),
        )

        font_sz = max(9, int(13 * min(sx, sy)))
        roll_text = self._translate(N_("Roll dice"))
        font = get_font(font_sz, bold=True, text=roll_text)
        text_surf = font.render(roll_text, True, (255, 255, 255))
        surface.blit(text_surf, text_surf.get_rect(center=(cx, cy)))

    def _draw_dice_on_board(self, surface: pygame.Surface, v1: int, v2: int, ox: float = 0, oy: float = 0) -> None:
        cx, cy = self._dice_center()
        sx, sy, _, _ = self._sc()
        die_sz = min(42 * sx, 42 * sy)
        gap = 6 * sy
        self._draw_single_die(surface, cx + ox, cy - die_sz - gap / 2 + oy, die_sz, v1)
        self._draw_single_die(surface, cx + ox, cy + gap / 2 + oy, die_sz, v2)

    def _draw_single_die(self, surface: pygame.Surface, x: float, y: float, sz: float, value: int) -> None:
        isz = max(8, int(sz))
        photo = die_photo(isz, value)
        rect = photo.get_rect(center=(int(x), int(y + sz / 2)))
        surface.blit(photo, rect)

    # ---------- Roll trigger & dice physics (fixed 20ms timestep) ----------

    def trigger_roll(self) -> None:
        """Programmatically trigger dice roll with animation.

        Used both for the human's own click (already gated by ``can_roll``
        in ``_on_canvas_click`` before this is called) and for the AI's
        scheduled roll, which must fire even while the board is locked
        (``can_roll=False``) during the AI's own turn.
        """
        if self._dice_anim_active:
            return
        self._can_roll = False
        self._start_dice_animation()

    def _start_dice_animation(self) -> None:
        cx, cy = self._dice_center()
        sx, sy, _, h = self._sc()
        bw, pw, cl = self._board_metrics()
        die_sz = min(36 * sx, 36 * sy)

        lane_l = bw + 6 * pw + 4
        lane_r = lane_l + cl - 8
        lane_t = bw + 10
        lane_b = h - bw - 10

        self._dice_phys = [
            {"x": cx - 5, "y": lane_t + die_sz, "sz": die_sz,
             "vx": random.uniform(-6, 6), "vy": random.uniform(6, 12),
             "face": random.randint(1, 6), "lane_l": lane_l, "lane_r": lane_r,
             "lane_t": lane_t, "lane_b": lane_b},
            {"x": cx + 5, "y": lane_b - die_sz, "sz": die_sz,
             "vx": random.uniform(-6, 6), "vy": random.uniform(-12, -6),
             "face": random.randint(1, 6), "lane_l": lane_l, "lane_r": lane_r,
             "lane_t": lane_t, "lane_b": lane_b},
        ]
        self._dice_frame_count = 0
        self._dice_accum_ms = 0.0
        self._dice_anim_active = True
        play_dice_roll()

    def _update_dice_physics(self, dt_ms: int) -> None:
        self._dice_accum_ms += dt_ms
        step_ms = 20.0
        while self._dice_accum_ms >= step_ms:
            self._dice_accum_ms -= step_ms
            self._tick_dice_physics()
            if not self._dice_anim_active:
                break

    def _tick_dice_physics(self) -> None:
        die_sz = self._dice_phys[0]["sz"]
        all_slow = True
        for d in self._dice_phys:
            d["x"] += d["vx"]
            d["y"] += d["vy"]

            bounced = False
            if d["x"] - die_sz / 2 < d["lane_l"]:
                d["x"] = d["lane_l"] + die_sz / 2
                d["vx"] = abs(d["vx"]) * 0.75
                bounced = True
            elif d["x"] + die_sz / 2 > d["lane_r"]:
                d["x"] = d["lane_r"] - die_sz / 2
                d["vx"] = -abs(d["vx"]) * 0.75
                bounced = True
            if d["y"] - die_sz / 2 < d["lane_t"]:
                d["y"] = d["lane_t"] + die_sz / 2
                d["vy"] = abs(d["vy"]) * 0.75
                bounced = True
            elif d["y"] + die_sz / 2 > d["lane_b"]:
                d["y"] = d["lane_b"] - die_sz / 2
                d["vy"] = -abs(d["vy"]) * 0.75
                bounced = True

            if bounced:
                d["face"] = random.randint(1, 6)

            d["vx"] *= 0.96
            d["vy"] *= 0.96

            speed = (d["vx"] ** 2 + d["vy"] ** 2) ** 0.5
            if speed > 0.8:
                all_slow = False
                if self._dice_frame_count % 4 == 0:
                    d["face"] = random.randint(1, 6)

        self._dice_frame_count += 1

        if (all_slow and self._dice_frame_count > 15) or self._dice_frame_count >= self._dice_anim_max_steps:
            self._dice_anim_active = False
            self._on_roll_dice_callback()

    # ---------- Move animation (time-based, not fixed-step) ----------

    def _start_move_animation(self, move: Move) -> None:
        if self._move_anim is not None:
            # A previous animation never reached completion (e.g. a remote/AI
            # move arrived faster than the prior one finished) — snap it to
            # its end state instead of dropping it, so its checker never
            # vanishes mid-flight.
            self._finish_move_animation()
        self._anim_hide_point = move.target
        start = self._point_center(move.source, move.player)
        end = self._point_center(move.target, move.player)
        sx, sy, _, _ = self._sc()
        r = CHECKER_RADIUS * sy
        self._move_anim = {
            "move": move, "start": start, "end": end, "r": r,
            "elapsed_ms": 0.0, "duration_ms": 400.0,
        }

    def _finish_move_animation(self) -> None:
        anim = self._move_anim
        if anim is None:
            return
        move = anim["move"]
        play_checker_place()
        # Always unhide: the checker has landed. The next sequence hop (if
        # any) sets its own hide point when its animation starts. Gating
        # this on the sequence still being "pending" left the final hop's
        # checker invisible until the opponent's roll, because the sequence
        # cleanup timer (500ms) outlives the flight animation (400ms).
        self._anim_hide_point = None
        if move.captures or move.bears_off:
            self._start_explosion(anim["end"])
        self._move_anim = None

    def _update_move_animation(self, dt_ms: int) -> None:
        anim = self._move_anim
        if anim is None:
            return
        anim["elapsed_ms"] += dt_ms
        if anim["elapsed_ms"] >= anim["duration_ms"]:
            self._finish_move_animation()

    def _draw_move_animation(self, surface: pygame.Surface) -> None:
        anim = self._move_anim
        if anim is None:
            return
        move = anim["move"]
        start, end, r = anim["start"], anim["end"], anim["r"]
        t = min(1.0, anim["elapsed_ms"] / anim["duration_ms"])
        eased = t * t * (3 - 2 * t)
        nx = start[0] + (end[0] - start[0]) * eased
        ny = start[1] + (end[1] - start[1]) * eased
        arc = -25 * (4 * eased * (1 - eased))
        ny += arc

        d = max(6, int(r * 2))
        is_white = move.player is Player.WHITE
        sh = shadow_photo(d)
        surface.blit(sh, sh.get_rect(center=(int(nx) + 2, int(ny) + 3)))
        ch = checker_photo(d, is_white)
        surface.blit(ch, ch.get_rect(center=(int(nx), int(ny))))

    # ---------- Explosion (time-based particles) ----------

    def _start_explosion(self, center: tuple[float, float]) -> None:
        particles = []
        for _ in range(12):
            angle = random.uniform(0, 2 * math.pi)
            speed = random.uniform(15, 40)
            particles.append({
                "dx": speed * math.cos(angle), "dy": speed * math.sin(angle),
                "color": random.choice([(255, 136, 0), (255, 204, 0), (255, 85, 0), (255, 221, 68)]),
                "x": center[0], "y": center[1],
            })
        self._explosion = {
            "center": center, "particles": particles, "elapsed_ms": 0.0, "duration_ms": 280.0,
        }

    def _update_explosion(self, dt_ms: int) -> None:
        exp = self._explosion
        if exp is None:
            return
        exp["elapsed_ms"] += dt_ms
        frac = dt_ms / 35.0
        for p in exp["particles"]:
            p["x"] += p["dx"] * 0.35 * frac
            p["y"] += p["dy"] * 0.35 * frac
        if exp["elapsed_ms"] >= exp["duration_ms"]:
            self._explosion = None

    def _draw_explosion(self, surface: pygame.Surface) -> None:
        exp = self._explosion
        if exp is None:
            return
        step = min(8, int(exp["elapsed_ms"] / 35.0))
        expansion = (step + 1) * 6
        cx, cy = exp["center"]
        pygame.draw.circle(surface, (255, 170, 51), (cx, cy), expansion, width=3)
        for p in exp["particles"]:
            pygame.draw.circle(surface, p["color"], (int(p["x"]), int(p["y"])), 3)


def _aa_filled_circle(
    surface: pygame.Surface, color: tuple[int, int, int], cx: int, cy: int, r: int,
) -> None:
    """Draw a filled circle with a smooth (anti-aliased) edge."""
    if r <= 0:
        return
    pygame.gfxdraw.filled_circle(surface, cx, cy, r, color)
    pygame.gfxdraw.aacircle(surface, cx, cy, r, color)


def _aa_polygon_outline(
    surface: pygame.Surface, color: tuple[int, int, int], points: list[tuple[float, float]], width: int = 3,
) -> None:
    """Draw a smooth (anti-aliased) polygon outline by nesting AA rings inward."""
    cx = sum(p[0] for p in points) / len(points)
    cy = sum(p[1] for p in points) / len(points)
    for i in range(width):
        ring = []
        for x, y in points:
            dx, dy = x - cx, y - cy
            dist = math.hypot(dx, dy) or 1.0
            factor = max(0.0, (dist - i) / dist)
            ring.append((int(round(cx + dx * factor)), int(round(cy + dy * factor))))
        pygame.gfxdraw.aapolygon(surface, ring, color)


def _wrap(text: str, font: pygame.font.Font, max_width: int) -> list[str]:
    """Word-wrap a single line of text to fit max_width pixels."""
    words = text.split(" ")
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if font.size(candidate)[0] <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [""]
