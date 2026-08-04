"""Presentation helpers for XS cards — element colors, type icons, stat strings.

Colors are emitted as Textual/Rich markup (``[blue]…[/]``); stats show ``?`` for the null-stat
cards.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from rich.text import Text

from ...logic.flow.duel import BEAST_BOOST
from ...logic.mechanics.powers import (
    ANIMATE_FIELD_STAT,
    ANIMATE_STAT,
    NAMED_STAT_VALUE,
    SCOPE_DEPTH,
    Mechanic,
    is_gamble,
    is_uncontrolled,
    mechanic_of,
    trigger_of,
)
from ...logic.schema.models import Card, Character, Power
from ...logic.content.naming import display_name  # moved to logic (the duel needs it too); screens import it here
from ...logic.flow.training import TRAIN_BOOST_STEP

# element -> colour, as explicit hex so the theme's ANSI palette can't remap it.
COLORS = {
    "water": "#4a9eff",
    "fire": "#ff5555",
    "wind": "#ffd43b",
    "earth": "#51cf66",
    "metal": "#ced4da",
}

# Plain Unicode symbols picked for *text* presentation (Emoji_Presentation=No), so no renderer draws
# them as colour emoji. Needs a comprehensive symbol font: Segoe UI Symbol on Windows (font fallback),
# and the browser build embeds a covering font in serve.py. Written as \u/\U escapes to keep source ASCII.
ICONS = {
    "wudai": "\U0001f5e1",  # weapon
    "head": "♔",  # crown
    "torso": "\U0001f580",  # armor
    "amulet": "\U0001f396",  # neckless
    "arms": "\U0001f591",  # hand
    "boots": "⛸︎",  # VS15: ambiguous width, so ask for the text face
    "item": "\U0001f6e0",  # tools
    "xiaolin": "☯",  # yin-yang
    "heylin": "☸",  # dharma wheel
    "construct": "⚙",  # robot gear
    "empty": "",
}


STAT_ORDER = ("force", "agility", "intellect")


def stat_str(value: int | None) -> str:
    return "?" if value is None else str(value)


def stats_line(stats: Mapping[str, int | None]) -> str:
    return "/".join(stat_str(stats[key]) for key in STAT_ORDER)


# Style for the contested stat. Explicit bright colour, not just bold — bold alone is advisory and a
# terminal may render it as nothing.
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
        text.append(value, style="dim" if challenge and stat != challenge else CONTESTED_STYLE)
    return text


def card_stats_text(stats: Mapping[str, int | None], challenge: str | None = None) -> Text:
    return stats_text([stat_str(stats[key]) for key in STAT_ORDER], challenge)


# Not zero: *absent*. `?` is a stat not yet resolved, `0` is a stat resolved to nothing, this is neither.
ABSENT = "-"


def absent_stats_text(challenge: str | None = None) -> Text:
    """A line that has been negated for this battle: no stats, and no element to resonate with."""
    return stats_text([ABSENT] * len(STAT_ORDER), challenge)


def char_stats(character: Character) -> str:
    return stats_line(character.stats)


# Name shortening moved to `logic.naming` (the duel needs it too, for summon names) — imported at the
# top and re-exported, so every `from .format import display_name` across the screens keeps working.


def affiliation_icon(character: Character) -> str:
    return ICONS.get(character.affiliation, "")


# Element order for a name cycled through all five colours (see WISH below).
_ELEMENT_CYCLE = ("water", "fire", "wind", "earth", "metal")


def _rainbow_name(name: str, *, bold: bool = False) -> Text:
    """A name lettered through the five element colours, one per character in turn."""
    weight = "bold " if bold else ""
    text = Text()
    for index, char in enumerate(name):
        text.append(char, style=f"{weight}{COLORS[_ELEMENT_CYCLE[index % len(_ELEMENT_CYCLE)]]}")
    return text


def card_name_text(card: Card, *, bold: bool = False) -> Text:
    """The card's name as element-coloured Rich text, using the in-duel resolved ``element`` (not
    necessarily the printed one). The WISH card is the exception: its name runs through all five
    colours rather than taking one. A card with no element falls back to plain white.
    """
    if mechanic_of(card.power) is Mechanic.WISH:
        return _rainbow_name(display_name(card.name), bold=bold)
    colour = COLORS.get(card.element, "white")
    return Text(display_name(card.name), style=f"bold {colour}" if bold else colour)


def points_label(card: Card) -> str:
    """A card's deposit value: ``X`` for a born wudai (can never be staked, lost or banked),
    ``?`` for a gamble card, else its printed points."""
    if _is_born_wudai(card):
        return "X"
    if is_gamble(card.power):
        return "?"
    return str(card.points)


# Born wudai: negative power id (the dragons, Jack-Bot), or MORPH (Hannibal's Morpher, whose power id
# is positive so it can't use the negative-id rule).
def _is_born_wudai(card: Card) -> bool:
    """A signature wudai a duelist holds from the start, never banked."""
    if card.type != "wudai":
        return False
    return card.power.id < 0 or mechanic_of(card.power) is Mechanic.MORPH


def display_type(card: Card) -> str:
    """The type word/``ICONS`` key for a card — ``card.type``, except a BOT-mechanic card (Jack-Bot)
    reads as ``construct`` instead of ``wudai``."""
    if mechanic_of(card.power) is Mechanic.BOT:
        return "construct"
    return card.type


def power_name_text(power: Power) -> Text:
    """A power's name, element-coloured when it names an element (``Dragon of Water``)."""
    element = power.name.rsplit(" ", 1)[-1].lower()
    if mechanic_of(power) is Mechanic.DRAGON and element in COLORS:
        return Text(power.name, style=COLORS[element])
    return Text(power.name)


