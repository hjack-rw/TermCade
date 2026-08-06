"""Start screen — the root: new game, continue from a save, or quit."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Center, Vertical
from textual.widgets import Footer, Header, Static

from termcade.ui.app import BANNER, BANNER_COMPACT
from termcade.ui.screens.base import EngineScreen
from termcade.ui.screens.save_slot import SaveSlotScreen
from termcade.ui.widgets import BoxedPanel, Button

from ..display._logo import SUBTITLE_ART, TITLE_ART, TITLE_ART_STACKED
from .character_select import CharacterSelectScreen
from ..reference.rules import RulesScreen
from ..reference.settings import SettingsScreen
from .temple import TempleScreen


class StartScreen(EngineScreen):
    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="start-root"):
            # Both wordmarks are mounted; the stylesheet picks one on the `-narrow` breakpoint.
            # Choosing in Python would force a recompose on every resize.
            with Center():
                yield Static(BANNER, id="banner")
                yield Static(BANNER_COMPACT, id="banner-compact")
            with Center():
                yield Static(TITLE_ART, id="title")
                yield Static(TITLE_ART_STACKED, id="title-compact")
            with Center():
                yield Static(SUBTITLE_ART, classes="subtitle")
            with Center():
                with BoxedPanel(title="MENU"):
                    yield Button("Play", id="play", variant="primary")
                    yield Button("Continue", id="continue")
                    yield Button("Rules", id="rules")
                    yield Button("Settings", id="settings")
                    yield Button("Lore", id="lore")
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
        elif event.button.id == "lore":
            # Deferred: rich.markdown/markdown_it are ~65ms of import cost every session pays at
            # boot if this sits at module level, for a screen most sessions never open.
            from ..reference.lore import LoreScreen

            self.app.push_screen(LoreScreen())
        elif event.button.id == "quit":
            self.app.exit()
