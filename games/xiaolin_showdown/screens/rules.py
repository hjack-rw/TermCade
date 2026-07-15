"""Rules screen — a book with a contents list, not a scroll.

**The sections are the navigation.** A rulebook read top to bottom is a rulebook nobody reads: a player
arrives with a question ("what does initiative *do*?") and wants the two paragraphs that answer it, not
a wall to scan. So the left rail lists the sections and the right pane shows the one you picked. How to
Play sits at the top of that rail, because it is where a player who has *no* question yet should land.

**The search is hidden until it is wanted, and `R` is what wants it.** A search box sitting open on a
book you have not read yet is clutter, and a rulebook is read far more often than it is searched. `R`
summons it and puts the cursor in it; `Tab` stays what it is everywhere else in the engine — the focus
key — and moves between the rail and the box once the box exists.

Searching **cuts across every section**: it is the answer to "a rule just bit me and I do not know
where it lives". The rail steps aside while results are up, because a result already says which section
it came from, and Escape puts the book back the way it was.

The numbers are read from the live settings, never typed twice. A rulebook that says 7 while the game
checks 8 is worse than no rulebook, and `test_rules_screen.py` fails the moment the two part.
"""

from __future__ import annotations

from rich.console import Console, ConsoleOptions, RenderResult
from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Footer, Header, Input, ListItem, ListView, Static

from termcade.ui.screens.base import EngineScreen
from termcade.ui.typography import spaced_dashes
from ..logic.mechanics.prize import PrizeRoute
from ..logic.settings import XiaolinSettings

PRIMER = "How to Play"  # the first entry in the rail, and where a player with no question yet lands

# The loop, and nothing else. A player who reads only this can sit down and play a whole run: what a
# turn buys, what a showdown costs, how a Wu changes hands, how the run ends. Every rule in the
# reference below is an answer to a question this raises — and none of them has to be read first.
HOW_TO_PLAY: list[str] = [
    "Collect Shen Gong Wu, bank them for points, and reach the target before your opponent does.",
    "A turn at the vault allows for ONE action: bank a Wu for its points, spend a Wu for its power, or "
    "draw one into your hand. Banking a Wu forfeits its power; keeping the power forfeits the points. ",
    "Then call `Gong Yi Tanpai!` —  a Showdown for the next Wu on the pile.",
    "Whoever is faster (Initiative) says what is contested.",
    "You both field your Wu at the same moment, neither seeing the other's. "
    "Your character, the Wu you played and the arena you stand in are all added up.",
    "The loser forfeits every Wu they wagered. The winner takes the prize Wu — but only by winning "
    "decisively. Win small and nobody takes it: it will be temporarily lost.",
    "When the pile runs dry the run ends. Whatever is still in your hand is cashed for points. "
    "Whatever you shelved in your Deck is wasted.",
]


def _route(route: PrizeRoute) -> str:
    """A prize route as the rulebook prints it: the game's own words, capitalised to open a line."""
    return route.value[0].upper() + route.value[1:]


