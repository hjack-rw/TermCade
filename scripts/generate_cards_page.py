"""Write ``docs/xs_game/CARDS.html`` from ``xs_game.db``.

    python scripts/generate_cards_page.py

Run this any time the card DB changes. See ``docs_html.py`` for why this is a generated HTML page
rather than a markdown table.
"""

from __future__ import annotations

import sqlite3
from html import escape
from pathlib import Path

from docs_html import Column, mechanic_rules_script, page, render_table
from xiaolin_showdown.logic.schema.catalog import DEFAULT_DB

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "xs_game" / "CARDS.html"


def _fetch_cards(con: sqlite3.Connection) -> list[sqlite3.Row]:
    return con.execute(
        """
        SELECT c.name, c.force, c.agility, c.intellect, c.element, c.type, c.points,
               p.name AS power_name, p.mechanic, p.description, p.initiative_bonus, p.train_step
        FROM card c LEFT JOIN power p ON c.power_id = p.id
        ORDER BY c.type, c.points, c.name
        """
    ).fetchall()


def _fetch_characters(con: sqlite3.Connection) -> list[sqlite3.Row]:
    return con.execute(
        """
        SELECT ch.name, ch.force, ch.agility, ch.intellect, ch.affiliation, ch.is_playable, ch.tier,
               p.name AS power_name, p.mechanic
        FROM character ch LEFT JOIN power p ON ch.power_id = p.id
        ORDER BY ch.is_playable DESC, ch.id
        """
    ).fetchall()


def _stats(r: sqlite3.Row) -> str:
    if r["force"] is None:
        return "—"
    return f"{r['force']}/{r['agility']}/{r['intellect']}"


CHAR_COLUMNS = [
    Column("Name", lambda r: escape(r["name"].replace("_", " "))),
    Column("F/A/I", lambda r: _stats(r), sort=lambda r: r["force"]),
    Column("Side", lambda r: escape(r["affiliation"])),
    Column("Tier", lambda r: escape(r["tier"] or ("playable" if r["is_playable"] else "—"))),
    Column("Power", lambda r: escape(r["power_name"] or "—")),
    Column("Mechanic", lambda r: escape(r["mechanic"] or ""), css_class="mech"),
]

# A gamble Wu's power and payout are deliberately secret — same "? ? ?" the card shows in-game.
CARD_COLUMNS = [
    Column("Name", lambda r: escape(r["name"])),
    Column("F/A/I", _stats, sort=lambda r: r["force"] if r["force"] is not None else -99),
    Column("Element", lambda r: escape(r["element"])),
    Column("Slot", lambda r: escape(r["type"])),
    Column(
        "Cost",
        lambda r: "?" if r["mechanic"] == "gamble" else str(r["points"]),
        sort=lambda r: "?" if r["mechanic"] == "gamble" else r["points"],
    ),
    Column(
        "Init",
        lambda r: f"{r['initiative_bonus']:+d}" if r["initiative_bonus"] else "—",
        sort=lambda r: r["initiative_bonus"],
    ),
    Column(
        "Train",
        lambda r: str(r["train_step"]) if r["train_step"] is not None else "—",
        sort=lambda r: r["train_step"] if r["train_step"] is not None else -1,
    ),
    Column("Power", lambda r: "? ? ?" if r["mechanic"] == "gamble" else escape(r["power_name"] or "—")),
    Column(
        "Mechanic",
        lambda r: "? ? ?" if r["mechanic"] == "gamble" else escape(r["mechanic"] or ""),
        css_class="mech",
    ),
    Column(
        "Description",
        lambda r: "? ? ?" if r["mechanic"] == "gamble" else escape(r["description"] or ""),
        css_class="wrap",
    ),
]


def render(con: sqlite3.Connection) -> str:
    cards = _fetch_cards(con)
    chars = _fetch_characters(con)
    slots = sorted({r["type"] for r in cards})
    slot_options = "\n".join(f"<option value='{escape(s)}'>{escape(s)}</option>" for s in slots)

    body = f"""
<h2>Duelists</h2>
<div class="tablewrap">
{render_table("chars", CHAR_COLUMNS, chars)}
</div>

<h2>Shen Gong Wu</h2>
<div class="controls">
  <input id="search" type="search" data-filter="cards" data-count="count"
         placeholder="Filter by name, element, mechanic&hellip;">
  <select id="slot" data-filter-column="3" data-filter-target="cards" data-count="count">
    <option value="">All slots</option>
    {slot_options}
  </select>
  <span class="count" id="count">{len(cards)} shown</span>
</div>
<div class="tablewrap">
{render_table("cards", CARD_COLUMNS, cards)}
</div>

<footer>
Most <code>initiative</code> cards are a flat turn-order bonus/penalty already shown above. Click any
<code>Mechanic</code> value for what it does and when it fires. See also
<a href="BALANCE.md">BALANCE.md</a> (current numbers) and
<a href="CIRCULATION.md">CIRCULATION.md</a> (how a Wu changes hands).
</footer>
{mechanic_rules_script()}
"""
    subtitle = (
        "Every card, character and power &mdash; generated straight from "
        "<code>games/xiaolin_showdown/data/xs_game.db</code>. Nothing here is hand-maintained; if a "
        "number looks wrong, the DB is wrong, not this page. Regenerate with "
        "<code>python scripts/generate_cards_page.py</code>."
    )
    return page("Xiaolin Showdown — Cards", subtitle, body)


def generate(db_path: Path = DEFAULT_DB) -> Path:
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    try:
        OUT.write_text(render(con), encoding="utf-8")
    finally:
        con.close()
    return OUT


def main() -> None:
    out = generate()
    print(f"{DEFAULT_DB.name} -> {out}")


if __name__ == "__main__":
    main()
