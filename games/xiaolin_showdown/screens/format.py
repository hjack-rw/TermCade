"""Presentation helpers for XS cards — element colors, type icons, stat strings.

Ported from the reference ``UTILS.colors`` / ``UTILS.icons`` / ``UTILS.number``. Colors are
emitted as Textual/Rich markup (``[blue]…[/]``); stats show ``?`` for the null-stat cards.
"""

from __future__ import annotations

from collections.abc import Mapping

from rich.text import Text

from ..logic.models import Card, Character, Power

# element -> Rich colour (reference used bright ANSI 94/91/93/92/37)
COLORS = {
    "water": "bright_blue",
    "fire": "bright_red",
    "wind": "bright_yellow",
    "earth": "bright_green",
    "metal": "white",
}

# card type -> glyph
ICONS = {
    "wudai": "🗡",
    "head": "♔",
    "torso": "🖀",
    "amulet": "🎖",
    "arms": "🖑",
    "boots": "⛸",
    "item": "🛠",
    "xiaolin": "☯",
    "heylin": "☸",
    "construct": "⚙",
    "empty": "",
}


def _stat(value: int | None) -> str:
    return "?" if value is None else str(value)


def stats_line(stats: Mapping[str, int | None]) -> str:
    return "/".join(_stat(stats[key]) for key in ("force", "agility", "intellect"))


def char_stats(character: Character) -> str:
    return stats_line(character.stats)


def affiliation_icon(character: Character) -> str:
    return ICONS.get(character.affiliation, "")


def card_markup(card: Card) -> str:
    """``[colour]NAME[/]  f/a/i  icon`` — a single hand row (unaligned)."""
    colour = COLORS.get(card.element, "white")
    icon = ICONS.get(card.type, "")
    return f"[{colour}]{card.name}[/]  {stats_line(card.stats)}  {icon}"


def power_label(item: Card | Character) -> str:
    """The power's name, or an em-dash for the blank/no-op power (power id 0)."""
    return item.power.name if item.power.id else "—"


def card_name_text(card: Card) -> Text:
    """The card's name as element-coloured Rich text."""
    return Text(card.name, style=COLORS.get(card.element, "white"))


def trigger_label(power: Power) -> str:
    """When a power fires, e.g. ``On Play`` — or ``? ? ?`` for a hidden deposit power."""
    if power.trigger == "deposit" and power.effect == 0:
        return "? ? ?"
    return f"On {power.trigger.capitalize()}"


_STAT_KEYS = ("force", "agility", "intellect")


def _rows(cards: list[Card], name_width: int, col_width: dict[str, int]) -> list[str]:
    rows = []
    for index, card in enumerate(cards, 1):
        colour = COLORS.get(card.element, "white")
        icon = ICONS.get(card.type, "")
        name = card.name.rjust(name_width)
        stats = "/".join(_stat(card.stats[key]).rjust(col_width[key]) for key in _STAT_KEYS)
        rows.append(f"{index}. [{colour}]{name}[/]  {stats}  {icon}")
    return rows


def hands_lines(hand_a: list[Card], hand_b: list[Card]) -> tuple[list[str], list[str]]:
    """Format both hands with *shared* name and per-column widths, so the two panels come out
    the same size and every name / ``/`` separator / icon lines up down and across the columns."""
    both = hand_a + hand_b
    name_width = max((len(card.name) for card in both), default=0)
    col_width = {
        key: max((len(_stat(card.stats[key])) for card in both), default=1) for key in _STAT_KEYS
    }
    return _rows(hand_a, name_width, col_width), _rows(hand_b, name_width, col_width)
