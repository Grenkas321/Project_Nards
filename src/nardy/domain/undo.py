"""Undo and snapshot helpers for immutable game states."""

from __future__ import annotations

from collections.abc import Iterable

from nardy.domain.models import GameState


class UndoUnavailableError(RuntimeError):
    """Raised when the caller requests an undo without stored snapshots."""


class SnapshotStore:
    """Keep a linear history of previous immutable states."""

    def __init__(self, snapshots: Iterable[GameState] | None = None) -> None:
        """Create a snapshot store with optional preloaded history."""
        self._snapshots = list(snapshots or ())

    def clear(self) -> None:
        """Discard all stored snapshots."""
        self._snapshots.clear()

    def push(self, state: GameState) -> None:
        """Store a state so that it can be restored later."""
        self._snapshots.append(state)

    def can_undo(self) -> bool:
        """Return ``True`` when a previous state is available."""
        return bool(self._snapshots)

    def pop(self) -> GameState:
        """Return the latest stored state."""
        if not self._snapshots:
            raise UndoUnavailableError("No snapshots are available for undo.")
        return self._snapshots.pop()
