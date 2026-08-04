"""Wu prose shared across screens — a card's own headline, a power's, and the Game Log's titles.

Kept apart from :mod:`format` (whose helpers — ``card_name_text``, ``COLORS``, ``stats_line`` — are
the base everything here builds on) because these are prose built ON TOP of that base, not part of it.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from functools import cache

from rich.text import Text

from ...logic.schema.catalog import load_catalog
from ...logic.schema.models import Card
from .format import card_name_text, power_name_text, stats_line


def card_headline(card: Card) -> Text:
    """One Wu, named: its name in its element's colour, then its stats in brackets. Nothing else.

    **The established shape for a card anywhere it is named** — a button, a dialog, a reveal. The type
    glyph is deliberately absent: it belongs to the temple's hand panels, where it says what can build
    Mala Mala Jong and gives the eye something to sort by. On a button it is decoration, and decoration
    on a button is noise.

    Built on a FRESH Text: `card_name_text` carries the element colour as its base style, so appending
    to it directly tints the stats too (see `card_label`, which learned this the same way).
    """
    line = Text()
    line.append_text(card_name_text(card, bold=True))
    line.append(f" ({stats_line(card.stats)})")
    return line


# What a Game Log entry is filed under. Three kinds, and the difference is WHOSE it is: a move of
# yours, a move of theirs, and the showdown — which is neither. A showdown is not somebody's move; it
# is what the two moves were leading to, so it is titled flat and owns no side.
YOUR_LOG = "Your move"
OPPONENT_LOG = "Opponent's move"
SHOWDOWN_LOG = "Showdown"


def your_move(action: str) -> str:
    """``Your move: Deposit`` — a line of the log that is yours, and says which action it was."""
    return f"{YOUR_LOG}: {action}"


def opponent_move(actions: Sequence[str]) -> str:
    """``Opponent's move: Deposit`` — the same shape, the other side of the table.

    One rule for both duelists: whose move, then which action. A move of theirs titled differently
    from the same move of yours makes a reader compare two shapes instead of two sides.

    A turn buys one action, so there is normally one to name. Where a rule hands out more (the console
    can), the actions are not listed — a title is a label, and a label that grows is a sentence.
    """
    return f"{OPPONENT_LOG}: {actions[0]}" if len(actions) == 1 else OPPONENT_LOG


def wu_in_prose(prose: str) -> Text:
    """The game's own prose, with every Wu it names drawn as a Wu.

    The Game Log's lines are sentences the game wrote — "Katnappé played Bras Finger", "Drew Eagle
    Scope" — and a card written in plain grey words is a card in the one place the game does not look
    like itself. Every other screen prints a Wu as an element-coloured name and its stats; so does this.

    **A Wu is introduced once.** The first time it is named it comes with its stats, because that is
    the moment a reader needs them; every mention after that is the name alone. Repeating the triple
    turns a sentence into a datasheet, and the second copy tells nobody anything new.

    Longest name first, or a Wu whose name contains another's gets cut in half by it.
    """
    names, cards = _wu_names()
    text = Text()
    introduced: set[str] = set()
    at = 0
    for match in names.finditer(prose):
        name = match.group()
        text.append(prose[at : match.start()])
        card = cards[name]
        text.append_text(card_name_text(card) if name in introduced else card_headline(card))
        introduced.add(name)
        at = match.end()
    text.append(prose[at:])
    return text


@cache
def _wu_names() -> tuple[re.Pattern[str], dict[str, Card]]:
    cards = {card.name: card for card in load_catalog().cards if card.name}
    pattern = re.compile("|".join(re.escape(name) for name in sorted(cards, key=len, reverse=True)))
    return pattern, cards


def power_headline(card: Card) -> Text:
    """A Wu named by its *power*: ``Teleskopia (Eagle Scope)``.

    The shape for a screen that asks which power to spend: the power is the thing being chosen, and
    the Wu is only which card it costs you. No stats — a power does not care what the card fights for,
    and printing them here asks a reader to weigh numbers that have nothing to do with the choice.
    `card_headline` is the other way round, and belongs everywhere a *card* is what is being picked.

    Fresh ``Text``, as always: both name helpers carry a colour as their base style.
    """
    line = Text()
    line.append_text(power_name_text(card.power))
    line.append(" (")
    line.append_text(card_name_text(card))
    line.append(")")
    return line
