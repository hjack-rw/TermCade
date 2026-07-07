"""Start screen — the root: new game, continue from a save, or quit."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Button, Footer, Header, Static

from termcade.ui.screens.base import EngineScreen
from termcade.ui.screens.save_slot import SaveSlotScreen
from termcade.ui.widgets import BoxedPanel

from .character_select import CharacterSelectScreen
from .rules import RulesScreen
from .settings import SettingsScreen
from .vault import VaultScreen


class StartScreen(EngineScreen):
    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="start-root"):
            yield Static("XIAOLIN SHOWDOWN", id="title")
            yield Static("The Card Game", classes="subtitle")
            with BoxedPanel(title="MENU"):
                yield Button("Play", id="play", variant="primary")
                yield Button("Continue", id="continue")
                yield Button("Rules", id="rules")
                yield Button("Settings", id="settings")
                yield Button("Quit", id="quit")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "play":
            self.app.push_screen(CharacterSelectScreen())
        elif event.button.id == "continue":
            self.app.push_screen(SaveSlotScreen("load", next_screen=VaultScreen))
        elif event.button.id == "rules":
            self.app.push_screen(RulesScreen())
        elif event.button.id == "settings":
            self.app.push_screen(SettingsScreen())
        elif event.button.id == "quit":
            self.app.exit()
