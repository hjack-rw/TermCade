"""Shared page/table builder for the docs generator scripts (``scripts/generate_cards_page.py``,
``scripts/generate_knobs_page.py``) — not a script itself, nothing to run here.

A table used to be hand-written per page: one f-string for the ``<thead>``'s column labels, a
second, separately-maintained f-string per row deciding which cells sort and which don't. The two
could drift — a column added to one and not the other — with nothing to catch it. :class:`Column`
is the single source for both: its ``label`` builds the header cell, its ``render``/``sort``
build every body cell, so a page defines its columns once and the header and every row follow.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from html import escape

Row = sqlite3.Row


@dataclass(frozen=True)
class Column:
    label: str
    render: Callable[[Row], str]  # already-escaped cell HTML
    sort: Callable[[Row], str | int | float] | None = None  # None: sorts on the rendered text
    css_class: str = ""


def render_table(table_id: str, columns: list[Column], rows: list[Row]) -> str:
    """A ``<table>`` — headers from ``columns``, one ``<tr>`` per row, ``data-sort`` only where a
    column supplies it (``docs.js`` falls back to the cell's own text otherwise)."""
    thead = "".join(f"<th>{escape(c.label)}</th>" for c in columns)

    def cell(c: Column, r: Row) -> str:
        cls = f" class='{c.css_class}'" if c.css_class else ""
        sort = f" data-sort='{escape(str(c.sort(r)))}'" if c.sort else ""
        return f"<td{cls}{sort}>{c.render(r)}</td>"

    body_rows = "\n".join(
        "  <tr>" + "".join(cell(c, r) for c in columns) + "</tr>" for r in rows
    )
    return (
        f'<table id="{table_id}" data-sortable>\n'
        f"  <thead><tr>{thead}</tr></thead>\n"
        f"  <tbody>\n{body_rows}\n  </tbody>\n"
        "</table>"
    )


def mechanic_rules_script() -> str:
    """A ``<script type="application/json">`` blob of every mechanic's rule, keyed by the DB's own
    mechanic string — the same value a page's ``.mech`` cells already show — for ``docs.js``'s
    click-to-explain popup. Single source: ``xiaolin_showdown.logic.mechanics.powers.RULES``, never
    duplicated by hand, so a rule can't drift between the game and the page that explains it.

    GAMBLE is left out on purpose: its rule text states the exact payout spread, which is the one
    thing this game never tells a player — the card shows ``?`` and the popup must too.
    """
    from xiaolin_showdown.logic.mechanics.powers import RULES
    from xiaolin_showdown.logic.schema.models import Mechanic

    rules = {
        rule.mechanic.value: rule.text
        for rule in RULES.values()
        if rule.mechanic is not Mechanic.GAMBLE
    }
    return f'<script type="application/json" id="mechanic-rules">{json.dumps(rules)}</script>'


def page(title: str, subtitle: str, body: str, *, assets: str = "../assets") -> str:
    """The shared HTML skeleton. Defaults to ``../assets``, right for anything one level under
    ``docs/`` (``docs/xs_game/*.html``); a page generated at ``docs/`` itself (``docs/index.html``)
    passes ``assets="assets"``."""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<link rel="stylesheet" href="{assets}/docs.css">
</head>
<body>
<h1>{escape(title)}</h1>
<p class="sub">{subtitle}</p>
{body}
<script src="{assets}/docs.js"></script>
</body>
</html>
"""
