"""Rules screen — static info explaining how the game plays.

Distinct from the Settings screen: this only informs, it changes nothing.

Grouped by *when* a rule applies, in the order a player meets them: what you do at the vault, what
decides a showdown, and what it costs you. Every rule the game enforces belongs here — one the code
obeys and this screen never states can only be learned by losing a run to it.

The numbers are read from the live settings, never typed twice. A rulebook that says 7 while the
game checks 8 is worse than no rulebook.
"""

from __future__ import annotations

from rich.table import Table
from textual.app import ComposeResult
from textual.widgets import Footer, Header, Static

from termcade.ui.screens.base import EngineScreen
from termcade.ui.widgets import BoxedPanel

from ..logic.settings import XiaolinSettings


def rules_for(settings: XiaolinSettings) -> dict[str, list[str]]:
    """The rulebook, with the game's own numbers in it."""
    return {
        "At the vault:": [
            f"Depositing and Using a Power share {settings.deposit_limit} action a turn — spend it "
            "on a power and you bank nothing.",
            'Same "Initiative Bonuses" don\'t stack — different ones do.',
            f"Bank {settings.point_limit} points and the run is yours.",
        ],
        "Calling a showdown:": [
            "Two Showdowns in a row can't use the exact same Challenge and/or Background (when "
            "possible).",
            "Whoever did NOT call the Challenge names the stakes: how many Wu each side must field, "
            f"up to {settings.max_wager}. Neither duelist can be made to stake more than they hold.",
            "The Challenge stat counts double; the other two still count.",
        ],
        "In the showdown:": [
            "Every round staked gets one Wu. You may add a Boost to any round, but each Boost Wu "
            "works once. Short on Wu? Your Boost gets played as a normal Wu instead.",
            "A Wu with a negative stat curses your Opponent: it lands on their side instead.",
            "The Background lifts a Wu of its element and drags down the one against it — and does "
            "the reverse to a curse cast at you.",
        ],
        "Who takes it:": [
            "Most rounds won. Level, and the wider margin takes it. Level on that too, and it falls "
            "to whoever called the Challenge.",
            "The loser forfeits every Wu they staked in the Showdown.",
            f"The prize Wu is only claimed if the winner's Challenge stat beats "
            f"{settings.prize_threshold} in any round — win small and it is lost.",
        ],
    }


class RulesScreen(EngineScreen):
    BINDINGS = [("escape", "app.pop_screen", "Back")]

    def compose(self) -> ComposeResult:
        settings = XiaolinSettings.from_settings(self.ctx.settings.current)
        yield Header()
        with BoxedPanel(title="RULES"):
            for heading, rules in rules_for(settings).items():
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
