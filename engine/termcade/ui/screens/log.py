"""The Game Log — everything the run has said, in the order it said it, cut into turns.

A notification is shown for a few seconds and then it is gone, and the game does not wait while it is
up. The opponent takes a whole turn in one toast. A power says what it did once. The mystery Wu tells
you what it was worth exactly once, and never again. Look away and it is simply lost, and there is no
"what did that say?" in a game with nowhere to look it up.

This is the nowhere-to-look-it-up, fixed. It reads `GameContext.journal` — which the engine fills from
`EngineApp.notify`, so a game gets this screen the moment it raises a toast — and shows the lot under
the turn each line belongs to, opened at the bottom, because the thing a player came here for is almost
always the last one.

The engine draws the *shape*; the GAME draws its own nouns (`Game.log_line`). Only the cartridge knows
that "Bras Finger" is a Wu.
"""

from __future__ import annotations

from itertools import groupby

from rich.text import Text
from textual.app import ComposeResult
from textual.color import Color
from textual.containers import VerticalScroll
from textual.widgets import Footer, Header, Static

from termcade.core.journal import Entry
from termcade.ui.widgets import BoxedPanel

from .base import EngineScreen

EMPTY = "Nothing has happened yet."

# How far the theme's accent is lifted for the turn headings. The accent itself is a *border* colour —
# dark enough to sit under text — and text drawn in it on a dark ground is nearly unreadable. Bold
# alone would not do it either: a terminal may render bold as nothing at all.
_HEADING_LIFT = 0.6

# The rule between turns. Dashed, not solid: a solid rule reads as a *border* — the edge of a panel —
# and the log already has one of those around it. Every second cell is blank, so the dashes read as a
# broken line rather than a continuous one.
_RULE = "╌ "
_RULE_SHARE = 0.8  # of the screen: short enough to be a rule, long enough to divide the page
_RULE_MIN = 20  # a very narrow terminal still gets a rule, not a hyphen


class GameLogScreen(EngineScreen):
    BINDINGS = [("escape", "app.pop_screen", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        with BoxedPanel(title="GAME LOG"):
            with VerticalScroll(id="log-body"):
                yield Static(self._page(), id="log-entries")
        yield Footer()

    def on_mount(self) -> None:
        # Opened at the END. The log answers "what just happened?", and that answer is at the bottom —
        # a screen that opens at the top of a hundred lines makes a player scroll to reach the one
        # thing they came for.
        self.query_one("#log-body", VerticalScroll).scroll_end(animate=False)

    @property
    def showing(self) -> str:
        """What is on the page, as plain text — what the tests ask about.

        Not read back off the widget: `Static.renderable` does not exist in this Textual, and code that
        reached for it broke silently when Textual moved on. This is what the screen *decided* to show,
        one step before Rich draws it.
        """
        return self._page().plain

    def _page(self) -> Text:
        entries = self.ctx.journal.entries
        if not entries:
            return Text(EMPTY, style="dim")

        page = Text()
        heading = self._heading_style()
        for index, (turn, lines) in enumerate(groupby(entries, key=lambda e: e.turn)):
            if index:
                # A dashed rule between turns, and only BETWEEN them: a line above the first would be
                # dividing it from nothing. The turn heading is what a reader scrolls by; the rule is
                # what tells them, at a glance, where one turn stopped being the other.
                page.append(f"{self._rule()}\n", style="dim")
            page.append(f"Turn {turn}\n", style=heading)
            for entry in lines:
                page.append_text(self._entry(entry))
                # A blank line BETWEEN entries, or an untitled one (a draw, say) reads as another line
                # of the titled block above it — "Drew Eagle Scope" arriving under "Opponent's move"
                # says the opponent drew it, which is a lie the layout tells on its own.
                page.append("\n")
        return page

    def _rule(self) -> str:
        """A rule that spans most of the page it divides, whatever width that is.

        Measured off the SCREEN, not off the scroll container: the page is built during `compose`, when
        the container has no size yet — asking it then answers zero, and the rule came out as the bare
        minimum, a stub in the middle of a wide terminal.
        """
        width = max(_RULE_MIN, int(self.app.size.width * _RULE_SHARE))
        return (_RULE * (width // len(_RULE))).rstrip()

    def _heading_style(self) -> str:
        try:
            accent = Color.parse(self.app.current_theme.accent).lighten(_HEADING_LIFT)
        except Exception:  # noqa: BLE001 — a themeless test app must still be able to read its log
            return "bold"
        return f"bold {accent.hex}"

    def _entry(self, entry: Entry) -> Text:
        """One entry: its title dim above what it said, the whole thing indented under its turn.

        Dim on the title, plain on the message — the same rule the console's help follows. The title is
        what the message is *about* ("Opponent's move"); the message is what you came to read, and a
        heading drawn as loudly as the text it heads competes with it.
        """
        text = Text()
        if entry.title:
            text.append(f"  {entry.title}\n", style="dim")
        # Every line of the message indented, not just the first: the opponent's whole move arrives as
        # one multi-line toast, and a block that hangs together under its title reads as one event —
        # which is what it is.
        for line in self._drawn(entry.message).split("\n"):
            text.append("    ")
            text.append_text(line)
            text.append("\n")
        return text

    def _drawn(self, message: str | Text) -> Text:
        """The game's own hand on its own nouns — a Wu named here looks like a Wu named anywhere.

        The WHOLE message at once, not line by line: a game that introduces a Wu with its stats and
        then refers to it again by name needs to know it has already been introduced, and it cannot
        know that if it is handed one line at a time.

        Text that arrives already styled is left alone. The game built it that way because it knew
        something the log cannot look up.
        """
        if isinstance(message, Text):
            return message
        draw = self.game.log_line
        return Text(message) if draw is None else draw(message)