def rules_for(settings: XiaolinSettings) -> dict[str, list[str]]:
    """The rulebook, with the game's own numbers in it."""
    return {
        "At the Vault": [
            f"A turn buys you {settings.actions_per_turn} action: deposit a Wu for its "
            "points, use its power, or draw one from your Deck.",
            "Depositing a Wu forfeits its power. You are vaulting it, not spending it.",
            "Your hand never refills itself. Drawing it back up costs you the turn's action too.",
            f"Your hand holds {settings.max_hand_size} Wu. Over that, you shelve one back to your Deck.",
            f"Left with nothing you can field, you are dealt back in — up to {settings.empty_draw_limit} "
            "Wu, from your own Deck first and the pile only after it. It costs you the turn's action, "
            "and it never hands you more than you could have staked. "
            "You are being put back in the fight, not paid for having lost it.",
            "Your opponent takes the same turn when you do.",
            f"Bank {settings.point_limit} points and the run is yours!",
        ],
        "Initiative": [
            "Initiative is how fast you are, and the faster duelist names the Challenge.",
            "Matching Initiative bonuses do NOT stack. Different ones do — a +1 beside a +2 is +3.",
            "A Wu with a NEGATIVE bonus slows your opponent, not you. "
            "Holding one makes you the faster of the two, exactly as a positive one does.",
            f"Lead them by {settings.early_bird_gap} and the Early Bird advantage is yours: "
            "take the next Wu straight off the pile, with no Showdown at all. "
            "It is treated as a power, and it costs the turn's action like any other.",
            "The Early Bird's price is one of your FASTEST Wu, and it is discarded for no points.",
        ],
        "Calling a Showdown": [
            "The higher Initiative names the Challenge. Tie, and a coin toss decides it.",
            "The Challenge can be one stat, or a Tournament across all three.",
            f"Name a stat and your opponent names the stakes, up to {settings.max_wager} Wu each.",
            f"A Tournament costs {settings.max_wager} Wu, and can only be called when you both hold {settings.max_wager}.",
            "You can never pick the same Challenge or Background two showdowns in a row.",
            "You can Return before the first Continue. After it, there is no retreat.",
        ],
        "In the Showdown": [
            "`Gong Yi Tanpai!` you and your opponent play your Wu at the same moment, neither seeing the other's.",
            "Each stat is ONE battle. Every Wu goes down together and they are summed up.",
            "A Tournament is three battles of three different Wus: Force, then Agility, then Intellect.",
            "Any Wu you field may carry a Boost, but each Boost Wu is spent once a Showdown. A field "
            "of three needs three different Boosts — one dragon cannot lift them all.",
            "A Wu with a negative stat curses your opponent: it lands on their side, not yours.",
            "The Background lifts a Wu of its element and drags down its opposite."
            "To a curse it does the reverse.",
            "Metal is nobody's friend: it is dragged down on every coloured arena, and every coloured "
            "Wu is dragged down on metal.",
            "During the evaluation: the contested stat counts x2. The other two still count, so don't "
            "put it all in one place.",
        ],
        "Who Takes It": [
            "A battle goes to whoever scored higher. Level? Initiative takes it. Every battle has a "
            "winner.",
            "The Showdown goes to whoever won the most battles. A Tournament therefore ends 2:1 or 3:0.",
            "Tied on battles? Add up every stat you won across them. The higher total takes it.",
            "Tied on that too? It goes to whoever called the Challenge.",
            "The loser forfeits every Wu they have wagered.",
        ],
        "Claiming the Prize": [
            "Winning the Showdown is not enough. The prize Wu answers only to a decisive victory, and "
            "there are four ways to take it, evaluated in that order:",
            # The route NAMES are quoted from `PrizeRoute` itself, never retyped. The board announces
            # the winning route in the enum's own words — "[Claimed: a decisive blow]" — so a book that
            # called it something else would teach a player a name the game never says. Renaming a route
            # in the code used to leave the book quietly lying; now it cannot.
            f"{_route(PrizeRoute.DECISIVE_BLOW)} — beat {settings.prize_threshold} on the contested "
            "stat in any one battle.",
            f"{_route(PrizeRoute.BROAD_WIN)} — beat {settings.prize_threshold - 1} on any two stats.",
            f"{_route(PrizeRoute.TOTAL_COMMAND)} — beat {settings.prize_threshold - 2} on all three.",
            f"{_route(PrizeRoute.IN_TUNE)} — end the Showdown with more of the arena's element on your "
            "side than against it. Nullifying the elemental bonus voids this way to win it.",
            "Meet none of them and the Wu is LOST: nobody takes it. It is not destroyed, though — "
            "a way exists that calls the oldest lost Wu back into your hand.",
        ],
        "When the Pile Runs Dry": [
            "The run ends. There is no Showdown left to call.",
            "Whatever is still in your hand is cashed for points, and the higher score wins.",
            "But Wus in your Deck are missed points.",
        ],
    }


