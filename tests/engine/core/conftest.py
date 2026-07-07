"""Shared fixtures for core tests: a minimal fake game state."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest


@dataclass
class FakeState:
    """A trivial GameState implementation for exercising the engine core."""

    schema_version: int = 1
    points: int = 0
    hand: list[str] = field(default_factory=list)

    def snapshot(self) -> dict[str, Any]:
        return {"points": self.points, "hand": list(self.hand)}

    @classmethod
    def restore(cls, data: dict[str, Any], ctx: Any) -> "FakeState":
        return cls(points=data["points"], hand=list(data["hand"]))


@pytest.fixture
def fake_state_cls() -> type[FakeState]:
    return FakeState
