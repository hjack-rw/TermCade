"""``catalog_fingerprint.py`` and the DB it is generated from say the same thing.

Committed so the boss-ladder tamper check has a fingerprint without a build step, but generated — so
it can drift from the DB exactly like ``xs_game.sql``/``xs_game.db`` can (see ``test_seed.py``). This
is the test that makes that drift loud. If it fails: `python generate_catalog_fingerprint.py`.
"""

from __future__ import annotations

import shutil
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from generate_catalog_fingerprint import OUT, generate

from xiaolin_showdown.logic.schema.catalog import DEFAULT_DB, catalog_tampered


def test_catalog_fingerprint_matches_what_the_db_generates(tmp_path):
    regenerated = generate(out_path=tmp_path / "catalog_fingerprint.py").read_text(encoding="utf-8")
    committed = OUT.read_text(encoding="utf-8")

    assert regenerated == committed, "catalog_fingerprint.py is stale — run `python generate_catalog_fingerprint.py`"


def test_the_shipped_db_is_not_tampered():
    assert not catalog_tampered()


def test_an_edited_stat_is_caught_as_tampered(tmp_path):
    """The whole point: a hand-edited `.db` — not one rebuilt from `xs_game.sql` — must be caught."""
    edited = tmp_path / "edited.db"
    shutil.copy(DEFAULT_DB, edited)
    con = sqlite3.connect(str(edited))
    con.execute("UPDATE card SET points = points + 1 WHERE id = 5")
    con.commit()
    con.close()

    assert catalog_tampered(edited)
