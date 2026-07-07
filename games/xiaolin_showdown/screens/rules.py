"""Rules screen — static info explaining how the game plays.

Distinct from the Settings screen: this only informs, it changes nothing.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.widgets import Footer, Header, Static

from termcade.ui.screens.base import EngineScreen
from termcade.ui.widgets import BoxedPanel

RULES = [
    'Same "Initiative Bonuses" don\'t stack — different ones do.',
    "Two Showdowns in a row can't use the exact same Challenge and/or Background (when possible).",
]


class RulesScreen(EngineScreen):
    BINDINGS = [("escape", "app.pop_screen", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        with BoxedPanel(title="RULES"):
            for index, rule in enumerate(RULES, 1):
                yield Static(f"{index}.  {rule}")
        yield Footer()
