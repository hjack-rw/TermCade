"""The card DB and the seed it is built from say the same thing.

``xs_game.sql`` is where a card is written; ``xs_game.db`` is what the game reads. Both are
committed — the wheel and the packaged exe bundle the DB as package data and neither runs a build
step — so the two can drift: a card added to the seed and never built, or a row edited straight
into the blob where no reviewer would see it.

This is the test that makes drift loud. If it fails: `python build_cards.py`.
"""

from __future__ import annotations

from xiaolin_showdown.logic.catalog import build_db, load_catalog


def test_the_committed_db_is_what_the_seed_builds(catalog, tmp_path):
    rebuilt = load_catalog(build_db(db_path=tmp_path / "xs_game.db"))

    assert rebuilt == catalog, "xs_game.db is out of date — run `python build_cards.py`"
