"""The game-state contract the engine persists, and the save envelope metadata.

The engine stays ignorant of a game's contents: a game implements ``GameState``
(``snapshot`` / ``restore``) and the engine only moves the resulting dict in and
out of a save file.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from termcade.app.game import GameContext


@runtime_checkable
class GameState(Protocol):
    """Implemented by each game. The engine never inspects the snapshot payload."""

    schema_version: int

    def snapshot(self) -> dict[str, Any]:
        """Return a fully JSON-serializable view of the current state."""
        ...

    @classmethod
    def restore(cls, data: dict[str, Any], ctx: "GameContext") -> "GameState":
        """Rebuild state from a snapshot produced by :meth:`snapshot`."""
        ...


@dataclass
class SaveMeta:
    slot: int
    game_id: str
    title: str
    schema_version: int
    seed: int
    saved_at: str  # ISO-8601 timestamp
