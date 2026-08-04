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

    Built on a FRESH Text: `card_name_text` carries the element colour as its base style, so appending
    to it directly tints the stats too (see `card_label`, which hits the same trap).
    """
    line = Text()
    line.append_text(card_name_text(card, bold=True))
    line.append(f" ({stats_line(card.stats)})")
    return line


# Game Log entry titles.
YOUR_LOG = "Your move"
OPPONENT_LOG = "Opponent's move"
SHOWDOWN_LOG = "Showdown"


def your_move(action: str) -> str:
    """``Your move: Deposit`` — a line of the log that is yours, and says which action it was."""
    return f"{YOUR_LOG}: {action}"


def opponent_move(actions: Sequence[str]) -> str:
    """``Opponent's move: Deposit`` — the same shape as :func:`your_move`.

    With more than one action (only possible via the console) the title omits them and reads
    ``Opponent's move`` alone.
    """
    return f"{OPPONENT_LOG}: {actions[0]}" if len(actions) == 1 else OPPONENT_LOG


def wu_in_prose(prose: str) -> Text:
    """The game's own prose, with every Wu it names drawn element-coloured, as elsewhere.

    A Wu is introduced once: the first mention gets its stats (`card_headline`), later mentions just
    the name (`card_name_text`). Names are matched longest-first, or a Wu whose name contains another's
    would get cut in half by it.
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
    """A Wu named by its *power*: ``Teleskopia (Eagle Scope)`` — no stats, unlike `card_headline`.

    Fresh ``Text``: both name helpers carry a colour as their base style.
    """
    line = Text()
    line.append_text(power_name_text(card.power))
    line.append(" (")
    line.append_text(card_name_text(card))
    line.append(")")
    return line
