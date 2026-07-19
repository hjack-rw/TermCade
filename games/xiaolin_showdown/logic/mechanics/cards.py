"""Asking questions about a *particular* card.

The duel never works on the cards in your hand. A played Wu enters the scoring queues as a
deep-copied stand-in, and a curse crosses the table as a mirror of one. :class:`~..models.Card` is a
plain dataclass, so all of those compare **equal** to the Wu they came from — and two different Wu
with the same printed face compare equal to each other.

So every question the duel asks — *is this Wu already spent? where does this mirror sit?* — is a
question about that one object, and `in` and `list.index` answer a different question than the one
being asked. These are the answers to the right one. Use them wherever a card is looked up.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from ..models import Card


def held_as_wudai(card: Card) -> Card:
    """A signature Wu held in the inalienable slot is a *wudai*, whatever its printed type.

    The dragons already print ``wudai``; Moby Morpher prints ``arms`` in the pool and becomes a wudai
    only in the one hand it can never leave — Hannibal's. Mutates and returns the given copy, so it is
    applied to the granted card, never the catalog. Both the deal and a save's restore go through it,
    so a loaded boss run does not quietly turn the Morpher back into an arm.
    """
    card.type = "wudai"
    return card


def is_one_of(card: Card, cards: Iterable[Card]) -> bool:
    """Is ``card`` one of ``cards`` — that object, not one that merely looks like it?"""
    return any(card is other for other in cards)


def excluding(cards: Iterable[Card], gone: Iterable[Card]) -> list[Card]:
    """``cards`` without the ones in ``gone``. The set difference, by identity."""
    spent = list(gone)
    return [card for card in cards if not is_one_of(card, spent)]


def index_of(cards: Sequence[Card], wanted: Card) -> int:
    """Where ``wanted`` sits in ``cards``. ``list.index`` would find the first *equal* card."""
    for index, card in enumerate(cards):
        if card is wanted:
            return index
    raise ValueError(f"{wanted.name!r} is not in this list")
