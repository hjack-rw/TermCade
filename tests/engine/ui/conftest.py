"""Fixtures for engine UI tests: boot the real EngineApp around a throwaway fake game.

These tests exercise *engine* mechanics (MenuScreen, ChoiceModal, the save picker) with no game
logic — the fake game is the minimum a Game needs, so anything asserted here is generic to the
engine, not to any cartridge.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from termcade.app.game import Game
from termcade.ui.app import EngineApp
from termcade.ui.screens.base import EngineScreen


class FakeState:
    """The smallest thing satisfying GameState — no gameplay, just a serializable stub."""

    schema_version = 1

    def snapshot(self) -> dict[str, Any]:
        return {}

    @classmethod
    def restore(cls, data: dict[str, Any], ctx: Any) -> "FakeState":
        return cls()


@pytest.fixture
def make_app(tmp_path) -> Callable[..., EngineApp]:
    """Build an EngineApp booted onto ``root_screen`` (a zero-arg EngineScreen factory)."""

    def _make(root_screen: Callable[[], EngineScreen], **game_kw: Any) -> EngineApp:
        game = Game(
            game_id="fake",
            title="Fake",
            state_cls=FakeState,
            root_screen=root_screen,
            **game_kw,
        )
        return EngineApp(game, data_dir=tmp_path, seed=1)

    return _make
