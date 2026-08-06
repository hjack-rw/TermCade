"""Write ``docs/index.html`` — the Pages site root, linking to every generated page.

    python scripts/generate_index_page.py

Run this any time a page is added to or removed from ``docs/xs_game/``. Hand-maintained: there is no
DB table of "pages", and the list is short enough that keeping it here beats generating it from a
directory listing that can't say what each page is for.
"""

from __future__ import annotations

from pathlib import Path

from docs_html import page

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "index.html"

PAGES = [
    ("xs_game/CARDS.html", "Cards", "Every card, character and power — sortable and searchable."),
    ("xs_game/KNOBS.html", "Live knobs", "Every tunable value, sortable and searchable."),
]


def render() -> str:
    items = "\n".join(
        f'<li><a href="{href}">{name}</a><p>{desc}</p></li>' for href, name, desc in PAGES
    )
    body = f"""
<ul class="pagelist">
{items}
</ul>
<footer>
Source: <a href="https://github.com/hjack-rw/TermCade">github.com/hjack-rw/TermCade</a>
</footer>
"""
    subtitle = "Generated reference pages for Xiaolin Showdown, published from the repo's docs/ folder."
    return page("TermCade docs", subtitle, body, assets="assets")


def generate() -> Path:
    OUT.write_text(render(), encoding="utf-8")
    return OUT


def main() -> None:
    out = generate()
    print(f"-> {out}")


if __name__ == "__main__":
    main()
