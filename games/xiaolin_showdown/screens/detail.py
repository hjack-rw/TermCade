"""Detail screen — one card's or character's full info."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.widgets import Footer, Header, Static

from termcade.ui.screens.base import EngineScreen
from termcade.ui.widgets import BoxedPanel

from ..logic.models import Card, Character
from ..logic.mechanics.powers import is_gamble
from .format import (
    char_stats,
    display_name,
    effect_line,
    element_text,
    points_label,
    power_name_text,
    stats_line,
    trigger_label,
)


class DetailScreen(EngineScreen):
    BINDINGS = [("escape", "app.pop_screen", "Back")]

    def __init__(self, target: Card | Character, *, is_card: bool) -> None:
        super().__init__()
        self._target = target
        self._is_card = is_card

    def compose(self) -> ComposeResult:
        target = self._target
        power = target.power
        yield Header()
        with BoxedPanel(title=display_name(target.name, upper=True)):
            if isinstance(target, Card):
                line = Text("Element: ")
                line.append_text(element_text(target.element))
                line.append(f"    Type: {target.type.capitalize()}    Points: {points_label(target)}")
                yield Static(line)
                yield Static(f"Stats (F/A/I): {stats_line(target.stats)}")
            else:
                yield Static(f"Affiliation: {target.affiliation.capitalize()}")
                yield Static(f"Stats (F/A/I): {char_stats(target)}")

            # An inalienable player Wu (power id −5..−1) keeps its power hidden.
            hidden = self._is_card and -5 < power.id < 0
            if power.id and not hidden:
                power_line = Text("Power: ")
                power_line.append_text(power_name_text(power))
                # The joke Wu's name, timing and text are the same three question marks. Printing all
                # three says nothing, at length.
                if not is_gamble(power):
                    card_type = target.type if isinstance(target, Card) else None
                    power_line.append(
                        f"  ({trigger_label(power, is_card=self._is_card, card_type=card_type)})"
                    )
                yield Static(power_line, classes="power")
                if power.description and not is_gamble(power):
                    yield Static(power.description, classes="description")

            # What it does, in a line, under the flavour. A hidden power still gets one: the dragon's
            # name stays its own business, but the rule it plays by is not a secret.
            if power.initiative_bonus:
                yield Static(f"Initiative bonus: {power.initiative_bonus:+d}", classes="power")
            elif effect := effect_line(power, is_card=self._is_card):
                yield Static(effect, classes="power")
        yield Footer()
