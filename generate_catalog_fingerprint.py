"""Write ``games/xiaolin_showdown/logic/schema/catalog_fingerprint.py`` from ``xs_game.db`` — a hash
over every balance-relevant row (cards, characters, powers, ``mechanic_config``).

    python generate_catalog_fingerprint.py

Run this any time the card DB changes — a renumber, a rename, a re-balance, a new or removed Wu or
knob. The fingerprint is what :func:`~xiaolin_showdown.logic.schema.catalog.catalog_tampered` compares
a loaded ``.db`` against: a mismatch means the ``.db`` was hand-edited after the fact rather than
rebuilt from an honestly-edited ``xs_game.sql`` (:func:`~xiaolin_showdown.logic.schema.catalog.build_db`
always regenerates from empty), and the boss ladder refuses to count it (see
``config.settings.rules_modified``). Forgetting to regenerate after a real balance change would lock
the ladder out for everyone — ``test_catalog_fingerprint.py`` fails the build the moment it drifts.
"""

from __future__ import annotations

from pathlib import Path

from xiaolin_showdown.logic.schema.catalog import (
    DEFAULT_DB, catalog_fingerprint, load_catalog, load_mechanic_config,
)

OUT = Path(__file__).resolve().parent / "games" / "xiaolin_showdown" / "logic" / "schema" / "catalog_fingerprint.py"

HEADER = '''"""The canonical catalog's fingerprint — GENERATED, do not hand-edit.

Run ``python generate_catalog_fingerprint.py`` after any card DB change (a renumber, a rename, a
re-balance, a new or removed Wu or knob) to bring this back in sync; ``test_catalog_fingerprint.py``
fails the build the moment it drifts. See :func:`~xiaolin_showdown.logic.schema.catalog.catalog_tampered`.
"""

from __future__ import annotations

CANONICAL = '''


def generate(db_path: Path = DEFAULT_DB, out_path: Path = OUT) -> Path:
    catalog = load_catalog(db_path)
    config = load_mechanic_config(db_path)
    fingerprint = catalog_fingerprint(catalog, config)
    out_path.write_text(f'{HEADER}"{fingerprint}"\n', encoding="utf-8")
    return out_path


def main() -> None:
    path = generate()
    print(f"{DEFAULT_DB.name} -> {path}")


if __name__ == "__main__":
    main()
