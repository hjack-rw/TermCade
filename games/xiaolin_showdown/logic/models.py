"""Domain models — cards, powers, characters, and a duelist.

Plain data only. Display formatting belongs to screens; decoding a DB row belongs to
:mod:`catalog`, which is the one module that knows the column order.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Power:
    id: int
    name: str
    trigger: str  # "hand" | "deposit" | "boost" | "play"
    effect: int  # -1 | 0 | 1 | ...
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


@dataclass
class Character:
    id: int
    name: str
    stats: dict[str, int]
    power: Power
    affiliation: str # xiaolin | heylin | construct | empty
    is_playable: bool
    # Which opponent roster this belongs to: the easy tier (False) or the hard one (True).
    # ``None`` on a playable character, which is on no opponent roster at all.
    is_hard: bool | None = None


@dataclass
class Player:
    """A duelist's persistent, between-duel state (no in-duel scratch)."""

    character: Character
    hand: list[Card] = field(default_factory=list)
    inalienable_hand: list[Card] = field(default_factory=list)
    deck: list[Card] = field(default_factory=list)
    points: int = 0

    @property
    def initiative(self) -> list[int]:
        """Derived, never stored: each hand card's passive initiative bonus."""
        return [card.power.initiative_bonus for card in self.hand]

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
