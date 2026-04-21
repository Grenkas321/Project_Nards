"""Integration and unit tests for socket-based match synchronization."""

from __future__ import annotations

import socket
import threading
import time

import pytest

from nardy.domain.models import GameMode
from nardy.net.socket_match import (
    MatchServer,
    RemoteEngineProxy,
    _state_from_wire,
    _state_to_wire,
)


def test_socket_clients_receive_distinct_player_roles() -> None:
    """First two joined clients should receive white and black roles."""
    port = _free_port()
    server = MatchServer(port=port)
    server.start_in_background()
    time.sleep(0.05)

    white = RemoteEngineProxy(port=port)
    black = RemoteEngineProxy(port=port)

    try:
        assert white.player.value == "white"
        assert black.player.value == "black"
    finally:
        white.close()
        black.close()


def test_socket_match_rejects_third_player_join() -> None:
    """Only two clients should be allowed in one local match."""
    port = _free_port()
    server = MatchServer(port=port)
    server.start_in_background()
    time.sleep(0.05)

    first = RemoteEngineProxy(port=port)
    second = RemoteEngineProxy(port=port)

    try:
        with pytest.raises(RuntimeError, match="two players"):
            RemoteEngineProxy(port=port)
    finally:
        first.close()
        second.close()


def test_wait_for_update_returns_none_when_state_is_unchanged() -> None:
    """Long wait should timeout and return ``None`` without state changes."""
    port = _free_port()
    server = MatchServer(port=port)
    server.start_in_background()
    time.sleep(0.05)

    client = RemoteEngineProxy(port=port)
    try:
        client.poll_state()
        assert client.wait_for_update(wait_ms=40) is None
    finally:
        client.close()


def test_wait_for_update_unblocks_when_opponent_moves() -> None:
    """Waiting client should receive fresh state after remote move."""
    port = _free_port()
    server = MatchServer(port=port)
    server.start_in_background()
    time.sleep(0.05)

    white = RemoteEngineProxy(port=port)
    black = RemoteEngineProxy(port=port)

    try:
        white.start_new_game(GameMode.LONG)
        white.roll_dice()
        black.poll_state()
        waiting_result: list[object | None] = [None]

        def _wait() -> None:
            waiting_result[0] = black.wait_for_update(wait_ms=1000)

        thread = threading.Thread(target=_wait)
        thread.start()
        time.sleep(0.05)

        move = white.state.turn.legal_moves[0]
        white.apply_move(move)
        thread.join(timeout=2)

        updated_state = waiting_result[0]
        assert updated_state is not None
        assert updated_state.turn.moves
        assert updated_state.turn.moves[-1].source == move.source
        assert updated_state.turn.moves[-1].target == move.target
    finally:
        white.close()
        black.close()


def test_long_wait_does_not_block_active_player_actions() -> None:
    """Action requests should stay responsive while peer waits for updates."""
    port = _free_port()
    server = MatchServer(port=port)
    server.start_in_background()
    time.sleep(0.05)

    white = RemoteEngineProxy(port=port)
    black = RemoteEngineProxy(port=port)

    try:
        white.start_new_game(GameMode.LONG)
        black.poll_state()
        wait_thread = threading.Thread(
            target=lambda: black.wait_for_update(wait_ms=1200),
        )
        wait_thread.start()
        time.sleep(0.05)

        started_at = time.monotonic()
        white.roll_dice()
        elapsed = time.monotonic() - started_at

        assert elapsed < 0.5
        wait_thread.join(timeout=2)
    finally:
        white.close()
        black.close()


def test_state_wire_roundtrip_preserves_critical_fields() -> None:
    """Serialization helpers should roundtrip game mode and board counters."""
    port = _free_port()
    server = MatchServer(port=port)
    server.start_in_background()
    time.sleep(0.05)

    client = RemoteEngineProxy(port=port)
    try:
        state = client.start_new_game(GameMode.SHORT)
        payload = _state_to_wire(state)
        restored = _state_from_wire(payload)
        assert restored.mode is GameMode.SHORT
        assert restored.current_player == state.current_player
        assert restored.bar == state.bar
        assert restored.borne_off == state.borne_off
        assert restored.point(24).checkers == state.point(24).checkers
    finally:
        client.close()


def _free_port() -> int:
    """Allocate a free localhost TCP port for temporary test servers."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
