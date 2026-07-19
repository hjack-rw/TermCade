"""Load the immutable card catalog from the bundled SQLite DB.

Read-only reference data — distinct from the engine's *save* store. The game owns this
file; the engine never sees it. ``sqlite3`` is stdlib, so the logic layer stays dependency-free.

Everything that knows what a row looks like lives here: column order, the ``power_id`` indirection,
and the ``~`` suffix that encodes an initiative bonus. :mod:`models` stays plain data.

The DB is a build artifact. ``xs_game.sql`` is the source a card is written into, and
:func:`build_db` turns it into the file the game reads — see ``build_cards.py``.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Callable

from .models import Background, Card, Character, Mechanic, Power

# Bundled alongside the package: games/xiaolin_showdown/data/
DATA = Path(__file__).resolve().parents[1] / "data"
DEFAULT_DB = DATA / "xs_game.db"
DEFAULT_SQL = DATA / "xs_game.sql"

# A card/character row's 6th column is a *power id*; resolution is a lookup.
ResolvePower = Callable[[int], Power]


@dataclass(frozen=True)
class Catalog:
    powers: list[Power]
    cards: list[Card]
    characters: list[Character]
    backgrounds: list[Background]

    def backgrounds_for(self, element: str) -> list[Background]:
        """Every place that element can summon — its own, and the ones that merely name it too."""
        return [b for b in self.backgrounds if b.belongs_to(element)]

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

    def opponents(self, tier: str) -> list[Character]:
        """One opponent roster: ``'easy'``, ``'hard'`` or ``'boss'``."""
        return [c for c in self.opponent_characters if c.tier == tier]

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
        backgrounds = [_background(row) for row in con.execute("SELECT * FROM background")]
    finally:
        con.close()
    return Catalog(powers=powers, cards=cards, characters=characters, backgrounds=backgrounds)


def build_db(sql_path: Path | str = DEFAULT_SQL, db_path: Path | str = DEFAULT_DB) -> Path:
    """Rebuild the card DB from the seed. The seed is written by hand; this file never is.

    Built from empty rather than migrated: the catalog is reference data with no history to keep,
    so the seed is the whole truth and a rebuild can't inherit a row somebody edited in the blob.
    """
    db_path = Path(db_path)
    db_path.unlink(missing_ok=True)
    con = sqlite3.connect(str(db_path))
    try:
        con.executescript(Path(sql_path).read_text(encoding="utf-8"))
        con.commit()
    finally:
        con.close()
    return db_path


def _background(row: tuple) -> Background:
    bg_id, name, element, sec_element = row
    return Background(bg_id, name, element, sec_element or None)


def _power(row: tuple) -> Power:
    """A power row, decoded. The mechanic is validated *here*, at load.

    ``Mechanic(name)`` raises on a name nobody implemented, so a typo in the seed is a DB that
    refuses to open rather than a Wu that quietly does nothing for a whole run. That failure mode is
    the entire reason the DB names its mechanic instead of encoding it as a pair of integers.

    ``initiative_bonus`` is its own column.
    """
    pid, name, mechanic, description, initiative_bonus = row
    return Power(pid, name, Mechanic(mechanic), description, initiative_bonus or 0)


def _card(row: tuple, resolve_power: ResolvePower) -> Card:
    cid, name, force, agility, intellect, power_id, element, type_, points = row
    stats = {"force": force, "agility": agility, "intellect": intellect}
    return Card(cid, name, stats, resolve_power(power_id), element, type_, points)


def _character(row: tuple, resolve_power: ResolvePower) -> Character:
    cid, name, force, agility, intellect, power_id, affiliation, is_playable, tier = row
    stats = {"force": force, "agility": agility, "intellect": intellect}
    return Character(
        cid,
        name,
        stats,
        resolve_power(power_id),
        affiliation,
        bool(is_playable),
        tier,
    )
