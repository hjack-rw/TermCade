"""Write ``docs/xs_game/KNOBS.html`` from ``xs_game.db``'s ``mechanic_config`` table.

    python scripts/generate_knobs_page.py

Run this any time ``mechanic_config`` changes. See ``docs_html.py`` for why this is a generated HTML
page rather than a markdown table.
"""

from __future__ import annotations

import sqlite3
from html import escape
from pathlib import Path

from docs_html import Column, mechanic_rules_script, page, render_table
from xiaolin_showdown.logic.schema.catalog import DEFAULT_DB

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "xs_game" / "KNOBS.html"

# What each knob does — not derivable from the DB, so it lives here rather than split across a
# markdown table nobody keeps in sync with this page. A new `mechanic_config` row with no entry here
# renders with an empty note: a nudge to add one, not a build failure.
_KNOB_NOTES: dict[tuple[str, str], str] = {
    ("animate", "field_stat"): "Heart of Jong's fielded-alone stat",
    ("animate", "stat"): "Heart of Jong construct stat",
    ("beast_form", "boost"): "Chase's Beast Form stat boost on the contested stat",
    ("beast_form", "margin"): "how far behind Chase must be to beast",
    (
        "bot",
        "attack_chance_when_leading",
    ): "Jack-bots Attack!'s base trigger chance while Jack leads",
    (
        "bot",
        "attack_chance_when_trailing",
    ): "Jack-bots Attack!'s base trigger chance while Jack trails",
    ("bot", "attack_max_chance"): "Attack!'s trigger-chance ceiling",
    ("bot", "attack_min_chance"): "Attack!'s trigger-chance floor",
    ("bot", "attack_momentum_cap"): "how far a loss/win streak can drift Attack!'s chance",
    ("bot", "attack_momentum_step"): "how much each streak step moves it",
    ("bot", "attack_stat"): "which stat Jack-bots Attack! contests",
    ("bot", "chamelon_margin"): "Jack's Chamelon-Bot: 0 = ties the player's lead, never beats it",
    ("bot", "flee_cap"): "Jack's free flees per run",
    ("bot", "good_jack_stat"): "Good Jack's base stat (dumber than Evil Jack's 3/3/7, not derived)",
    ("bot", "jack_force_margin"): "how far below STAT_CAP Jack's trained force stops (tops at 4)",
    ("bot", "printed_physical"): "Evil Jack's baseline force/agility, for training-delta math",
    ("buff", "value"): (
        "Orb of Tornami's stat swing (+3) — Kaijin's Curse (misfortune) reads the same row "
        "negated, no separate row needed"
    ),
    ("jong", "boost_stat"): "the Heart's boost-alone stat, as Jong",
    ("jong", "stat"): "Mala Mala Jong's base stat",
    ("morph", "aside"): "Hannibal's Morpher fielded-alone stat",
    ("morph", "boost"): "Hannibal's Morpher boost stat",
    ("scry", "depth"): "how many pile cards a scry reveals",
    ("witchcraft", "early_bird_gap"): "Wuya's own Early Bird flies at a reduced initiative gap",
    ("witchcraft", "recall_limit"): "Wuya's lost-Wu recalls per run",
    ("witchcraft", "recall_margin"): "minimum value a recalled Wu must clear",
    ("witchcraft", "returns"): "a spent Witchcraft Wu returns to hand",
    ("witchcraft", "wears"): "...and wears once for it",
}

KNOB_COLUMNS = [
    Column("Mechanic", lambda r: escape(r["mechanic"]), css_class="mech"),
    Column("Key", lambda r: escape(r["key"])),
    Column("Value", lambda r: str(r["value"]), sort=lambda r: r["value"]),
    Column(
        "What it does",
        lambda r: escape(_KNOB_NOTES.get((r["mechanic"], r["key"]), "")),
        css_class="wrap",
    ),
]


def _fetch(con: sqlite3.Connection) -> list[sqlite3.Row]:
    return con.execute(
        "SELECT mechanic, key, value FROM mechanic_config ORDER BY mechanic, key"
    ).fetchall()


def render(con: sqlite3.Connection) -> str:
    rows = _fetch(con)
    body = f"""
<div class="controls">
  <input id="search" type="search" data-filter="knobs" data-count="count"
         placeholder="Filter by mechanic, key, or what it does&hellip;">
  <span class="count" id="count">{len(rows)} shown</span>
</div>
<div class="tablewrap">
{render_table("knobs", KNOB_COLUMNS, rows)}
</div>
<footer>
Not DB-backed but still live (Settings-screen fields, deal weights, wager rules):
<a href="BALANCE.md">BALANCE.md</a>. Click any <code>Mechanic</code> value for what it does and when
it fires. Never hand-edit this page &mdash; regenerate with
<code>python scripts/generate_knobs_page.py</code> after any <code>mechanic_config</code> change.
</footer>
{mechanic_rules_script()}
"""
    subtitle = (
        "Every live <code>mechanic_config</code> row, one per key, generated straight from "
        "<code>xs_game.db</code>. Values can never go stale; the descriptions are curated in "
        "<code>scripts/generate_knobs_page.py</code> and won't rename or renumber themselves "
        "&mdash; if a key looks undocumented, that script is where to fix it."
    )
    return page("Xiaolin Showdown — Live knobs", subtitle, body)


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
