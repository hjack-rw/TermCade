"""Write ``tests/games/xiaolin_showdown/card_ids.py`` from ``xs_game.db`` — every mechanic that only
one pool Wu (``card.id >= FIRST_DECK_CARD``) carries becomes one constant, named after the mechanic.

    python scripts/generate_card_ids.py

Run this any time the card DB changes — a renumber, a rename, a new or removed Wu. Cards are tied to
their mechanic, not to a printed name or an id that a balance pass can move: a mechanic with exactly
one Wu is a fact the DB itself states, so the constant is derived, never hand-typed, and can never go
stale. A mechanic shared by several Wu (initiative, innate, train_boost, dragon...) has no single
answer a script can pick for you — those stay out of this file; a test that needs one specific Wu
among several says so inline, by whatever actually singles it out (a stat, a summon keyword, the
mechanic plus a second trait) — never a bare id.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from xiaolin_showdown.logic.schema.catalog import DEFAULT_DB
from xiaolin_showdown.logic.schema.constants import FIRST_DECK_CARD

OUT = Path(__file__).resolve().parent.parent / "tests" / "games" / "xiaolin_showdown" / "card_ids.py"

HEADER = '''"""Named cards the test suite reaches for, one constant per mechanic that only one pool Wu carries.

GENERATED — do not hand-edit. Run ``python scripts/generate_card_ids.py`` after any card DB change (a
renumber, a rename, a new or removed Wu) to bring this back in sync; ``test_seed.py``'s sibling check
fails the build the moment it drifts. Import from here instead of a bare integer:

    from card_ids import AMEND
    mouse = card(AMEND)

A mechanic several Wu share (initiative, innate, train_boost, dragon...) has no single right answer
the generator can pick — it is not represented here. A test that needs one specific Wu among several
picks it inline by whatever actually singles it out (a stat, a summon keyword, the mechanic plus a
second trait) — never a bare id.
"""

from __future__ import annotations

'''


def generate(db_path: Path = DEFAULT_DB, out_path: Path = OUT) -> Path:
    con = sqlite3.connect(str(db_path))
    try:
        rows = con.execute(
            """
            SELECT p.mechanic, MIN(c.id), MIN(c.name)
            FROM card c JOIN power p ON c.power_id = p.id
            WHERE c.id >= ?
            GROUP BY p.mechanic
            HAVING COUNT(*) = 1
            ORDER BY p.mechanic
            """,
            (FIRST_DECK_CARD,),
        ).fetchall()
    finally:
        con.close()

    lines = [HEADER]
    for mechanic, card_id, name in rows:
        lines.append(f'{mechanic.upper()} = {card_id}  # "{name}"\n')
    out_path.write_text("".join(lines), encoding="utf-8")
    return out_path


def main() -> None:
    path = generate()
    print(f"{DEFAULT_DB.name} -> {path}")


if __name__ == "__main__":
    main()
