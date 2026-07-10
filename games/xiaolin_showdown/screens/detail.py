"""Detail screen — one card's or character's full info."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.widgets import Footer, Header, Static

from termcade.ui.screens.base import EngineScreen
from termcade.ui.widgets import BoxedPanel

from ..logic.models import Card, Character
from .format import char_stats, element_text, points_label, power_name_text, stats_line, trigger_label


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
        with BoxedPanel(title=target.name.upper().replace("_", " ")):
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
                power_line.append(f"  ({trigger_label(power)})")
                yield Static(power_line, classes="power")
                if power.description:
                    yield Static(power.description, classes="description")
            if power.initiative_bonus:
                yield Static(f"Initiative bonus: {power.initiative_bonus:+d}", classes="power")
        yield Footer()
