"""Character select — pick a playable dragon, then deal a fresh game into the vault.

Feeds the chosen character into ``new_game`` with the current (settings-derived) ruleset.
"""

from __future__ import annotations

from termcade.ui.screens.menu import MenuItem, MenuScreen

from ..logic.catalog import Catalog, load_catalog
from ..logic.settings import XiaolinSettings, is_hard
from ..logic.setup import new_game
from .format import affiliation_icon, char_stats, display_name
from .vault import VaultScreen


class CharacterSelectScreen(MenuScreen):
    menu_title = "CHOOSE YOUR CHARACTER"

    def __init__(self) -> None:
        super().__init__()
        self._catalog: Catalog = load_catalog()

    def menu_items(self) -> list[MenuItem]:
        items = []
        for character in self._catalog.playable_characters:
            parts = character.power.name.split()  # the dragon's power names its element
            element = parts[-1].lower() if parts else ""
            # A plain-string label (not Rich Text) takes the button's CSS colour, so the
            # `elem-*` class tints it and the hover/focus highlight can still override it.
            label = f"{affiliation_icon(character)} {display_name(character.name).upper()}  ({char_stats(character)})"
            items.append(MenuItem(f"char-{character.id}", label, classes=f"elem-{element}"))
        return items

    def on_select(self, item_id: str) -> None:
        character = self._catalog.character(int(item_id.removeprefix("char-")))
        current = self.ctx.settings.current
        settings = XiaolinSettings.from_settings(current)
        self.ctx.state = new_game(
            self._catalog,
            self.ctx.rng,
            character,
            settings=settings,
            hard_opponents=is_hard(current.difficulty),
        )
        self.app.switch_screen(VaultScreen())
