"""The base Textual application every termcade game runs on."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.app import App
from textual.widgets import Footer, Header, Static

from .screens.base import EngineScreen


class HelloScreen(EngineScreen):
    """Placeholder scene proving the engine boots; a real menu replaces it later."""

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("TermCade — engine online", id="hello")
        yield Footer()


class EngineApp(App[None]):
    """Base Textual application for termcade games.

    Scaffold: boots straight to a placeholder scene. The next step builds a
    ``GameContext`` (settings, saves, rng) from a ``Game`` descriptor and pushes
    the game's real root screen instead.
    """

    TITLE = "TermCade"

    def on_mount(self) -> None:
        self.push_screen(HelloScreen())
