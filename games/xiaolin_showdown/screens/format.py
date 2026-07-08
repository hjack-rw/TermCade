"""Presentation helpers for XS cards — element colors, type icons, stat strings.

Colors are emitted as Textual/Rich markup (``[blue]…[/]``); stats show ``?`` for the null-stat
cards.
"""

from __future__ import annotations

from collections.abc import Mapping

from rich.text import Text

from ..logic.models import Card, Character, Power

# element -> colour, as explicit hex so the theme's ANSI palette can't remap it (the OG mapping:
# water blue, fire red, wind/air yellow, earth green, metal a neutral grey).
COLORS = {
    "water": "#4a9eff",
    "fire": "#ff5555",
    "wind": "#ffd43b",
    "earth": "#51cf66",
    "metal": "#ced4da",
}

# Card / affiliation icons — plain Unicode symbols, deliberately picked for *text* presentation
# (each has Emoji_Presentation=No), so any renderer that owns a glyph for them draws them monochrome,
# never as colour emoji. They do need a comprehensive symbol font, though: on Windows that is Segoe
# UI Symbol (reached automatically via font fallback), and the browser build embeds a covering font
# in serve.py so xterm.js always has the glyphs. Written as \u/\U escapes so the source stays ASCII.
ICONS = {
    "wudai": "\U0001f5e1",  # dagger — the elemental warrior Wu
    "head": "♔",  # chess king
    "torso": "\U0001f580",  # telephone-on-modem (reads as an armoured torso)
    "amulet": "\U0001f396",  # military medal
    "arms": "\U0001f591",  # raised hand
    "boots": "⛸",  # ice skate
    "item": "\U0001f6e0",  # hammer & wrench
    "xiaolin": "☯",  # yin-yang — the light-side monks
    "heylin": "☸",  # dharma wheel — the dark side
    "construct": "⚙",  # gear
    "empty": "",
}


def _stat(value: int | None) -> str:
    return "?" if value is None else str(value)


def stats_line(stats: Mapping[str, int | None]) -> str:
    return "/".join(_stat(stats[key]) for key in ("force", "agility", "intellect"))


def char_stats(character: Character) -> str:
    return stats_line(character.stats)


def display_name(name: str) -> str:
    """A stored name shown for humans: underscores become spaces (``Salvador_Cumo`` -> ``Salvador Cumo``)."""
    return name.replace("_", " ")


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


def _rows(cards: list[Card], name_width: int, col_width: dict[str, int]) -> list[Text]:
    rows = []
    for index, card in enumerate(cards, 1):
        colour = COLORS.get(card.element, "white")
        icon = ICONS.get(card.type, "")
        name = card.name.rjust(name_width)
        stats = "/".join(_stat(card.stats[key]).rjust(col_width[key]) for key in _STAT_KEYS)
        # Built as styled Text (not markup) so the element colour renders reliably in a Static:
        # dim list number, bright element-coloured Wu name, plain stats + type glyph.
        row = Text()
        row.append(f"{index}. ", style="dim")
        row.append(name, style=f"bold {colour}")
        row.append(f"  {stats}  {icon}")
        rows.append(row)
    return rows


def hands_lines(hand_a: list[Card], hand_b: list[Card]) -> tuple[list[Text], list[Text]]:
    """Format both hands with *shared* name and per-column widths, so the two panels come out
    the same size and every name / ``/`` separator / icon lines up down and across the columns."""
    both = hand_a + hand_b
    name_width = max((len(card.name) for card in both), default=0)
    col_width = {
        key: max((len(_stat(card.stats[key])) for card in both), default=1) for key in _STAT_KEYS
    }
    return _rows(hand_a, name_width, col_width), _rows(hand_b, name_width, col_width)
