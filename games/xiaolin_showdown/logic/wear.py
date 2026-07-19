"""Wear — "Three Times in a Row": a Wu fielded in its third showdown is deposited, free.

Nobody rides one overpowered Wu through a whole run: every showdown a Wu is committed to (staked,
or spent as a boost) wears it by one, and the showdown that brings it to the limit VAULTS it on the
spot — banked for its points, costing no action. Only showdowns count, never turns spent in hand.

The count is PER WEARER, and remembered: a Wu that changes hands arrives fresh for its new owner,
but its old owner's count waits in the card's pocket — win it back and you resume where you left
off. Measured against reset-on-every-transfer at 200 runs/tier: identical within noise; remembered
is the author's call.

The inalienable wudai is exempt — it cannot be banked at all, so it cannot wear out.
"""

from __future__ import annotations

from termcade.core.rng import Rng

from .constants import WEAR_LIMIT
from .mechanics.cards import is_one_of
from .models import Card, Player
from .turn import bank_value

__all__ = ["WEAR_LIMIT", "hand_over", "record_showdown"]


def hand_over(card: Card) -> Card:
    """A Wu changing hands swaps whose count is live: fresh for the new owner (their own count, in
    a two-duelist run), while the departing owner's waits in the pocket to be resumed."""
    card.uses, card.uses_memory = card.uses_memory, card.uses
    return card


def record_showdown(player: Player, committed: list[Card], *, rng: Rng) -> list[tuple[Card, int]]:
    """Wear every Wu ``player`` committed to the ended showdown and STILL HOLDS, then vault the
    worn-out for their points. Returns what was vaulted, with what each paid, for the log.

    Checked against the plain hand only: a staked Wu the showdown took away wears for its NEW owner
    from zero, and the inalienable slot cannot wear at all.
    """
    for card in committed:
        if is_one_of(card, player.hand):
            card.uses += 1
    vaulted = []
    for card in [c for c in player.hand if c.uses >= WEAR_LIMIT]:
        player.remove_card(card)
        paid = bank_value(card, rng)
        player.points = max(0, player.points + paid)  # a bad gamble cannot go below zero
        vaulted.append((card, paid))
    return vaulted