def matching(rules: dict[str, list[str]], query: str) -> dict[str, list[str]]:
    """The rules holding ``query``, section by section. An empty query is the whole book.

    A section whose rules all fall away goes with them — a heading over nothing reads as a bug. But a
    section *heading* that matches keeps its whole section: someone searching "showdown" wants the
    showdown rules, not only the ones that happen to repeat the word.
    """
    wanted = query.strip().lower()
    if not wanted:
        return rules

    found: dict[str, list[str]] = {}
    for heading, section in rules.items():
        if wanted in heading.lower():
            found[heading] = section
            continue
        hits = [rule for rule in section if wanted in rule.lower()]
        if hits:
            found[heading] = hits
    return found


class RulesScreen(EngineScreen):
    """The book: a rail of sections on the left, the one you picked on the right."""

    # `Tab` is the engine's focus key everywhere and stays that way here — it moves between the rail
    # and the search box once the box exists. `R` is what *summons* the box: a search field sitting open
    # on a book you have not read yet is clutter, and a rulebook is read far more often than searched.
    BINDINGS = [
        Binding("r", "search", "Search", show=True),
        Binding("escape", "back", "Back", show=True),
    ]

    def compose(self) -> ComposeResult:
        settings = XiaolinSettings.from_settings(self.ctx.settings.current)
        self._rules = rules_for(settings)
        self._searching = False
        self._visible: dict[str, list[str]] = {PRIMER: HOW_TO_PLAY}
        self._by_slug = {_slug(name): name for name in self._entries()}

        yield Header()
        yield Input(placeholder="Search every section...", id="rule-search")
        with Horizontal(id="rule-book"):
            yield ListView(
                *(ListItem(Static(name), id=_slug(name)) for name in self._entries()),
                id="rule-nav",
            )
            with VerticalScroll(id="rule-body"):
                yield Static(_page(PRIMER, HOW_TO_PLAY), id="rule-page", classes="rules")
        yield Footer()

    def on_mount(self) -> None:
        """The book opens out of focus mode, like every other screen in the engine.

        It used to open with the rail focused, on the argument that the rail *is* this screen. That was
        wrong, and it broke the one thing the focus key is for: `Tab` is offered in the footer as the way
        **into** keyboard mode, and on a screen that starts in it, pressing the advertised key throws you
        out of a mode you never asked to enter. One screen behaving backwards is worse than the second of
        friction it saves.

        The rail keeps its highlight regardless — the highlight says which section is on the page, and
        that is true whether or not the rail holds the keyboard.
        """
        self.query_one("#rule-search", Input).display = False  # hidden until `R` asks for it
        self.query_one("#rule-nav", ListView).index = 0

    def _entries(self) -> list[str]:
        return [PRIMER, *self._rules]

    # --- the rail ---------------------------------------------------------------------------
    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        """Pick a section and it is *shown* — no click, no Enter. Moving the cursor is the choice.

        Keyed by the item's id rather than the label rendered inside it: reading a widget's text back
        out to decide what it meant is a round trip through the display, and the display is the last
        place a decision should live.
        """
        if self._searching or event.item is None or event.item.id is None:
            return
        self._show(self._by_slug[event.item.id])

    @property
    def showing(self) -> dict[str, list[str]]:
        """The rules on the page right now, under the headings they came from.

        The page itself is a Rich table, and reading text back out of a rendered widget is a round trip
        through the display — brittle, and it tests the renderer rather than the book. This is what the
        screen *decided to show*, one step before Rich draws it, and it is what the tests ask about.
        """
        return self._visible

    def _show(self, entry: str) -> None:
        rules = HOW_TO_PLAY if entry == PRIMER else self._rules[entry]
        self._visible = {entry: rules}
        self.query_one("#rule-page", Static).update(_page(entry, rules))

    # --- the search -------------------------------------------------------------------------
    def action_search(self) -> None:
        """`R` reveals the box and puts the cursor in it; `Tab` can then move focus back to the rail."""
        box = self.query_one("#rule-search", Input)
        box.display = True
        self._searching = True
        self.query_one("#rule-nav", ListView).display = False  # a result says which section it is from
        box.focus()

    def action_back(self) -> None:
        """Escape closes the search first, and only leaves the screen once there is none to close."""
        if not self._searching:
            self.app.pop_screen()
            return
        box = self.query_one("#rule-search", Input)
        box.value = ""
        box.display = False
        self._searching = False
        nav = self.query_one("#rule-nav", ListView)
        nav.display = True
        nav.focus()
        self._show(self._entries()[nav.index or 0])

    def on_input_changed(self, event: Input.Changed) -> None:
        """Every section at once — the point of searching is not knowing where the rule lives."""
        page = self.query_one("#rule-page", Static)
        found = matching(self._rules, event.value)
        self._visible = found
        page.update(
            _all_of_it(found)
            if found
            else Text(f"No rule mentions '{event.value.strip()}'.", style="dim")
        )


