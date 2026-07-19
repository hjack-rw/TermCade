"""Domain models — cards, powers, characters, and a duelist.

Plain data only. Display formatting belongs to screens; decoding a DB row belongs to
:mod:`catalog`, which is the one module that knows the column order.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Mechanic(StrEnum):
    """The rule a Wu's power buys — the whole vocabulary of what a power can *be*.

    The card DB names one of these and nothing else. What each one does, when it fires, and what it
    says to a player all live in :mod:`.mechanics.powers`; this is only the list of the words.

    It lives here, with the nouns, because :class:`Power` *is* one — and because a mechanic no card
    can name is a rule nobody can reach. The names are the powers' printed names (``CHRONOKINESIS``,
    ``INTANGIBLE``, ...), so a reader can grep one straight back to the card that carries it.
    """

    FILLER = "filler"
    INITIATIVE = "initiative"
    HAND_SIZE = "hand_size"
    HAND_FIZZLE = "hand_fizzle"
    GAMBLE = "gamble"
    DRAW = "draw"
    LUCK = "luck"
    DRAGON = "dragon"
    BOOST = "boost"
    INNATE = "innate"
    MORPH = "morph"
    NULLIFY_ELEMENT = "nullify_element"
    READ_DECK = "read_deck"
    SCRY = "scry"
    ENHANCED_VISION = "enhanced_vision"
    BUFF = "buff"
    MISFORTUNE = "misfortune"
    FETCH = "fetch"
    BOUNCE = "bounce"
    NULLIFY_STATS = "nullify_stats"
    NULLIFY_CURSE = "nullify_curse"
    NULLIFY_WU = "nullify_wu"
    REVERSE_ELEMENT = "reverse_element"
    NULLIFY_BOOST = "nullify_boost"  # Star Hanabi — the opponent's boost's stats count nothing
    CLEANSE = "cleanse"  # Kuzusu Atom — force a side's Wu to count as metal
    SET_ELEMENT = "set_element"  # Eye of Dashi — set a side's Wu to a chosen element
    SET_ARENA = "set_arena"  # Monsoon Sandals — change the arena's element
    WARD = "ward"  # the -phylaxia four — the caster's Wu of this card's element ignore drags
    TRANSFER = "transfer"  # Sun Chi Lantern — the two duelists swap hands
    WITCHCRAFT = "witchcraft"  # Wuya's character power — spent Wu return worn; the lost answer her
    BEAST_FORM = "beast_form"  # Chase Young's — +3 on the contested stat, but his Wu score nothing
    PROGNOSIS = "prognosis"  # new Mind Reader Conch — let them lead, but read and pin their challenge


@dataclass
class Power:
    """What a Wu does, named — never encoded.

    The DB stores the *mechanic*, so a row says ``subjugation`` and means it. It used to store a
    ``(trigger, effect)`` pair of integers: nothing but a lookup table said what ``use``/+5 meant, two
    cards could silently claim the same pair, and a typo became a Wu that quietly did nothing rather
    than a load that failed. Now an unknown name cannot survive :func:`~.catalog.load_catalog`.

    ``trigger`` is not stored either — *when* a power fires follows from *what it is*, and
    :data:`~.mechanics.powers.RULES` is the one place that says so.
    """

    id: int
    name: str
    mechanic: Mechanic
    description: str
    initiative_bonus: int = 0


@dataclass
class Card:
    id: int
    name: str
    stats: dict[str, int | None]  # force / agility / intellect
    power: Power
    element: str  # water | fire | wind | earth | metal
    type: str  # wudai | head | torso | amulet | arms | boots | item | empty
    points: int
    # The wear count (see logic/wear.py): showdowns THIS copy was committed to by its CURRENT owner.
    # Wear is per wearer and remembered: `uses_memory` holds the other duelist's count, and changing
    # hands swaps the two — win your Wu back and you resume where you left off.
    uses: int = 0
    uses_memory: int = 0


@dataclass
class Character:
    id: int
    name: str
    stats: dict[str, int]
    power: Power
    affiliation: str # xiaolin | heylin | construct | empty
    is_playable: bool
    # Which opponent roster this belongs to: 'easy', 'hard' or 'boss'. ``None`` on a playable
    # character, which is on no opponent roster at all.
    tier: str | None = None


@dataclass
class Background:
    """A named place a showdown can be fought in — flavour over an element, never a rule.

    A place belongs to a pool for *each* element it names: ``element`` and, when it has one,
    ``sec_element``. The two are a set of tags, not a rank — ``Sunflower Field`` is fire and earth,
    and either name can summon it. What scores is the element the duelist *named*, never the place.
    """

    id: int
    name: str
    element: str
    sec_element: str | None = None

    def belongs_to(self, element: str) -> bool:
        return element in (self.element, self.sec_element)


@dataclass
class Player:
    """A duelist's persistent, between-duel state (no in-duel scratch)."""

    character: Character
    hand: list[Card] = field(default_factory=list)
    inalienable_hand: list[Card] = field(default_factory=list)
    deck: list[Card] = field(default_factory=list)
    points: int = 0
    # The training bar (see logic/training.py): progress toward the next payout, and whether a
    # payout was just taken — the bar shows full until the turn turns over, then resets to climb.
    training: int = 0
    just_trained: bool = False

    @property
    def initiative(self) -> list[int]:
        """Derived, never stored: each hand card's passive initiative bonus, plus the character's own
        inherent bonus (Wuya's witchcraft carries +1). A 0 changes nothing — only Wuya's power is
        non-zero — and equal bonuses do not stack (the sum takes distinct values)."""
        return [self.character.power.initiative_bonus] + [card.power.initiative_bonus for card in self.hand]

    @property
    def whole_hand(self) -> list[Card]:
        """Playable cards — the inalienable Wu (if any) ahead of the drawn hand.
        Initiative stays hand-only; the Wu never joins it."""
        return self.inalienable_hand + self.hand

    def remove_card(self, card: Card) -> None:
        """Remove the exact ``card`` from the hand or the inalienable slot.

        Identity, not equality: the draw pile is padded with value-equal blank cards, so
        ``list.remove`` (which matches by value equality) can drop the wrong instance.
        """
        for holder in (self.hand, self.inalienable_hand):
            for index, held in enumerate(holder):
                if held is card:
                    del holder[index]
                    return
