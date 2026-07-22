"""Presentation helpers for XS cards — element colors, type icons, stat strings.

Colors are emitted as Textual/Rich markup (``[blue]…[/]``); stats show ``?`` for the null-stat
cards.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from functools import cache

from rich.style import Style
from rich.text import Text

from ..logic.catalog import load_catalog
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


# A name longer than this is shortened to its first word where space is scarce. The threshold is the
# point of it: "Le Mime" is two words and seven characters, and "Le" is not a name — so the rule has
# to fire on what a name COSTS, not on how many words it happens to have. At 10 it takes Salvador
# Cumo, Hannibal Roy Bean and Chase Young, all of whom are known by their first name, and leaves
# Le Mime whole.
SHORTEN_OVER = 10


def display_name(name: str, *, upper: bool = False, short: bool = False) -> str:
    """A stored name shown for humans: underscores become spaces (``Salvador_Cumo`` -> ``Salvador Cumo``).
    ``upper`` shouts it for a heading, keeping the underscore rule in one place.

    ``short`` asks for the first word alone, and is honoured only for a name long enough to be worth
    it (see ``SHORTEN_OVER``). A phone is the caller: the temple's state row has about 86 columns to
    spend and a full name pushes Deck and Initiative off the end entirely — they truncate to
    ``Deck:…`` and ``Initiative: …``, which is a label costing the value it was there to introduce.
    """
    shown = name.replace("_", " ")
    if short and len(shown) > SHORTEN_OVER:
        shown = shown.split(" ", 1)[0]
    return shown.upper() if upper else shown


def affiliation_icon(character: Character) -> str:
    return ICONS.get(character.affiliation, "")


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

    A *born* wudai weapon can never be staked, lost or banked, so ``X`` reads "not for sale" where a
    ``0`` would read "worth nothing": a dragon held from the start, or Hannibal's Morpher. A wudai
    *found* in the pile — the Shimo Staff — is the exception: it is banked like any Wu and shows its
    real points, as does a Morpher drawn from the pool (type ``arms``).
    """
    if _is_born_wudai(card):
        return "X"
    if is_gamble(card.power):  # nobody knows, and the card is not going to tell you
        return "?"
    return str(card.points)


def _is_born_wudai(card: Card) -> bool:
    """A signature wudai a duelist holds from the start, never banked — as opposed to one won off the
    pile. A dragon born in the hand carries a negative power id; Hannibal's Morpher is a wudai-typed
    Morph. The Shimo Staff is a dragon *found* in the pile (positive id), so it is not born."""
    if card.type != "wudai":
        return False
    return card.power.id < 0 or mechanic_of(card.power) is Mechanic.MORPH


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
    Mechanic.DRAW: "Draw a Wu from the incoming Wu pile.",
    Mechanic.DRAGON: "Boosts only. Can't be staked, lost or banked.",
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
    Mechanic.BEAST_FORM: "+3 to the contested stat, element-free; his Wu score nothing.",
    Mechanic.READ_DECK: "Read your opponent's personal Deck.",
    Mechanic.SCRY: f"Look at the next {SCOPE_DEPTH} Wu in the incoming Wu pile.",
    Mechanic.ENHANCED_VISION: "Take or refuse the next Showdown's Initiative.",
    Mechanic.PROGNOSIS: "Your opponent leads next Showdown, but you read their challenge and hold the tiebreak.",
    Mechanic.BUFF: f"You name one stat. It takes +{NAMED_STAT_VALUE} in the battle.",
    Mechanic.MISFORTUNE: f"You name one stat. Your opponent takes −{NAMED_STAT_VALUE} in the battle.",
    Mechanic.FETCH: "Pull any one Wu from your own Deck into your hand.",
    Mechanic.BOUNCE: "Shove a Wu from their hand: deposit it (they keep the points) or bury it in their Deck (no points).",
    Mechanic.LUCK: "Bring the oldest lost Wu back – into your hand.",
    Mechanic.NULLIFY_STATS: "In battle: their own stats count nothing.",
    Mechanic.NULLIFY_CURSE: "In battle: the curses laid on you count nothing.",
    Mechanic.NULLIFY_WU: "In battle: every Wu they played counts nothing.",
    Mechanic.TREASURE: "Worth a bunch of points on deposit.",
    Mechanic.REFRESH: "Bring the Wu you last used back into your hand.",
    Mechanic.DOUBLE_TRAINING: "While held: the training you gain counts double.",
    Mechanic.STAT_SHIELD: "In battle: no curse can debuff the stat it boosts.",
    Mechanic.DOUBLE_ELEMENT: "Its own elemental advantage and disadvantage count double.",
}


# A wudai weapon is boost-only and unlosable — but a *character* whose power is one does not print the
# weapon's own rules; they possess it. So the same mechanic reads one way on the Wu, another on its owner.
_WUDAI_MECHANICS = frozenset({Mechanic.DRAGON, Mechanic.MORPH})


def effect_line(power: Power, *, is_card: bool = True) -> str | None:
    """The one-liner under a Wu's flavour, or ``None`` for the ones that do not earn one.

    ``is_card`` distinguishes the Wu from the character who holds it: a dragon (or Hannibal's Morpher)
    reads "boost only, can't be lost" as a *weapon*, but "possesses a custom wudai weapon" as a *power*.
    """
    mechanic = mechanic_of(power)
    if not is_card:
        # Hannibal's Morpher is his one wudai, held unlosably; a dragon is a generic born weapon.
        if mechanic is Mechanic.MORPH:
            return "Immutable Moby Morpher."
        if mechanic is Mechanic.DRAGON:
            return "Possesses a personal Wudai weapon."
        if mechanic is Mechanic.WITCHCRAFT:
            return "Her spent Wu return to her; the lost answer her call."
        if mechanic is Mechanic.BEAST_FORM:
            return "Takes Beast Form for +3, but wields no Wu; gifts the prize he wins."
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

    A wudai fires as a *boost*, whatever the weapon's own trigger — so it reads ``On Boost`` whether
    shown on the character who possesses it (a dragon, or Hannibal) or on a wudai-typed Wu itself
    (Hannibal's Morpher). The same Morpher drawn from the pool (type ``arms``) is fielded: ``On Play``.
    """
    if is_gamble(power):
        return "? ? ?"
    possessed = not is_card and mechanic_of(power) in _WUDAI_MECHANICS
    if possessed or card_type == "wudai":
        return _TRIGGERS["boost"]
    trigger = trigger_of(power)
    return _TRIGGERS.get(trigger, f"On {trigger.capitalize()}")


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
        # The wear count rides on the row's own span (the panels share one Static — see the state
        # grid's tooltip note in temple.py), so hovering any Wu answers "how worn is it".
        row.stylize(Style(meta={"tooltip": f"Used: {card.uses}"}))
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
