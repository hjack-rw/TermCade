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
    BOT = "bot"  # Jack Spicer's Jack-Bot — a dragon in a mechanical way, kept distinct so it can grow its own rules later without dragging the four playable dragons with it
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
    BEAST_FORM = "beast_form"  # Chase Young's — `duel.BEAST_BOOST` on the contested stat, Wu dead
    PROGNOSIS = "prognosis"  # new Mind Reader Conch — let them lead, but read and pin their challenge
    TREASURE = "treasure"  # a Wu with no power to spend — its worth is a fat deposit value
    REFRESH = "refresh"  # spend it to call one already-used Wu back to your hand
    DOUBLE_TRAINING = "double_training"  # held: every point of training its holder gains counts double
    STAT_SHIELD = "stat_shield"  # fielded: its caster is immune to curses on the stat it boosts
    DOUBLE_ELEMENT = "double_element"  # this Wu's own elemental bonus, resonance and drag alike, counts double
    SEIZE_GROUND = "seize_ground"  # Cube of Haniku — fielded, its caster takes the challenger's ground, overriding a temple Prognosis
    AMEND = "amend"  # Hodoku Mouse — spent at the temple, it puts the board back the way it was before your last action
    WISH = "wish"  # Treasurebox of the Blind Swordsman — one wish, chosen by where it is used, then gone for good: deposit for points, spend to restore a Wu from the Vault, or field to win the showdown outright
    TRAIN_BOOST = "train_boost"  # a summon Wu spent at the temple — one-time shove of TRAIN_BOOST_STEP into the training bar
    ANIMATE = "animate"  # Heart of Jong — nothing fielded alone; in the boost slot it morphs (Moby Morpher shape, arena element) into an animated form the background names. The seed of Mala Mala Jong's deferred assembly
    HACK = "hack"  # Denshi Bunny — vs a robot construct (Jack in any bot identity swap, never Mala Mala Jong): a stand-in (AI Jack, Attack!) auto-loses outright; a modifier (Chamelon-Bot's boost, Jack-Bot's curse) is nullified instead
    STEAL = "steal"  # Sands of Time — takes the opponent's strongest hand Wu, or a random deck card if the hand is empty; the same policy AI Jack's own steal already uses
    CONDUCT = "conduct"  # Shard of Lightning — +1 to the contested stat per metal Wu on the table this battle, -1 per non-metal Wu, either side, boosts included, plus +1/-1 more once the arena itself is decided. Uncapped, can go negative.
    STAT_SWAP = "stat_swap"  # Ying Yo-Yo / Yang Yo-Yo — names a stat, swapped with the opponent's Character for the rest of the showdown; also flips the caster's shown affiliation for the rest of the run (Good Jack, for Jack specifically)
    CHI_SWAP = "chi_swap"  # Ying-Yang Yo-Yo (combined) — same stat swap as the halves, but flips the OPPONENT's affiliation instead of the caster's own; a separate temple power lets the caster correct their own, exiling the card for good


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
    # A summon Wu's flavour: what it calls up to fight in its place. When set, a fielded copy shows this
    # on the board instead of the Wu's own name (the hand still shows the Wu). ``{caster}`` fills with the
    # duelist's character. Purely cosmetic — stats never change. ``None`` for an ordinary Wu.
    summon: str | None = None
    # A TRAIN_BOOST Wu's shove into the training bar. 0 means the base ``TRAIN_BOOST_STEP``; a positive
    # value is a higher-tier boost that overrides it. Ignored by every other mechanic.
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
    # The Vault: every Wu this duelist has deposited, kept (not just cashed) so a Treasurebox of the
    # Blind Swordsman can wish one back into hand. Deposits are the only things here; a Treasurebox is
    # never itself vaulted — its every use is final.
    vault: list[Card] = field(default_factory=list)
    points: int = 0
    # The training bar (see logic/training.py): progress toward the next payout, and whether a
    # payout was just taken — the bar shows full until the turn turns over, then resets to climb.
    training: int = 0
    just_trained: bool = False
    # Mala Mala Jong (see logic/jong.py): whether this duelist is wearing the construct, and the Heart
    # of Jong it exiled to power the form. The costume is an overlay — ``character`` stays the real
    # duelist underneath — so a revert needs nothing but to clear these two.
    jong_form: bool = False
    jong_heart: Card | None = None
    # The Yin/Yang Yo-Yo (logic/jack.py, Mechanic.STAT_SWAP): whether this duelist's shown
    # affiliation currently reads flipped — Xiaolin<->Heylin, cosmetic, persists across showdowns
    # until a Yo-Yo flips it back. Jack Spicer alone reads this as Good Jack instead (see
    # `jack.GOOD_JACK_STAT`), not a plain flip.
    yoyo_flipped: bool = False
    # Good Jack's own intellect — deliberately dumber than Evil Jack's real one, trained
    # independently while the form is worn (see logic/training.py); a gain here also raises the
    # real `character.stats["intellect"]` permanently. Meaningless off of Jack.
    good_jack_intellect: int = 4

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
