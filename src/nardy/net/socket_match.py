"""Socket-based local match backend for two separate GUI processes."""

from __future__ import annotations

import json
import socket
import threading
from typing import Any

from nardy.domain.engine import GameEngine, build_default_engine
from nardy.domain.models import (
    DiceRoll,
    GameMode,
    GameState,
    Move,
    Player,
    PointState,
    TurnPhase,
    TurnState,
)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


class MatchServer:
    """Run an authoritative game engine over a small TCP JSON protocol."""

    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
        """Initialize server resources and in-memory match state."""
        self._host = host
        self._port = port
        self._engine: GameEngine = build_default_engine()
        self._lock = threading.Lock()
        self._condition = threading.Condition(self._lock)
        self._server: socket.socket | None = None
        self._clients: dict[str, Player] = {}
        self._next_client_id = 1
        self._version = 0

    def start_in_background(self) -> None:
        """Start serving connections in a daemon thread."""
        thread = threading.Thread(target=self.run_forever, daemon=True)
        thread.start()

    def run_forever(self) -> None:
        """Accept and handle client requests forever."""
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind((self._host, self._port))
        self._server.listen(8)
        while True:
            conn, _addr = self._server.accept()
            thread = threading.Thread(
                target=self._handle_client,
                args=(conn,),
                daemon=True,
            )
            thread.start()

    def _handle_client(self, conn: socket.socket) -> None:
        """Serve requests on one socket until the client disconnects."""
        with conn:
            stream = conn.makefile("rwb")
            while True:
                line = stream.readline()
                if not line:
                    return
                try:
                    request = json.loads(line.decode("utf-8"))
                    response = self._process_request(request)
                except Exception as exc:  # noqa: BLE001
                    response = {"ok": False, "error": str(exc), "state": None}
                payload = (json.dumps(response) + "\n").encode("utf-8")
                stream.write(payload)
                stream.flush()

    def _process_request(self, request: dict[str, Any]) -> dict[str, Any]:
        """Apply one protocol action and return the updated state."""
        action = str(request.get("action", ""))
        payload = request.get("payload", {})
        if not isinstance(payload, dict):
            payload = {}

        with self._lock:
            if action == "join":
                return self._join_client()

            client_id = request.get("client_id")
            if not isinstance(client_id, str) or client_id not in self._clients:
                return {
                    "ok": False,
                    "error": "Client is not joined.",
                    "state": self._serialize_state_optional(),
                }
            player = self._clients[client_id]

            if action == "get_state":
                since_version = int(payload.get("since_version", -1))
                wait_ms = int(payload.get("wait_ms", 0))
                if since_version == self._version and wait_ms > 0:
                    self._condition.wait(timeout=wait_ms / 1000)
                return self._ok_response(player)
            if action == "start_game":
                self._ensure_player(player, Player.WHITE)
                mode = GameMode(str(payload["mode"]))
                self._engine.start_new_game(mode)
                self._mark_updated()
                return self._ok_response(player)
            if action == "roll_dice":
                self._ensure_turn(player)
                self._engine.roll_dice()
                self._mark_updated()
                return self._ok_response(player)
            if action == "apply_move":
                self._ensure_turn(player)
                move = _move_from_wire(payload["move"])
                self._engine.apply_move(move)
                self._mark_updated()
                return self._ok_response(player)
            if action == "undo":
                self._engine.undo(player)
                self._mark_updated()
                return self._ok_response(player)
            if action == "can_undo":
                return self._ok_response(player)

            return {
                "ok": False,
                "error": f"Unknown action: {action}",
                "state": self._serialize_state_optional(),
            }

    def _join_client(self) -> dict[str, Any]:
        """Assign one of two fixed players to a new client."""
        if Player.WHITE not in self._clients.values():
            assigned = Player.WHITE
        elif Player.BLACK not in self._clients.values():
            assigned = Player.BLACK
        else:
            return {
                "ok": False,
                "error": "Match already has two players.",
                "state": self._serialize_state_optional(),
            }

        client_id = f"c{self._next_client_id}"
        self._next_client_id += 1
        self._clients[client_id] = assigned
        response = self._ok_response(assigned)
        response["client_id"] = client_id
        response["assigned_player"] = assigned.value
        return response

    def _ok_response(self, player: Player) -> dict[str, Any]:
        """Return a successful response with current state metadata."""
        return {
            "ok": True,
            "error": None,
            "state": self._serialize_state_optional(),
            "can_undo": self._can_undo_for(player),
            "version": self._version,
        }

    def _mark_updated(self) -> None:
        """Increase state version and wake up waiting clients."""
        self._version += 1
        self._condition.notify_all()

    def _serialize_state_optional(self) -> dict[str, Any] | None:
        """Serialize current state when a game already exists."""
        try:
            state = self._engine.state
        except RuntimeError:
            return None
        return _state_to_wire(state)

    def _can_undo_for(self, player: Player) -> bool:
        """Return whether undo is allowed for this player now."""
        try:
            return self._engine.can_undo(player)
        except RuntimeError:
            return False

    def _ensure_turn(self, player: Player) -> None:
        """Reject actions from the non-active player."""
        state = self._engine.state
        if state.current_player is not player:
            raise RuntimeError("It is not your turn.")

    @staticmethod
    def _ensure_player(actual: Player, expected: Player) -> None:
        """Require a concrete player for host-only actions."""
        if actual is not expected:
            raise RuntimeError("Only host player can start the game.")


