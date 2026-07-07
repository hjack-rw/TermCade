"""Load the immutable card catalog from the bundled SQLite DB (ported from DATA.connect__database).

Read-only reference data — distinct from the engine's *save* store. The game owns this
file; the engine never sees it. ``sqlite3`` is stdlib, so the logic layer stays dependency-free.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .models import Card, Character, Power

# Bundled alongside the package: games/xiaolin_showdown/data/xs_game.db
DEFAULT_DB = Path(__file__).resolve().parents[1] / "data" / "xs_game.db"


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
        return [c for c in self.characters if not c.is_playable]

    # Built lazily so the dataclass stays a plain data container.
    @property
    def _cards_by_id(self) -> dict[int, Card]:
        return {c.id: c for c in self.cards}

    @property
    def _chars_by_id(self) -> dict[int, Character]:
        return {c.id: c for c in self.characters}


def load_catalog(db_path: Path | str = DEFAULT_DB) -> Catalog:
    con = sqlite3.connect(str(db_path))
    try:
        powers = [Power.from_row(row) for row in con.execute("SELECT * FROM power")]
        by_id = {p.id: p for p in powers}
        resolve = by_id.__getitem__  # card/character power_id -> Power
        cards = [Card.from_row(row, resolve) for row in con.execute("SELECT * FROM card")]
        characters = [Character.from_row(row, resolve) for row in con.execute("SELECT * FROM character")]
    finally:
        con.close()
    return Catalog(powers=powers, cards=cards, characters=characters)
