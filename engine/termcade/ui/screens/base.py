"""Base screen ("scene") shared by engine and game screens."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from textual.screen import Screen

from termcade.app.game import GameContext

if TYPE_CHECKING:
    from ..app import EngineApp


class EngineScreen(Screen[None]):
    """Common base for every termcade screen.

    Exposes the running :class:`GameContext` as ``self.ctx`` (settings, saves, rng, and the
    game's current state). Helper dialogs (``show_message`` / ``await confirm(...)``) land
    here later.
    """

    @property
    def ctx(self) -> GameContext:
        ctx = cast("EngineApp", self.app).ctx
        assert ctx is not None, "screen has no GameContext (running without a Game)"
        return ctx
