"""Build ``games/xiaolin_showdown/data/xs_game.db`` from ``xs_game.sql`` — the card catalog.

    python build_cards.py

Run this after editing the seed. Its inverse is ``dump_seed.py``, which writes the seed back out
from the ``.db`` — the two files hold the same rows and either may be edited, whichever is easier.

Both are committed: the seed so a new Wu is a readable line in a diff, the ``.db`` because the
packaged exe and the wheel bundle it as package data and neither runs a build step. Two committed
files means they can drift, so ``tests/games/xiaolin_showdown/test_seed.py`` fails the moment they
disagree. Run the matching script, commit both.
"""

from __future__ import annotations

from xiaolin_showdown.logic.catalog import DEFAULT_SQL, build_db, load_catalog


def main() -> None:
    db = build_db()
    catalog = load_catalog(db)
    print(f"{DEFAULT_SQL.name} -> {db}")
    print(
        f"  {len(catalog.cards)} cards, {len(catalog.powers)} powers, "
        f"{len(catalog.characters)} characters, {len(catalog.backgrounds)} backgrounds"
    )


if __name__ == "__main__":
    main()
