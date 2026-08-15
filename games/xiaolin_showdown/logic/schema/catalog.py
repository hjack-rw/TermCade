"""Load the immutable card catalog from the bundled SQLite DB.

Read-only reference data — distinct from the engine's *save* store. The game owns this
file; the engine never sees it. ``sqlite3`` is stdlib, so the logic layer stays dependency-free.

Everything that knows what a row looks like lives here: column order, the ``power_id`` indirection,
and the ``~`` suffix that encodes an initiative bonus. :mod:`models` stays plain data.

The DB is a build artifact. ``xs_game.sql`` is the source a card is written into, and
:func:`build_db` turns it into the file the game reads — see ``scripts/build_cards.py``.
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from functools import cached_property, lru_cache
from pathlib import Path
from typing import Callable

from .models import Background, Card, Character, Mechanic, Power

# Bundled alongside the package: games/xiaolin_showdown/data/
DATA = Path(__file__).resolve().parents[2] / "data"
DEFAULT_DB = DATA / "xs_game.db"
DEFAULT_SQL = DATA / "xs_game.sql"

# A card/character row's 6th column is a *power id*; resolution is a lookup.
ResolvePower = Callable[[int], Power]

# An ordinary opponent (Tubbimura, Vlad, ...) has no signature power at all — `power_id` is ``NULL``,
# not a row pointing at a "does nothing" placeholder, so the DB never has to reserve an id nobody's
# card or power ever collides with. A synthetic stand-in, never read from a row — like `resolve.
# _NEUTRAL_POWER`, which is why it shares that convention's `id=0`.
NO_POWER = Power(id=0, name="No power", mechanic=Mechanic.FILLER, description="")


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


def load_mechanic_config(db_path: Path | str = DEFAULT_DB) -> dict[str, dict[str, int]]:
    """The ``mechanic_config`` table, as ``{mechanic: {key: value}}`` — the balance knobs
    :mod:`.mechanics.powers` reads at import, so a row edit changes the number with no code change."""
    con = sqlite3.connect(str(db_path))
    try:
        rows = con.execute('SELECT "mechanic", "key", "value" FROM mechanic_config').fetchall()
    finally:
        con.close()
    config: dict[str, dict[str, int]] = {}
    for mechanic, key, value in rows:
        config.setdefault(mechanic, {})[key] = value
    return config


def catalog_fingerprint(catalog: Catalog, config: dict[str, dict[str, int]]) -> str:
    """A stable hash over every balance-relevant row — cards, powers, characters, ``mechanic_config``
    — order-independent of how the DB returned them. Two DBs with identical rows hash identically; one
    edited stat, power or knob changes it. Backgrounds are excluded: flavour only, never scored (see
    ``flow.duel.DuelState.background_name``).

    Compared against the canonical build's fingerprint (``catalog_fingerprint.CANONICAL``, generated
    by ``scripts/generate_catalog_fingerprint.py``) by :func:`catalog_tampered`, so a hand-edited ``.db`` — as
    opposed to one rebuilt from an honestly-edited ``xs_game.sql`` — can be told apart from a real
    balance change and kept from counting toward the boss ladder (see
    ``config.settings.rules_modified``).
    """
    parts: list[str] = []
    for card in sorted(catalog.cards, key=lambda c: c.id):
        stats = card.stats["force"], card.stats["agility"], card.stats["intellect"]
        parts.append(f"card:{card.id}:{card.name}:{stats}:{card.power.id}:{card.element}:"
                      f"{card.type}:{card.points}")
    for character in sorted(catalog.characters, key=lambda c: c.id):
        stats = character.stats["force"], character.stats["agility"], character.stats["intellect"]
        parts.append(f"character:{character.id}:{character.name}:{stats}:{character.power.id}:"
                      f"{character.affiliation}:{character.is_playable}:{character.tier}")
    for power in sorted(catalog.powers, key=lambda p: p.id):
        parts.append(f"power:{power.id}:{power.name}:{power.mechanic}:{power.initiative_bonus}:"
                      f"{power.summon}:{power.train_step}")
    for mechanic in sorted(config):
        for key in sorted(config[mechanic]):
            parts.append(f"config:{mechanic}:{key}:{config[mechanic][key]}")
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


def catalog_tampered(db_path: Path | str = DEFAULT_DB) -> bool:
    """Whether ``db_path`` diverges from the canonical build — a ``.db`` hand-edited after the fact,
    rather than rebuilt from an honestly-edited ``xs_game.sql`` (:func:`build_db` always regenerates
    from empty, so a legitimate change always carries a matching, regenerated fingerprint)."""
    from .catalog_fingerprint import CANONICAL  # generated — see scripts/generate_catalog_fingerprint.py

    catalog = load_catalog(db_path)
    config = load_mechanic_config(db_path)
    return catalog_fingerprint(catalog, config) != CANONICAL


@lru_cache(maxsize=None)
def load_catalog(db_path: Path | str = DEFAULT_DB) -> Catalog:
    """The catalog at ``db_path``, read once per distinct path and reused after that.

    Was a fresh, uncached ``sqlite3.connect()`` (~1.5-2ms measured) on every call, fired from
    ``GameContext.__init__`` among many other sites — on one process serving several sessions on a
    shared event loop, that blocks EVERY concurrently-connected player's render/input for its
    duration, not just the caller's. Safe to cache now, not before: the DB is a build artifact that
    never changes within a running process (see the module docstring), and the returned ``Catalog``
    holds the ONLY copy of each ``Card``/``Power`` object every caller will ever see from this
    function — so caching means every session sharing one process shares those objects, which is
    exactly the identity-sharing risk that requires ``new_game``'s ``deepcopy`` calls (and nothing
    downstream skipping them) to still be what actually keeps two sessions' cards apart. See
    ``tests/games/xiaolin_showdown/test_showdown_invariants.py::
    test_two_games_sharing_one_catalog_never_share_a_card_by_identity`` for the regression coverage
    that invariant now has.
    """
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
    pid, name, mechanic, description, initiative_bonus, summon, train_step = row
    return Power(
        pid, name, Mechanic(mechanic), description, initiative_bonus or 0, summon or None, train_step or 0
    )


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
        NO_POWER if power_id is None else resolve_power(power_id),
        affiliation,
        bool(is_playable),
        tier,
    )
