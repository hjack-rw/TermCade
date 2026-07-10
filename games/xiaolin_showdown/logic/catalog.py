"""Load the immutable card catalog from the bundled SQLite DB.

Read-only reference data — distinct from the engine's *save* store. The game owns this
file; the engine never sees it. ``sqlite3`` is stdlib, so the logic layer stays dependency-free.

Everything that knows what a row looks like lives here: column order, the ``power_id`` indirection,
and the ``~`` suffix that encodes an initiative bonus. :mod:`models` stays plain data.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Callable

from .models import Card, Character, Power

# Bundled alongside the package: games/xiaolin_showdown/data/xs_game.db
DEFAULT_DB = Path(__file__).resolve().parents[1] / "data" / "xs_game.db"

# A card/character row's 6th column is a *power id*; resolution is a lookup.
ResolvePower = Callable[[int], Power]


@dataclass(frozen=True)
class Catalog:
    powers: list[Power]
    cards: list[Card]
    characters: list[Character]

    def card(self, card_id: int) -> Card:
        return self._cards_by_id[card_id]

    def character(self, character_id: int) -> Character:
        return self._chars_by_id[character_id]

    @property
    def playable_characters(self) -> list[Character]:
        return [c for c in self.characters if c.is_playable]

    @property
    def opponent_characters(self) -> list[Character]:
        """Every non-playable character, across both opponent rosters."""
        return [c for c in self.characters if not c.is_playable]

    def opponents(self, *, hard: bool) -> list[Character]:
        """One opponent roster: the easy tier, or the tougher stat blocks (``is_hard``)."""
        return [c for c in self.opponent_characters if bool(c.is_hard) is hard]

    # Built on first lookup and kept — `cached_property` writes straight to __dict__, so it works
    # on a frozen dataclass. Without the cache, `card()` would rebuild the whole index per call.
    @cached_property
    def _cards_by_id(self) -> dict[int, Card]:
        return {c.id: c for c in self.cards}

    @cached_property
    def _chars_by_id(self) -> dict[int, Character]:
        return {c.id: c for c in self.characters}


def load_catalog(db_path: Path | str = DEFAULT_DB) -> Catalog:
    con = sqlite3.connect(str(db_path))
    try:
        powers = [_power(row) for row in con.execute("SELECT * FROM power")]
        by_id = {p.id: p for p in powers}
        resolve = by_id.__getitem__  # card/character power_id -> Power
        cards = [_card(row, resolve) for row in con.execute("SELECT * FROM card")]
        characters = [_character(row, resolve) for row in con.execute("SELECT * FROM character")]
    finally:
        con.close()
    return Catalog(powers=powers, cards=cards, characters=characters)


def _power(row: tuple) -> Power:
    pid, name, trigger, effect, description = row
    # an initiative bonus is encoded after a "~", and only on passive hand powers
    bonus = int(description.split("~")[1]) if (trigger == "hand" and effect == 0) else 0
    return Power(pid, name, trigger, effect, description.split("~")[0], bonus)


def _card(row: tuple, resolve_power: ResolvePower) -> Card:
    cid, name, force, agility, intellect, power_id, element, type_, points = row
    stats = {"force": force, "agility": agility, "intellect": intellect}
    return Card(cid, name, stats, resolve_power(power_id), element, type_, points)


def _character(row: tuple, resolve_power: ResolvePower) -> Character:
    cid, name, force, agility, intellect, power_id, affiliation, is_playable, is_hard = row
    stats = {"force": force, "agility": agility, "intellect": intellect}
    return Character(
        cid,
        name,
        stats,
        resolve_power(power_id),
        affiliation,
        bool(is_playable),
        None if is_hard is None else bool(is_hard),
    )
