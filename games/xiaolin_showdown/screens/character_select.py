"""Character select — pick a playable dragon, then deal a fresh game into the temple.

Feeds the chosen character into ``new_game`` with the current (settings-derived) ruleset. A BOSS
run adds one screen between the two: each boss is a distinct mechanic, so a boss is CHOSEN — the
easy and hard tiers deal a random opponent, the boss tier never does.
"""

from __future__ import annotations

from termcade.ui.screens.menu import MenuItem

from ..logic.catalog import Catalog, load_catalog
from ..logic.mechanics.powers import Mechanic, mechanic_of
from ..logic.models import Character
from ..logic.settings import roster_of
from ..logic.setup import new_game
from ..logic.turn import bot_turn
from .base import XiaolinMenu
from .format import affiliation_icon, char_stats, display_name, opponent_move
from .temple import TempleScreen

# A boss's archetype, by the mechanic its power carries — the tooltip in the boss picker. Keyed off
# the power, not the id, so a new boss names its own archetype by the mechanic it is built on.
_BOSS_ARCHETYPE: dict[Mechanic, str] = {
    Mechanic.MORPH: "Elemental Boss",
    Mechanic.WITCHCRAFT: "Shen Gong Wu Boss",
    Mechanic.BEAST_FORM: "Stat Boss",
}


def _character_row(character: Character) -> str:
    """The one label shape both select screens use: icon, NAME, stats in brackets."""
    return f"{affiliation_icon(character)} {display_name(character.name, upper=True)}  ({char_stats(character)})"


def _begin_run(screen: XiaolinMenu, catalog: Catalog, character: Character, opponent: Character | None) -> None:
    """Deal the run and open the temple — shared by both select screens.

    The temple turn is one turn and both of you take it. Every later one of theirs runs as a
    showdown ends; the first has no showdown to end, so it runs here, before the temple opens.
    Without it the opponent sits out the whole opening turn and meets you with a hand they never
    got to shape.
    """
    current = screen.ctx.settings.current
    settings = screen.rules
    state = new_game(
        catalog,
        screen.ctx.rng,
        character,
        settings=settings,
        roster=roster_of(current.difficulty),
        opponent=opponent,
    )
    screen.ctx.state = state

    moves = bot_turn(state, settings, rng=screen.ctx.rng, difficulty=current.difficulty)
    state.bot_turn_done = True
    screen.app.switch_screen(TempleScreen())
    screen.app.notify(
        "\n".join(move.line for move in moves),
        title=opponent_move([move.action for move in moves]),
    )


class CharacterSelectScreen(XiaolinMenu):
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
            items.append(
                MenuItem.indexed("char", character.id, _character_row(character), classes=f"elem-{element}")
            )
        return items

    def on_select(self, item_id: str) -> None:
        character = self._catalog.character(self.index_of(item_id, "char"))
        if roster_of(self.ctx.settings.current.difficulty) == "boss":
            # A boss is picked, never dealt — every boss is its own mechanic, and "which one" is
            # the whole decision. Pushed, so escape returns here to re-pick the character.
            self.app.push_screen(BossSelectScreen(self._catalog, character))
            return
        _begin_run(self, self._catalog, character, None)


class BossSelectScreen(XiaolinMenu):
    """The boss roster, one button each — hovering a boss reads out what its power does."""

    menu_title = "CHOOSE YOUR OPPONENT"

    def __init__(self, catalog: Catalog, character: Character) -> None:
        super().__init__()
        self._catalog = catalog
        self._character = character  # the dragon already chosen, carried into the deal

    def menu_items(self) -> list[MenuItem]:
        return [
            MenuItem.indexed(
                "boss",
                boss.id,
                _character_row(boss),
                tooltip=_BOSS_ARCHETYPE.get(mechanic_of(boss.power)),
            )
            for boss in self._catalog.opponents("boss")
        ]

    def on_select(self, item_id: str) -> None:
        boss = self._catalog.character(self.index_of(item_id, "boss"))
        _begin_run(self, self._catalog, self._character, boss)
