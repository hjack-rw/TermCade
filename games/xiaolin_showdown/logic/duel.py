"""The transient per-duel state (the reference's ``duel_stuff``).

**Runtime only — never saved.** A save's ``snapshot()`` is valid only at the vault, with no
active duel, so nothing here is serialized (the duel mutates deep-copied cards in place). The
stage machine and card resolution that drive this state land in the next slices.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import Card

LAST_STAGE = 6  # the showdown cycles stages 0..6 (ENGINE.py last_duel_stage)


@dataclass
class DuelState:
    stage: int = 0
    stakes: Card | None = None  # the prize card for this showdown
    challenge: str | None = None  # the contested stat: force / agility / intellect
    background: str | None = None  # the contested element
    player_priority: bool | None = None  # who commits first (None = tie → coin toss)
    player_stakes: list[Card] = field(default_factory=list)
    bot_stakes: list[Card] = field(default_factory=list)
    player_queue: list[Card] = field(default_factory=list)  # resolved cards feeding scoring
    bot_queue: list[Card] = field(default_factory=list)
    winner: bool | None = None  # True = player won, False = bot won
    winner_character: str | None = None
    card_won: bool = False
