"""Write ``games/xiaolin_showdown/data/xs_game.sql`` back out from ``xs_game.db`` — the other way.

    python dump_seed.py

The inverse of ``build_cards.py``, and the reason both exist: a card table is far easier to *edit*
in a DB browser than as forty columns of INSERT, so the ``.db`` is a legitimate place to work. What
must never happen is the two files disagreeing — so whichever one was edited, the other is
regenerated from it, and ``test_seed.py`` fails if anybody forgets.

Only the row data is rewritten. Every comment, ``CREATE TABLE`` and blank line in the seed is kept
exactly as written: the header explains why card ids are contiguous and why a power names its
mechanic, and that is the part no schema can hold.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from xiaolin_showdown.logic.catalog import DEFAULT_DB, DEFAULT_SQL

INSERT = re.compile(r'^INSERT INTO "?(\w+)"?\s')


def _literal(value: object) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, str):
        escaped = value.replace("'", "''")
        return f"'{escaped}'"
    return str(value)


def _rows(con: sqlite3.Connection, table: str) -> list[str]:
    """Every row of one table, as the INSERT lines the seed holds — ordered by id, so the file is
    stable: dumping the same DB twice must produce the same bytes, or the diff is noise."""
    columns = [row[1] for row in con.execute(f'PRAGMA table_info("{table}")')]
    names = ", ".join(f'"{column}"' for column in columns)
    lines = []
    for row in con.execute(f'SELECT {names} FROM "{table}" ORDER BY id'):
        values = ", ".join(_literal(value) for value in row)
        lines.append(f"INSERT INTO {table} ({names}) VALUES ({values});")
    return lines


def dump_seed(db_path: Path = DEFAULT_DB, sql_path: Path = DEFAULT_SQL) -> Path:
    con = sqlite3.connect(str(db_path))
    try:
        old = sql_path.read_text(encoding="utf-8").splitlines()
        new: list[str] = []
        index = 0
        while index < len(old):
            match = INSERT.match(old[index])
            if not match:  # a comment, a CREATE, a blank — kept verbatim
                new.append(old[index])
                index += 1
                continue
            table = match.group(1)
            while index < len(old):  # skip the whole stale run of rows for this table
                run = INSERT.match(old[index])
                if not run or run.group(1) != table:
                    break
                index += 1
            new.extend(_rows(con, table))
        sql_path.write_text("\n".join(new) + "\n", encoding="utf-8")
    finally:
        con.close()
    return sql_path


def main() -> None:
    sql = dump_seed()
    print(f"{DEFAULT_DB.name} -> {sql}")
    print(f"  {sum(1 for line in sql.read_text(encoding='utf-8').splitlines() if INSERT.match(line))} rows")


if __name__ == "__main__":
    main()
