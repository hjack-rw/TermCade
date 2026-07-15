"""Presentation helpers for XS cards — element colors, type icons, stat strings.

Colors are emitted as Textual/Rich markup (``[blue]…[/]``); stats show ``?`` for the null-stat
cards.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from rich.text import Text

from ..logic.mechanics.powers import (
    NAMED_STAT_VALUE,
    SCOPE_DEPTH,
    Mechanic,
    is_gamble,
    mechanic_of,
    trigger_of,
)
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
    "wudai": "\U0001f5e1",  # weapon — the elemental warrior Wu
    "head": "♔",  # crown
    "torso": "\U0001f580",  # armor
    "amulet": "\U0001f396",  # neckless
    "arms": "\U0001f591",  # hand
    "boots": "⛸︎",  # feet — VS15: ambiguous width, so ask for the text face
    "item": "\U0001f6e0",  # tools
    "xiaolin": "☯",  # yin-yang — the light-side monks
    "heylin": "☸",  # dharma wheel — the dark-side villains
    "construct": "⚙",  # robot gear
    "empty": "",
}


STAT_ORDER = ("force", "agility", "intellect")


def stat_str(value: int | None) -> str:
    return "?" if value is None else str(value)


def stats_line(stats: Mapping[str, int | None]) -> str:
    return "/".join(stat_str(stats[key]) for key in STAT_ORDER)


# The stat a battle is decided on, wherever it is drawn: bright white and bold, against the dim of the
# two that only count single. Bold on its own is advisory — a terminal may render it as nothing.
CONTESTED_STYLE = "bold bright_white"


def stats_text(values: Sequence[str], challenge: str | None = None) -> Text:
    """A stat triple with every stat but the contested one dimmed, so the eye finds what decides.

    ``values`` are already rendered, in :data:`STAT_ORDER`. No ``challenge`` (before it is named)
    leaves all three plain.
    """
    text = Text()
    for index, (stat, value) in enumerate(zip(STAT_ORDER, values)):
        if index:
            text.append("/", style="dim")
        # Bright on the contested stat, dim on the rest. One rule, everywhere a stat is printed — the
        # end totals AND the Wu on the table — so the eye learns a single thing to look for. An explicit
        # colour, because bold alone is a hint a terminal may ignore and is invisible on a dim ground.
        text.append(value, style="dim" if challenge and stat != challenge else CONTESTED_STYLE)
    return text


def card_stats_text(stats: Mapping[str, int | None], challenge: str | None = None) -> Text:
    return stats_text([stat_str(stats[key]) for key in STAT_ORDER], challenge)


# A negated line — a Sphere, a Scorpion, a Mirror. Not zero: *absent*. `?` is a stat not yet
# resolved and `0` is a stat that resolved to nothing, and this is neither.
ABSENT = "-"


def absent_stats_text(challenge: str | None = None) -> Text:
    """A line that has been negated for this battle: no stats, and no element to resonate with."""
    return stats_text([ABSENT] * len(STAT_ORDER), challenge)


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


def card_name_text(card: Card, *, bold: bool = False) -> Text:
    """The card's name as element-coloured Rich text.

    In a duel the queue holds stand-ins whose ``element`` is what the card *resolved* as — a Morpher
    wears its chosen element — so this shows the in-duel element, not the printed one. A curse mirror
    keeps the element it is, and earns no bonus for the side it lands on (that is the duel's job, not
    a colour's). A card with no element falls back to plain white.
    """
    colour = COLORS.get(card.element, "white")
    return Text(display_name(card.name), style=f"bold {colour}" if bold else colour)


def points_label(card: Card) -> str:
    """A card's deposit value — ``X`` when it has none to give.

    A dragon Wu (``boost``/0) can never be staked, lost or banked, so ``0`` reads as "worth nothing"
    when it means "not for sale".
    """
    if mechanic_of(card.power) is Mechanic.DRAGON:
        return "X"
    if is_gamble(card.power):  # nobody knows, and the card is not going to tell you
        return "?"
    return str(card.points)


def power_name_text(power: Power) -> Text:
    """A power's name, element-coloured when it names an element (``Dragon of Water``)."""
    element = power.name.rsplit(" ", 1)[-1].lower()
    if mechanic_of(power) is Mechanic.DRAGON and element in COLORS:
        return Text(power.name, style=COLORS[element])
    return Text(power.name)


def element_text(element: str) -> Text:
    """``Water`` in water's colour — the element named in its own colour, as Wu names are."""
    return Text(element.capitalize(), style=COLORS.get(element, "white"))


def card_label(card: Card, suffix: str = "", *, prefix: str = "") -> Text:
    """``prefix`` + the element-coloured Wu name + plain ``suffix`` — a button label.

    Built on a fresh ``Text`` on purpose: ``card_name_text`` carries the element colour as its *base*
    style, so appending to it directly would tint the suffix too.
    """
    label = Text(prefix)
    label.append_text(card_name_text(card))
    label.append(suffix)
    return label


def bonus_tooltip(bonuses: Sequence[int]) -> str:
    """``(+1, -1)`` — the buffs and debuffs behind an initiative, for a hover tooltip.

    ``bonuses`` are the ones ``scoring.initiative_sources`` credits: this duelist's own buffs and
    the opponent's debuffs, one per distinct value, so they always sum to the initiative shown.
    Nothing applies → ``(none)``, so a silent hover always means "no tooltip here", never "no Wu".
    """
    if not bonuses:
        return "(/)"
    return f"({', '.join(f'{bonus:+d}' for bonus in bonuses)})"


# What a Wu does, in one line, under its flavour. The trigger is already printed beside the power's
# name, so it is not repeated here. Not every mechanic gets one: a plain Wu's stats are the whole of
# it, and the joke Wu tells you nothing on purpose.
EFFECTS = {
    Mechanic.HAND_SIZE: "Hand limit: +1",
    Mechanic.CHRONOKINESIS: "Draw a Wu from the incoming Wu pile.",
    Mechanic.DRAGON: "Boosts only. Can't be staked, lost or banked.",
    Mechanic.BOOST: "Enhances the played Wu by 1 per stat it holds.",
    Mechanic.MORPH: "You choose its Element.",
    Mechanic.INTANGIBLE: "No Elemental bonus for either duelist all Showdown.",
    Mechanic.DIASKOPIA: "Read your opponent's personal Deck.",
    Mechanic.TELESKOPIA: f"Look at the next {SCOPE_DEPTH} Wu in the incoming Wu pile.",
    Mechanic.TELEPATHEIA: "Take or refuse the next Showdown's Initiative.",
    Mechanic.HYDROKINESIS: f"You name one stat. It takes +{NAMED_STAT_VALUE} in the battle.",
    Mechanic.MISFORTUNE: f"You name one stat. Your opponent takes −{NAMED_STAT_VALUE} in the battle.",
    Mechanic.ATTRACTION: "Pull any one Wu from your own Deck into your hand.",
    Mechanic.REPULSION: "Shove a Wu out of their hand. They bank it, and keep the points.",
    Mechanic.ANABIOSIS: "Bring the oldest lost Wu back — into your hand.",
    Mechanic.CONTAINMENT: "In battle: their own stats count nothing.",
    Mechanic.REVERSAL: "In battle: the curses laid on you count nothing.",
    Mechanic.SUBJUGATION: "In battle: every Wu they played counts nothing.",
}


def effect_line(power: Power) -> str | None:
    """The one-liner under a Wu's flavour, or ``None`` for the Wu that do not earn one."""
    return EFFECTS.get(mechanic_of(power))


_TRIGGERS = {
    "use": "On Use",
    "hand": "While Held",
    "play": "On Play",
    "boost": "On Boost",
}


def trigger_label(power: Power) -> str:
    """When a power fires, e.g. ``On Play`` — or ``? ? ?`` for the gamble Wu, which says nothing."""
    if is_gamble(power):
        return "? ? ?"
    trigger = trigger_of(power)
    return _TRIGGERS.get(trigger, f"On {trigger.capitalize()}")


def card_headline(card: Card) -> Text:
    """One Wu, named: its name in its element's colour, then its stats in brackets. Nothing else.

    **The established shape for a card anywhere it is named** — a button, a dialog, a reveal. The type
    glyph is deliberately absent: it belongs to the vault's hand panels, where it says what can build
    Mala Mala Jong and gives the eye something to sort by. On a button it is decoration, and decoration
    on a button is noise.

    Built on a FRESH Text: `card_name_text` carries the element colour as its base style, so appending
    to it directly tints the stats too (see `card_label`, which learned this the same way).
    """
    line = Text()
    line.append_text(card_name_text(card, bold=True))
    line.append(f" ({stats_line(card.stats)})")
    return line


def _rows(cards: list[Card], name_width: int, col_width: dict[str, int]) -> list[Text]:
    rows = []
    for index, card in enumerate(cards, 1):
        colour = COLORS.get(card.element, "white")
        icon = ICONS.get(card.type, "")
        name = card.name.rjust(name_width)
        stats = "/".join(stat_str(card.stats[key]).rjust(col_width[key]) for key in STAT_ORDER)
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
        key: max((len(stat_str(card.stats[key])) for card in both), default=1) for key in STAT_ORDER
    }
    return _rows(hand_a, name_width, col_width), _rows(hand_b, name_width, col_width)
