"""Start screen — the root: new game, continue from a save, or quit."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Center, Vertical
from textual.widgets import Footer, Header, Static

from termcade.ui.app import BANNER
from termcade.ui.screens.base import EngineScreen
from termcade.ui.screens.save_slot import SaveSlotScreen
from termcade.ui.widgets import BoxedPanel, Button

from ._logo import SUBTITLE_ART, TITLE_ART
from .character_select import CharacterSelectScreen
from .rules import RulesScreen
from .settings import SettingsScreen
from .temple import TempleScreen


class StartScreen(EngineScreen):
    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="start-root"):
            with Center():
                yield Static(BANNER, id="banner")
            with Center():
                yield Static(TITLE_ART, id="title")
            with Center():
                yield Static(SUBTITLE_ART, classes="subtitle")
            with Center():
                with BoxedPanel(title="MENU"):
                    yield Button("Play", id="play", variant="primary")
                    yield Button("Continue", id="continue")
                    yield Button("Rules", id="rules")
                    yield Button("Settings", id="settings")
                    yield Button("Quit", id="quit")
        yield Static(f"v{self.game.version}", id="version")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "play":
            self.app.push_screen(CharacterSelectScreen())
        elif event.button.id == "continue":
            self.app.push_screen(SaveSlotScreen("load", next_screen=TempleScreen))
        elif event.button.id == "rules":
            self.app.push_screen(RulesScreen())
        elif event.button.id == "settings":
            self.app.push_screen(SettingsScreen())
        elif event.button.id == "quit":
            self.app.exit()
