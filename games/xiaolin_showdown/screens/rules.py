"""Rules screen — static info explaining how the game plays.

Distinct from the Settings screen: this only informs, it changes nothing.

Grouped by *when* a rule applies, in the order a player meets them: what you do at the vault, what
decides a showdown, and what it costs you. Every rule the game enforces belongs here — one the code
obeys and this screen never states can only be learned by losing a run to it.

The numbers are read from the live settings, never typed twice. A rulebook that says 7 while the
game checks 8 is worse than no rulebook.
"""

from __future__ import annotations

from rich.console import Console, ConsoleOptions, RenderResult
from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.widgets import Footer, Header, Static

from termcade.ui.screens.base import EngineScreen
from termcade.ui.widgets import BoxedPanel

from ..logic.settings import XiaolinSettings


def rules_for(settings: XiaolinSettings) -> dict[str, list[str]]:
    """The rulebook, with the game's own numbers in it."""
    return {
        "At the vault:": [
            f"You get {settings.deposit_limit} action a turn: deposit a Wu for its points, or use "
            "its power. Never both!",
            "Depositing a Wu forfeits its power. You are vaulting it, not spending it.",
            f"You may also draw {settings.draw_limit} Wu a turn from your own Deck to shuffle Cards.",
            f"Your hand holds {settings.max_hand_size} Wu. Over that, you shelve one back to your Deck.",
            "Left with nothing you can field? The pile deals you back in.",
            "Your opponent takes the same turn you do.",
            f"Bank {settings.point_limit} points and the run is yours!",
        ],
        "Calling a Showdown:": [
            "Matching Initiative Bonuses do not stack. Different ones do.",
            "The higher Initiative names the Challenge. Tie, and a coin toss decides it.",
            "The Challenge can be one stat, or a Tournament across all three.",
            f"Name a stat and your opponent names the stakes, up to {settings.max_wager} Wu each.",
            f"A Tournament costs {settings.max_wager} Wu, and can only be called when you both hold {settings.max_wager}.",
            "You can never pick the same Challenge or Background two showdowns in a row.",
            "You can Return before the first Continue. After it, there is no retreat.",
        ],
        "In the Showdown:": [
            "Gong Yi Tanpai! You and your opponent field your Wu at the same moment, neither seeing "
            "the other's.",
            "Each stat is ONE battle. Every Wu goes down together and they are summed up.",
            "A Tournament is three battles of three different Wus: Force, then Agility, then Intellect.",
            "Any Wu you field may carry a Boost, but a Boost Wu works once.",
            "A Wu with a negative stat curses your opponent: it lands on their side, not yours.",
            "The Background lifts a Wu of its element and drags down its opposite. To a curse it does the reverse.",
            "During the evaluation: the contested stat counts x2. The other two still count so don't put it all in one place.",
        ],
        "Who takes it:": [
            "The Showdown goes to whoever won the most battles.",
            "Tied on battles? Add up every stat you won across them. The higher total takes it.",
            "Tied on that too? It goes to whoever called the Challenge.",
            "The loser forfeits every Wu they have wagered.",
            f"The prize Wu needs a hard blow: beat {settings.prize_threshold} on the contested stat "
            "in any one battle. Win small and it is lost.",
        ],
        "When the pile runs dry:": [
            "The run ends. There is no Showdown left to call.",
            "Whatever is still in your hand is cashed for its points, and the higher score wins.",
            "But Wus in your Deck are wasted.",
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


class _Rule:
    """One rule, wrapped so that no line of it is left holding a single word.

    A greedy wrap ends a rule on whatever is left over, which is regularly one short word sitting
    alone under a full line. It reads as a mistake. Where the line above can spare a word, one is
    pulled down to keep it company; the text itself is never touched.
    """

    def __init__(self, rule: str) -> None:
        self.rule = rule

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        for line in _balance(self.rule.split(), options.max_width):
            yield Text(line)


def _wrap(words: list[str], width: int) -> list[list[str]]:
    """Greedy-wrap: fill each line to ``width`` before starting the next."""
    lines: list[list[str]] = [[]]
    for word in words:
        line = lines[-1]
        if line and len(" ".join(line)) + 1 + len(word) > width:
            lines.append([word])
        else:
            line.append(word)
    return lines


def _balance(words: list[str], width: int) -> list[str]:
    """Wrap ``words`` into even lines rather than a full one and a stub.

    Greedy wrapping packs each line to the margin and leaves whatever is over on the last, which is
    where the ragged tails come from — a rule that fills the width and then drops two words underneath
    reads as though it broke. The line *count* is what greedy gets right, so this keeps that and then
    wraps again at the narrowest width that still fits in it. Same number of lines, evenly filled.
    """
    if not words:
        return []
    count = len(_wrap(words, width))
    narrowest = max(len(word) for word in words)
    for trial in range(narrowest, width + 1):
        lines = _wrap(words, trial)
        if len(lines) <= count:
            return [" ".join(line) for line in lines]
    return [" ".join(line) for line in _wrap(words, width)]


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
        grid.add_row("•", _Rule(rule))
    return grid
