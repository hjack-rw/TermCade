"""Rules screen — static info explaining how the game plays.

Distinct from the Settings screen: this only informs, it changes nothing.

Grouped by *when* a rule applies, in the order a player meets them: what you do at the vault, what
decides a showdown, and what it costs you. Every rule the game enforces belongs here — one the code
obeys and this screen never states can only be learned by losing a run to it.
"""

from __future__ import annotations

from rich.table import Table
from textual.app import ComposeResult
from textual.widgets import Footer, Header, Static

from termcade.ui.screens.base import EngineScreen
from termcade.ui.widgets import BoxedPanel

RULES: dict[str, list[str]] = {
    "At the vault:": [
        "Depositing and Using a Power share one action a turn — spend it on a power and you bank "
        "nothing.",
        'Same "Initiative Bonuses" don\'t stack — different ones do.',
    ],
    "Calling a showdown:": [
        "Two Showdowns in a row can't use the exact same Challenge and/or Background (when "
        "possible).",
        "The Challenge stat counts double; the other two still count.",
        "A dead heat goes to whoever named the Challenge.",
    ],
    "In the showdown:": [
        "A Wu with a negative stat curses your Opponent: it lands on their side instead.",
        "The Background lifts a Wu of its element and drags down the one against it — and does the "
        "reverse to a curse cast at you.",
    ],
    "What it costs you:": [
        "The loser forfeits every Wu they staked in the Showdown.",
        "The prize Wu is only claimed if the winner's Challenge stat beats 7 — win small and it is "
        "lost.",
    ],
}


class RulesScreen(EngineScreen):
    BINDINGS = [("escape", "app.pop_screen", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        with BoxedPanel(title="RULES"):
            for heading, rules in RULES.items():
                yield Static(heading, classes="rule-heading")
                yield Static(_bullets(rules), classes="rules")
        yield Footer()


def _bullets(rules: list[str]) -> Table:
    """The rules of one section, as a hanging indent.

    A bullet and its text are two columns, not one string: a rule long enough to wrap must come back
    under its own text, not under the bullet. Padding on a ``Static`` indents the whole block and
    cannot do that.
    """
    grid = Table.grid(padding=(0, 1))
    grid.add_column(justify="left", width=1)  # the bullet
    grid.add_column(justify="left", ratio=1)  # the rule, free to wrap under itself
    for rule in rules:
        grid.add_row("•", rule)
    return grid
