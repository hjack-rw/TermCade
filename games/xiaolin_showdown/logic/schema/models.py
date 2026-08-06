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
    BOT = "bot"  # Jack Spicer's Jack-Bot — kept distinct from DRAGON so it can evolve independently
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
    NULLIFY_BOOST = "nullify_boost"  # Star Hanabi
    CLEANSE = "cleanse"  # Kuzusu Atom
    SET_ELEMENT = "set_element"  # Eye of Dashi
    SET_ARENA = "set_arena"  # Monsoon Sandals
    WARD = "ward"  # the -phylaxia four
    TRANSFER = "transfer"  # Sun Chi Lantern
    WITCHCRAFT = "witchcraft"  # Wuya's character power
    BEAST_FORM = "beast_form"  # Chase Young's — see `powers.BEAST_BOOST`
    PROGNOSIS = "prognosis"  # the Mind Reader Conch
    TREASURE = "treasure"
    REFRESH = "refresh"
    DOUBLE_TRAINING = "double_training"
    STAT_SHIELD = "stat_shield"
    DOUBLE_ELEMENT = "double_element"
    SEIZE_GROUND = "seize_ground"  # Cube of Haniku — see `XiaolinState.ground_seized`
    AMEND = "amend"  # Hodoku Mouse — see `XiaolinState.undo`
    WISH = "wish"  # Treasurebox of the Blind Swordsman
    TRAIN_BOOST = "train_boost"  # a summon Wu — see `TRAIN_BOOST_STEP`
    ANIMATE = "animate"  # Heart of Jong
    HACK = "hack"  # Denshi Bunny
    STEAL = "steal"  # Sands of Time — shares AI Jack's own steal policy
    CONDUCT = "conduct"  # Shard of Lightning
    STAT_SWAP = "stat_swap"  # Ying Yo-Yo / Yang Yo-Yo
    CHI_SWAP = "chi_swap"  # Ying-Yang Yo-Yo (combined)


@dataclass
class Power:
    """What a Wu does, named — never encoded.

    The DB stores the *mechanic* by name, so a row says ``nullify_wu`` and means it: an unknown name
    cannot survive :func:`~.catalog.load_catalog`, so a typo is a DB that refuses to open rather than
    a Wu that quietly does nothing.

    ``trigger`` is not stored either — *when* a power fires follows from *what it is*, and
    :data:`~.mechanics.powers.RULES` is the one place that says so.
    """

    id: int
    name: str
    mechanic: Mechanic
    description: str
    initiative_bonus: int = 0
    # A summon Wu's flavour name: a fielded copy shows this instead of the Wu's own name (the hand still
    # shows the Wu). ``{caster}`` fills with the duelist's character. Cosmetic only. ``None`` otherwise.
    summon: str | None = None
    # TRAIN_BOOST only: 0 means the base ``TRAIN_BOOST_STEP``; a positive value overrides it.
    train_step: int = 0


@dataclass
class Card:
    id: int
    name: str
    stats: dict[str, int | None]  # force / agility / intellect
    power: Power
    element: str  # water | fire | wind | earth | metal
    type: str  # wudai | head | torso | amulet | arms | boots | item | empty
    points: int
    # The wear count (see logic/flow/wear.py): showdowns THIS copy was committed to by its CURRENT owner.
    # `uses_memory` holds the other duelist's count; changing hands swaps the two.
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
    """A named place a showdown can be fought in.

    ``element`` and ``sec_element`` are a set of tags, not a rank — ``Sunflower Field`` is fire and
    earth, and either name can summon it.
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
    # The Vault: every Wu this duelist has deposited, kept so a Treasurebox wish can restore one to
    # hand. A Treasurebox itself is never vaulted — its use is final.
    vault: list[Card] = field(default_factory=list)
    points: int = 0
    # The training bar (see logic/flow/training.py): progress toward the next payout, and whether a
    # payout was just taken.
    training: int = 0
    just_trained: bool = False
    # Mala Mala Jong (see logic/characters/jong.py): whether this duelist is wearing the construct, and
    # the Heart of Jong it exiled. The costume is an overlay — ``character`` stays the real duelist
    # underneath — so a revert needs nothing but to clear these two.
    jong_form: bool = False
    jong_heart: Card | None = None
    # The Yin/Yang Yo-Yo (logic/characters/jack.py, Mechanic.STAT_SWAP): whether this duelist's shown
    # affiliation currently reads flipped, cosmetic, persists until a Yo-Yo flips it back. Jack Spicer
    # alone reads this as Good Jack instead (see `jack.GOOD_JACK_STAT`), not a plain flip.
    yoyo_flipped: bool = False
    # Good Jack's own intellect, trained independently while the form is worn (see
    # logic/flow/training.py); a gain here also raises the real `character.stats["intellect"]`
    # permanently. Meaningless off of Jack.
    good_jack_intellect: int = 4
    # Reveal-memory: card ids this duelist has actually been told are in the OPPONENT's deck, from
    # personally firing a Diaskopia (see logic/flow/temple_ai.py). A snapshot at reveal time, not a
    # live view — a consumer intersects it against the opponent's current deck ids at read time, since
    # a once-seen card may since have been drawn out.
    known_of_opponent_deck: frozenset[int] = field(default_factory=frozenset)
    # Reveal-memory: card ids this duelist has actually been told are coming up next in the SHARED
    # pile, from personally firing a Teleskopia (see logic/flow/temple_ai.py). Same shape as
    # ``known_of_opponent_deck`` for the same reason — a consumer intersects it against the pile's
    # current front at read time, since the window shifts as either side draws, wins a prize, or
    # flies the Early Bird.
    known_upcoming_pile: frozenset[int] = field(default_factory=frozenset)

    @property
    def initiative(self) -> list[int]:
        """Derived, never stored: each hand card's passive initiative bonus, plus the character's own
        inherent bonus. Equal bonuses do not stack elsewhere (the sum takes distinct values)."""
        return [self.character.power.initiative_bonus] + [card.power.initiative_bonus for card in self.hand]

    @property
    def whole_hand(self) -> list[Card]:
        """Playable cards — the inalienable Wu (if any) ahead of the drawn hand.
        Initiative stays hand-only; the Wu never joins it."""
        return self.inalienable_hand + self.hand

    def remove_card(self, card: Card) -> None:
        """Remove the exact ``card`` from the hand, the inalienable slot, or the deck — a steal
        (see ``bot.steal_target``) can take from any of the three.

        Identity, not equality: the draw pile is padded with value-equal blank cards, so
        ``list.remove`` (which matches by value equality) can drop the wrong instance.
        """
        for holder in (self.hand, self.inalienable_hand, self.deck):
            for index, held in enumerate(holder):
                if held is card:
                    del holder[index]
                    return