def element_text(element: str) -> Text:
    """``Water`` in water's colour — the element named in its own colour, as Wu names are."""
    return Text(element.capitalize(), style=COLORS.get(element, "white"))


def labelled(label: str, value: str | Text, *, strong: bool = False, style: str = "") -> Text:
    """``Points: 12`` — a dim label, a bright value. The pairing used on the temple and the board."""
    text = Text()
    text.append(f"{label}: ", style="dim")
    if isinstance(value, Text):
        text.append_text(value)
    else:
        text.append(value, style=f"{'bold ' if strong else ''}{style}".strip())
    return text


def card_label(card: Card, suffix: str = "", *, prefix: str = "") -> Text:
    """``prefix`` + the element-coloured Wu name + plain ``suffix`` — a button label.

    Built on a fresh ``Text`` on purpose: ``card_name_text`` carries the element colour as its *base*
    style, so appending to it directly would tint the suffix too.
    """
    label = Text(prefix)
    label.append_text(card_name_text(card))
    label.append(suffix)
    return label


def card_options(cards: Sequence[Card], *, suffix_stats: bool = False) -> list[tuple[Text, Card]]:
    """``(label, card)`` options for a chooser — a Wu reads the same on a button as on the board.
    With ``suffix_stats`` the printed stats trail the name (the in-duel card picker wants them)."""
    return [
        (card_label(card, f"  ({stats_line(card.stats)})") if suffix_stats else card_label(card), card)
        for card in cards
    ]


def prompt(top: str | Text, question: str | Text) -> Text:
    """A dialog body: a statement, a blank line, then the question under it — the shape every dialog
    uses. ``top`` may be plain text or an already-styled ``Text`` (a card headline); this owns the
    single blank line between the two."""
    body = Text()
    body.append_text(top if isinstance(top, Text) else Text(top))
    body.append("\n\n")
    body.append_text(question if isinstance(question, Text) else Text(question))
    return body


def bonus_tooltip(bonuses: Sequence[int]) -> str:
    """``(+1, -1)`` — the buffs and debuffs behind an initiative, for a hover tooltip.

    ``bonuses`` are the ones ``scoring.initiative_sources`` credits, so they always sum to the
    initiative shown. Nothing applies → ``(/)``.
    """
    if not bonuses:
        return "(/)"
    return f"({', '.join(f'{bonus:+d}' for bonus in bonuses)})"


