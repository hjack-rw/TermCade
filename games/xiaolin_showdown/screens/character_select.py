"""Character select — pick a playable dragon, then deal a fresh game into the temple.

Feeds the chosen character into ``new_game`` with the current (settings-derived) ruleset.
"""

from __future__ import annotations

from termcade.ui.screens.menu import MenuItem, MenuScreen

from ..logic.catalog import Catalog, load_catalog
from ..logic.settings import XiaolinSettings, roster_of
from ..logic.setup import new_game
from ..logic.turn import bot_turn
from .format import affiliation_icon, char_stats, display_name, opponent_move
from .temple import TempleScreen


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
        state = new_game(
            self._catalog,
            self.ctx.rng,
            character,
            settings=settings,
            roster=roster_of(current.difficulty),
        )
        self.ctx.state = state

        # The temple turn is one turn and both of you take it. Every later one of theirs runs as a
        # showdown ends; the first has no showdown to end, so it runs here, before the temple opens.
        # Without it the opponent sits out the whole opening turn and meets you with a hand they
        # never got to shape.
        moves = bot_turn(state, settings, rng=self.ctx.rng, difficulty=current.difficulty)
        state.bot_turn_done = True
        self.app.switch_screen(TempleScreen())
        self.app.notify(
            "\n".join(move.line for move in moves),
            title=opponent_move([move.action for move in moves]),
        )