class RemoteEngineProxy:
    """Expose a GameEngine-like API backed by a socket match server."""

    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
        """Connect to server and join the two-player match."""
        self._host = host
        self._port = port
        self._socket = socket.create_connection((host, port), timeout=5)
        self._socket.settimeout(None)
        self._stream = self._socket.makefile("rwb")
        self._wait_socket: socket.socket | None = None
        self._wait_stream = None
        self._lock = threading.Lock()
        self._wait_lock = threading.Lock()
        self._client_id = ""
        self._player: Player | None = None
        self._state: GameState | None = None
        self._version = -1
        join_response = self._request("join", payload={})
        self._client_id = str(join_response["client_id"])
        self._player = Player(str(join_response["assigned_player"]))
        self._version = int(join_response.get("version", -1))
        self._state = _state_from_wire_optional(join_response.get("state"))
        self._wait_socket = socket.create_connection(
            (self._host, self._port),
            timeout=5,
        )
        self._wait_socket.settimeout(None)
        self._wait_stream = self._wait_socket.makefile("rwb")

    @property
    def player(self) -> Player:
        """Return the player controlled by this process."""
        if self._player is None:
            raise RuntimeError("Client is not assigned to a player.")
        return self._player

    @property
    def state(self) -> GameState:
        """Return last synchronized state."""
        if self._state is None:
            raise RuntimeError("Game is not started yet.")
        return self._state

    def start_new_game(self, mode: GameMode) -> GameState:
        """Request match creation from the server."""
        response = self._request("start_game", payload={"mode": mode.value})
        return self._update_state(response)

    def roll_dice(self) -> GameState:
        """Roll dice on the authoritative server."""
        return self._update_state(self._request("roll_dice", payload={}))

    def apply_move(self, move: Move) -> GameState:
        """Apply one move on the authoritative server."""
        response = self._request(
            "apply_move",
            payload={"move": _move_to_wire(move)},
        )
        return self._update_state(response)

    def undo(self, player: Player) -> GameState:
        """Undo the last completed turn for the given player."""
        _ = player
        return self._update_state(self._request("undo", payload={}))

    def can_undo(self, player: Player) -> bool:
        """Return undo availability for this client's player."""
        _ = player
        response = self._request("can_undo", payload={})
        self._update_state(response)
        return bool(response.get("can_undo", False))

    def available_moves(self) -> tuple[Move, ...]:
        """Return currently legal moves from synchronized state."""
        return self.state.turn.legal_moves

    def poll_state(self) -> GameState | None:
        """Fetch latest state from server for passive updates."""
        response = self._request(
            "get_state",
            payload={"since_version": -1, "wait_ms": 0},
        )
        return self._update_state(response)

    def wait_for_update(self, wait_ms: int = 30000) -> GameState | None:
        """Block until server state changes or timeout expires."""
        response = self._wait_request(
            "get_state",
            payload={
                "since_version": self._version,
                "wait_ms": wait_ms,
            },
        )
        next_version = int(response.get("version", self._version))
        if next_version == self._version:
            return None
        return self._update_state(response)

    def close(self) -> None:
        """Close underlying socket resources."""
        try:
            if self._wait_socket is not None:
                try:
                    self._wait_socket.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
            try:
                self._socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            if self._wait_stream is not None:
                self._wait_stream.close()
            self._stream.close()
        finally:
            if self._wait_socket is not None:
                self._wait_socket.close()
            self._socket.close()

    def _request(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Send one action and decode one response."""
        request = {
            "action": action,
            "payload": payload,
            "client_id": self._client_id,
        }
        message = (json.dumps(request) + "\n").encode("utf-8")
        with self._lock:
            self._stream.write(message)
            self._stream.flush()
            line = self._stream.readline()
        if not line:
            raise RuntimeError("Server disconnected.")
        response = json.loads(line.decode("utf-8"))
        if not response.get("ok"):
            raise RuntimeError(str(response.get("error", "Request failed.")))
        return response

    def _wait_request(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Send blocking long-wait request via dedicated socket."""
        if self._wait_stream is None:
            raise RuntimeError("Wait stream is not available.")
        request = {
            "action": action,
            "payload": payload,
            "client_id": self._client_id,
        }
        message = (json.dumps(request) + "\n").encode("utf-8")
        with self._wait_lock:
            self._wait_stream.write(message)
            self._wait_stream.flush()
            line = self._wait_stream.readline()
        if not line:
            raise RuntimeError("Server disconnected.")
        response = json.loads(line.decode("utf-8"))
        if not response.get("ok"):
            raise RuntimeError(str(response.get("error", "Request failed.")))
        return response

    def _update_state(self, response: dict[str, Any]) -> GameState | None:
        """Update local state cache from wire payload."""
        self._version = int(response.get("version", self._version))
        self._state = _state_from_wire_optional(response.get("state"))
        return self._state


def _state_to_wire(state: GameState) -> dict[str, Any]:
    """Serialize game state into JSON-safe structure."""
    board = [
        {
            "owner": point.owner.value if point.owner is not None else None,
            "checkers": point.checkers,
        }
        for point in state.board
    ]
    return {
        "mode": state.mode.value,
        "board": board,
        "current_player": state.current_player.value,
        "turn": {
            "player": state.turn.player.value,
            "phase": state.turn.phase.value,
            "dice": (
                list(state.turn.dice.values)
                if state.turn.dice is not None
                else None
            ),
            "remaining_pips": list(state.turn.remaining_pips),
            "legal_moves": [_move_to_wire(move) for move in state.turn.legal_moves],
            "moves": [_move_to_wire(move) for move in state.turn.moves],
        },
        "bar": list(state.bar),
        "borne_off": list(state.borne_off),
        "winner": state.winner.value if state.winner is not None else None,
        "turn_number": state.turn_number,
    }


def _state_from_wire_optional(payload: dict[str, Any] | None) -> GameState | None:
    """Deserialize optional state payload."""
    if payload is None:
        return None
    return _state_from_wire(payload)


def _state_from_wire(payload: dict[str, Any]) -> GameState:
    """Deserialize JSON payload into immutable GameState."""
    board = []
    for point in payload["board"]:
        owner_value = point["owner"]
        owner = Player(owner_value) if owner_value is not None else None
        board.append(PointState(owner=owner, checkers=int(point["checkers"])))
    dice_payload = payload["turn"]["dice"]
    dice = None
    if dice_payload is not None:
        dice = DiceRoll.from_values(int(dice_payload[0]), int(dice_payload[1]))
    legal_moves = tuple(
        _move_from_wire(item) for item in payload["turn"]["legal_moves"]
    )
    moves = tuple(_move_from_wire(item) for item in payload["turn"]["moves"])
    return GameState(
        mode=GameMode(payload["mode"]),
        board=tuple(board),
        current_player=Player(payload["current_player"]),
        turn=TurnState(
            player=Player(payload["turn"]["player"]),
            phase=TurnPhase(payload["turn"]["phase"]),
            dice=dice,
            remaining_pips=tuple(
                int(value) for value in payload["turn"]["remaining_pips"]
            ),
            legal_moves=legal_moves,
            moves=moves,
        ),
        bar=(int(payload["bar"][0]), int(payload["bar"][1])),
        borne_off=(int(payload["borne_off"][0]), int(payload["borne_off"][1])),
        winner=(Player(payload["winner"]) if payload["winner"] is not None else None),
        turn_number=int(payload["turn_number"]),
    )


def _move_to_wire(move: Move) -> dict[str, Any]:
    """Serialize Move dataclass to JSON-safe dictionary."""
    return {
        "player": move.player.value,
        "source": move.source,
        "target": move.target,
        "die_value": move.die_value,
        "captures": move.captures,
        "bears_off": move.bears_off,
    }


def _move_from_wire(payload: dict[str, Any]) -> Move:
    """Deserialize Move payload from JSON dictionary."""
    return Move(
        player=Player(payload["player"]),
        source=int(payload["source"]),
        target=int(payload["target"]),
        die_value=int(payload["die_value"]),
        captures=bool(payload.get("captures", False)),
        bears_off=bool(payload.get("bears_off", False)),
    )
