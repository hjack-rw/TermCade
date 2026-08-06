"""``card_ids.py`` and the DB it is generated from say the same thing.

Committed for a readable diff and importable without a build step, but generated — so it can drift
from the DB exactly like ``xs_game.sql``/``xs_game.db`` can (see ``test_seed.py``). This is the test
that makes that drift loud. If it fails: `python scripts/generate_card_ids.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from generate_card_ids import OUT, generate


def test_card_ids_matches_what_the_db_generates(tmp_path):
    regenerated = generate(out_path=tmp_path / "card_ids.py").read_text(encoding="utf-8")
    committed = OUT.read_text(encoding="utf-8")

    assert regenerated == committed, "card_ids.py is out of date — run `python scripts/generate_card_ids.py`"