# One-line effect text per mechanic, shown under a Wu's flavour. The trigger is printed separately
# (see trigger_label), so it is not repeated here. Not every mechanic has an entry.
EFFECTS = {
    Mechanic.HAND_SIZE: "Hand limit: +1",
    Mechanic.DRAW: "Draw a Wu from the incoming Wu pile.",
    Mechanic.DRAGON: "Boosts only. Can't be staked, lost or banked.",
    Mechanic.BOT: "Boosts only. Can't be staked, lost or banked.",
    Mechanic.BOOST: "Enhances the played Wu by 1 per stat it holds.",
    Mechanic.MORPH: "You choose its Element.",
    Mechanic.NULLIFY_ELEMENT: "No Elemental bonus for either duelist all Showdown.",
    Mechanic.REVERSE_ELEMENT: "Elemental bonus reversed for either duelist all Showdown.",
    Mechanic.NULLIFY_BOOST: "Their boost's stats count nothing this battle.",
    Mechanic.CLEANSE: "Their Wu count as Metal this battle.",
    Mechanic.SET_ELEMENT: "You choose what element your Wu count as this battle.",
    Mechanic.SET_ARENA: "You choose the arena's element for the Showdown.",
    Mechanic.WARD: "Your Wu of its element cannot be dragged down this battle.",
    Mechanic.TRANSFER: "Swap your entire hand with your opponent's.",
    Mechanic.WITCHCRAFT: "Spent Wu return to her hand, worn; her turn can recall the lost.",
    # Read off the constant so this can't drift from what the duel actually deals.
    Mechanic.BEAST_FORM: f"+{BEAST_BOOST} to the contested stat, element-free; his Wu score nothing.",
    Mechanic.READ_DECK: "Read your opponent's personal Deck.",
    Mechanic.SCRY: f"Look at the next {SCOPE_DEPTH} Wu in the incoming Wu pile.",
    Mechanic.ENHANCED_VISION: "Take or refuse the next Showdown's Initiative.",
    Mechanic.PROGNOSIS: "Your opponent leads next Showdown, but you read their challenge and hold the tiebreak.",
    Mechanic.SEIZE_GROUND: "You hold the tiebreak all Showdown, overriding a Prognosis.",
    Mechanic.HACK: "Vs Jack shown as a bot, you win the Showdown outright; vs his own bot boost or "
    "curse, it counts nothing instead. Never against Mala Mala Jong.",
    Mechanic.STEAL: "Take their strongest hand Wu, or a random one from their Deck if their hand is empty.",
    Mechanic.CONDUCT: "+1 to the contested stat for every metal Wu in this battle, either side, "
    "boosts included; -1 for every non-metal one. The arena counts the same way. Can go negative.",
    Mechanic.STAT_SWAP: "Name a stat: swap it with your opponent's Character for the rest of the "
    "Showdown. Also flips your affiliation for the rest of the run, until you play another Yo-Yo.",
    Mechanic.CHI_SWAP: "Name a stat: swap it with your opponent's Character for the rest of the "
    "Showdown. Also flips YOUR OPPONENT'S affiliation for the rest of the run. Held, it may "
    "instead correct your own — exiled either way.",
    Mechanic.AMEND: "Take back your previous action this turn (boss runs only).",
    Mechanic.WISH: "One wish, then gone: deposit for points, restore a Vaulted Wu, or field to win the Showdown.",
    # TRAIN_BOOST is not here: its number is per-card (``train_step``), filled in by `effect_line`.
    Mechanic.BUFF: f"You name one stat. It takes +{NAMED_STAT_VALUE} in the battle.",
    Mechanic.MISFORTUNE: f"You name one stat. Your opponent takes −{NAMED_STAT_VALUE} in the battle.",
    Mechanic.FETCH: "Pull any one Wu from your own Deck into your hand.",
    Mechanic.BOUNCE: "Shove a Wu from their hand: deposit it (they keep the points) or bury it in their Deck (no points).",
    Mechanic.LUCK: "Bring the oldest lost Wu back – into your hand.",
    Mechanic.NULLIFY_STATS: "In battle: their own stats count nothing.",
    Mechanic.NULLIFY_CURSE: "In battle: the curses laid on you count nothing.",
    Mechanic.NULLIFY_WU: "In battle: every Wu they played counts nothing.",
    Mechanic.TREASURE: "Worth a bunch of points on deposit.",
    Mechanic.ANIMATE: f"A {ANIMATE_FIELD_STAT}/{ANIMATE_FIELD_STAT}/{ANIMATE_FIELD_STAT} body fielded; "
    f"boosted, a separate {ANIMATE_STAT}/{ANIMATE_STAT}/{ANIMATE_STAT} summon in the arena's element — and "
    f"your opponent may field one more Wu.",
    Mechanic.REFRESH: "Bring the Wu you last used back into your hand.",
    Mechanic.DOUBLE_TRAINING: "While held: the training you gain counts double.",
    Mechanic.STAT_SHIELD: "In battle: no curse can debuff the stat it boosts.",
    Mechanic.DOUBLE_ELEMENT: "Its own elemental advantage and disadvantage count double.",
}