def _slug(name: str) -> str:
    return "nav-" + "".join(ch if ch.isalnum() else "-" for ch in name.lower()).strip("-")


def _page(heading: str, rules: list[str]) -> Table:
    """One section: its name, then its rules."""
    grid = Table.grid(padding=(0, 0))
    grid.add_column(justify="left", ratio=1)
    grid.add_row(Text(heading.upper(), style="bold"))
    grid.add_row("")
    grid.add_row(_bullets(rules))
    return grid


def _all_of_it(rules: dict[str, list[str]]) -> Table:
    """Search results: every section that still has something in it, its heading kept.

    The heading is what makes a hit useful — "you found this under *Initiative*" is half the answer.
    """
    grid = Table.grid(padding=(0, 0))
    grid.add_column(justify="left", ratio=1)
    for heading, section in rules.items():
        grid.add_row(Text(heading.upper(), style="bold"))
        grid.add_row(_bullets(section))
        grid.add_row("")
    return grid


class _Rule:
    """One rule, wrapped so that no line of it is left holding a single word.

    A greedy wrap ends a rule on whatever is left over, which is regularly one short word sitting
    alone under a full line. It reads as a mistake. Where the line above can spare a word, one is
    pulled down to keep it company; the text itself is never touched.
    """

    def __init__(self, rule: str) -> None:
        self.rule = rule

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        # The lines come back already spaced (see `_line`): the wrap both measures and emits the printed
        # text, because the em dash needs a column the joined text does not have.
        for line in _balance(self.rule.split(), options.max_width):
            yield Text(line)


def _line(words: list[str]) -> str:
    """The line as it will be PRINTED — em dashes already given their gap.

    Wrapping has to measure the printed line, not the joined one: `spaced_dashes` puts a column back
    after every dash, and a wrap that measured the text before that ran hands Rich a line one column
    too long. Rich then breaks it again, on its own terms, and the whole balancing act below is undone
    by a word dropped onto a line of its own.
    """
    return spaced_dashes(" ".join(words))


def _wrap(words: list[str], width: int) -> list[list[str]]:
    """Greedy-wrap: fill each line to ``width`` before starting the next."""
    lines: list[list[str]] = [[]]
    for word in words:
        line = lines[-1]
        if line and len(_line([*line, word])) > width:
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
            return [_line(line) for line in lines]
    return [_line(line) for line in _wrap(words, width)]


def _bullets(rules: list[str]) -> Table:
    """The rules of one section, as a hanging indent.

    A bullet and its text are two columns, not one string: a rule long enough to wrap must come back
    under its own text, not under the bullet. Padding on a ``Static`` indents the whole block and
    cannot do that.
    """
    # A blank line between rules. They are paragraphs, not a list of nouns — run together they read as
    # a wall, and the rail freed the width to afford the air.
    grid = Table.grid(padding=(1, 1))
    grid.add_column(justify="left", width=1)  # the bullet
    grid.add_column(justify="left", ratio=1)  # the rule, free to wrap under itself
    for rule in rules:
        grid.add_row("•", _Rule(rule))
    return grid
