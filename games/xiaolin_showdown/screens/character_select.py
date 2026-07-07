"""Character select — pick a playable dragon, then deal a fresh game into the vault.

Feeds the chosen character into ``new_game`` with the current (settings-derived) ruleset.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.widgets import Button, Footer, Header

from termcade.ui.screens.base import EngineScreen
from termcade.ui.widgets import BoxedPanel

from ..logic.catalog import Catalog, load_catalog
from ..logic.settings import XiaolinSettings
from ..logic.setup import new_game
from .format import affiliation_icon, char_stats
from .vault import VaultScreen


class CharacterSelectScreen(EngineScreen):
    BINDINGS = [("escape", "app.pop_screen", "Back")]

    def __init__(self) -> None:
        super().__init__()
        self._catalog: Catalog = load_catalog()

    def compose(self) -> ComposeResult:
        yield Header()
        with BoxedPanel(title="CHOOSE YOUR DRAGON"):
            for character in self._catalog.playable_characters:
                icon = affiliation_icon(character)
                label = f"{icon} {character.name.upper()}   {char_stats(character)}"
                yield Button(label, id=f"char-{character.id}")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        assert event.button.id is not None
        character = self._catalog.character(int(event.button.id.removeprefix("char-")))
        settings = XiaolinSettings.from_settings(self.ctx.settings.current)
        self.ctx.state = new_game(self._catalog, self.ctx.rng, character, settings=settings)
        self.app.switch_screen(VaultScreen())