# Mechanics that read differently on the Wu itself vs. the character who possesses it (see is_card
# below).
_WUDAI_MECHANICS = frozenset({Mechanic.DRAGON, Mechanic.MORPH, Mechanic.BOT})


def effect_line(power: Power, *, is_card: bool = True) -> str | None:
    """The one-liner under a Wu's flavour, or ``None`` for the ones that do not earn one.

    ``is_card`` distinguishes the Wu from the character who holds it — text differs between the two.
    """
    mechanic = mechanic_of(power)
    if not is_card:
        if mechanic is Mechanic.MORPH:
            # power id -5 (Elemental Manipulation) also carries a Deflection passive, described only here.
            if power.id == -5:
                return "Immutable Moby Morpher; deflects the elements — his drag and the foe's lift, metal aside."
            return "Immutable Moby Morpher."
        if mechanic is Mechanic.DRAGON:
            return "Possesses a personal Wudai weapon."
        if mechanic is Mechanic.BOT:
            return "Commands a personal construct."
        if mechanic is Mechanic.WITCHCRAFT:
            return "Her spent Wu return to her; the lost answer her call."
        if mechanic is Mechanic.BEAST_FORM:
            # Prize-gifting on a win is handled separately, in duel._award_prize.
            return f"Takes Beast Form for +{BEAST_BOOST}, but wields no Wu; keeps the prize he wins."
    if is_uncontrolled(power):
        return "Temple only: train a whole level at once. Fielded, it loses the Showdown for you."
    if mechanic is Mechanic.TRAIN_BOOST:  # the number is per-card, not baked per mechanic
        step = power.train_step or TRAIN_BOOST_STEP
        return f"Spend it to summon help to train against: +{step} to your training bar, once."
    return EFFECTS.get(mechanic)


_TRIGGERS = {
    "use": "On Use",
    "hand": "While Held",
    "play": "On Play",
    "boost": "On Boost",
    "deposit": "On Deposit",
}


def trigger_label(power: Power, *, is_card: bool = True, card_type: str | None = None) -> str:
    """When a power fires, e.g. ``On Play`` — or ``? ? ?`` for the gamble Wu, which says nothing.

    A wudai always fires as a *boost*, regardless of the weapon's own trigger (see ``_WUDAI_MECHANICS``
    and ``card_type``).
    """
    if is_gamble(power):
        return "? ? ?"
    possessed = not is_card and mechanic_of(power) in _WUDAI_MECHANICS
    if possessed or card_type == "wudai":
        return _TRIGGERS["boost"]
    trigger = trigger_of(power)
    return _TRIGGERS.get(trigger, f"On {trigger.capitalize()}")
