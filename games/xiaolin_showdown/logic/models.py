"""Domain models, ported from the reference ``src/DATA.py`` and ``Player`` in ``ENGINE.py``.

Plain data only. The reference's ``_info`` ANSI formatters are intentionally dropped —
rendering belongs to screens. Rows come from the bundled card DB via :mod:`catalog`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

# In the reference a card/character's 6th column is a *power id*; resolution is a lookup.
ResolvePower = Callable[[int], "Power"]


@dataclass
class Power:
    id: int
    name: str
    trigger: str  # "hand" | "deposit" | "boost" | "play"
    effect: int  # -1 | 0 | 1
    description: str
    initiative_bonus: int = 0

    @classmethod
    def from_row(cls, row: tuple) -> "Power":
        pid, name, trigger, effect, description = row
        # initiative bonus is encoded after a "~" only on passive hand powers (DATA.py:14-20)
        bonus = int(description.split("~")[1]) if (trigger == "hand" and effect == 0) else 0
        return cls(pid, name, trigger, effect, description.split("~")[0], bonus)


@dataclass
class Card:
    id: int
    name: str
    stats: dict[str, int | None]  # force / agility / intellect (None for non-combat cards)
    power: Power
    element: str  # water | fire | wind | earth | metal
    type: str  # wudai | head | torso | amulet | arms | boots | item | xiaolin | heylin | construct | empty
    points: int

    @classmethod
    def from_row(cls, row: tuple, resolve_power: ResolvePower) -> "Card":
        cid, name, force, agility, intellect, power_id, element, type_, points = row
        stats = {"force": force, "agility": agility, "intellect": intellect}
        return cls(cid, name, stats, resolve_power(power_id), element, type_, points)


@dataclass
class Character:
    id: int
    name: str
    stats: dict[str, int]
    power: Power
    affiliation: str
    is_playable: bool

    @classmethod
    def from_row(cls, row: tuple, resolve_power: ResolvePower) -> "Character":
        cid, name, force, agility, intellect, power_id, affiliation, is_playable = row
        stats = {"force": force, "agility": agility, "intellect": intellect}
        return cls(cid, name, stats, resolve_power(power_id), affiliation, bool(is_playable))


@dataclass
class Player:
    """A duelist's persistent, between-duel state (ENGINE.py Player, minus in-duel scratch)."""

    character: Character
    hand: list[Card] = field(default_factory=list)
    inalienable_hand: list[Card] = field(default_factory=list)
    deck: list[Card] = field(default_factory=list)
    points: int = 0

    @property
    def initiative(self) -> list[int]:
        """Derived, never stored: each hand card's passive initiative bonus (ENGINE.py:27)."""
        return [card.power.initiative_bonus for card in self.hand]

    @property
    def whole_hand(self) -> list[Card]:
        """Playable cards — the inalienable Wu (if any) ahead of the drawn hand
        (``ENGINE.show__whole__hand``). Initiative stays hand-only; the Wu never joins it."""
        return self.inalienable_hand + self.hand


def remove_card_from_hand(player: Player, card: Card) -> None:
    """Remove the exact ``card`` from the player's hand or inalienable slot.

    Identity, not equality: the draw pile is padded with value-equal blank cards, so
    ``list.remove`` (value equality, as the reference used) can drop the wrong instance.
    """
    for holder in (player.hand, player.inalienable_hand):
        for index, held in enumerate(holder):
            if held is card:
                del holder[index]
                return
