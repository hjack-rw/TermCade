"""The Lore book, loaded from the prose that ships with the cartridge.

A **book, not a scrolling document**: the reader turns pages, and a page is a unit the author chose.
That is the whole feature — the pacing of the lore is part of the lore — so the split lives here, in
pure logic, where a test can assert what a chapter holds without booting an app.

**Where a section ends.** An authored `---` rule ends a section; the file stays a legitimate markdown
document, and the author owns where one idea stops and the next starts. Where a chapter carries no
rule, it falls back to its `##` headings, which are the author's units too.

**Where a PAGE ends.** Sections are then packed onto pages: as many as fit, whole, in the order they
were written. A section is never split and never reordered, so the author's units survive — the only
thing decided here is how many of them share a sheet, which is a typesetting question and not a
pacing one. One section per page left pages a third full; a section that no longer fits simply starts
the next one.

Rendering lives here too (`page_renderable`) rather than in the screen, because the packer has to
measure exactly what the screen will draw — headings, blank lines and all. Two copies of that model
would drift and the packer would quietly mis-fill. `rich` is a text library with no TTY and is not
`textual`, so the no-textual rule for `logic/` still holds.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console, Group, RenderableType
from rich.markdown import Markdown
from rich.text import Text

LORE_DIR = Path(__file__).resolve().parent.parent / "lore"

# The size a page is promised to fit — the area `screens/lore.py` actually draws into, fixed by the
# `LoreScreen` rules in the game's theme and therefore the same at every window size. `test_lore.py`
# renders every page at this and fails if one overflows, so an over-long page is something the author
# fixes while writing, never something a player meets. `test_lore_screen.py` pins these two numbers to
# what the widget really measures: if the CSS moves and these do not, the guard would be checking a
# page size nobody draws.
PAGE_COLS = 100
PAGE_ROWS = 32

_PAGE_BREAK = re.compile(r"^-{3,}\s*$", re.MULTILINE)
_SECTION = re.compile(r"^(?=## )", re.MULTILINE)
_SUBHEAD = re.compile(r"^(?=> \*\*)", re.MULTILINE)


def page_renderable(page: str) -> RenderableType:
    """A page, spaced so its headings read as headings.

    Markdown collapses blank lines, so the gaps cannot be authored into the prose — the page is split
    apart and stacked with blank lines of its own. Three different gaps, each doing a different job:

    * **Under a chapter title** — one extra line; a chapter opening wants the air.
    * **Under a section heading** — nothing added. Markdown's own line is enough, and more would push
      the heading away from the prose it belongs to.
    * **ABOVE a section heading that lands mid-page** — the widest gap, because that heading has the
      previous section's last paragraph sitting on top of it and needs to be cut free of it.

    `Text("\\n")`, never `Text()` — an EMPTY Text renders no rows at all inside a Group, so a gap made
    that way silently does not appear.
    """
    parts = [part for part in _SUBHEAD.split(page) if part.strip()]
    if len(parts) == 1 and not page.startswith("# "):
        return Markdown(page)

    out: list[RenderableType] = []
    for index, part in enumerate(parts):
        if index:
            out.append(Text("\n"))  # air ABOVE the heading this part opens with
        head, sep, body = part.partition("\n")
        if head.startswith("# ") and sep and body.strip():
            out += [Markdown(head), Text("\n"), Markdown(body.lstrip("\n"))]
        else:
            out.append(Markdown(part))
    return Group(*out)


def page_rows(page: str) -> int:
    """How tall ``page`` draws at the contract width — what the packer fills against."""
    console = Console(file=io.StringIO(), width=PAGE_COLS)
    console.print(page_renderable(page))
    return len(console.file.getvalue().rstrip("\n").splitlines())  # type: ignore[attr-defined]


@dataclass(frozen=True)
class Chapter:
    """One prose file: its title, and the pages it was cut into."""

    title: str
    pages: tuple[str, ...]


def load_book(directory: Path | None = None) -> list[Chapter]:
    """Every chapter, in the order their filenames number them.

    A missing or unreadable chapter raises rather than rendering an empty book — the suite is where
    that gets caught, and a player should never open the lore to find a hole in it.
    """
    folder = directory or LORE_DIR
    # `00-` is the retiring drawer: prose kept beside the book but out of it. Cut a passage without
    # deleting it and it stays readable, in the same folder, in the same markdown — just unbound.
    files = [path for path in sorted(folder.glob("*.md")) if not path.name.startswith("00")]
    if not files:
        raise FileNotFoundError(f"no lore chapters in {folder}")
    return [_chapter(path.read_text(encoding="utf-8")) for path in files]


def _chapter(text: str) -> Chapter:
    body = text.strip()
    title = _title(body)
    return Chapter(title=title, pages=tuple(_pages(body)))


def _title(body: str) -> str:
    """The file's first `#` heading. A chapter with no title is a broken file, not a nameless one."""
    for line in body.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    raise ValueError("a lore chapter must open with a `# ` title")


def _sections(body: str) -> list[str]:
    """Split on authored rules; failing that, on section headings. Never on the viewport."""
    if _PAGE_BREAK.search(body):
        parts = _PAGE_BREAK.split(body)
    else:
        parts = _SECTION.split(body)
    return [part.strip() for part in parts if part.strip()]


def _pages(body: str) -> list[str]:
    """Pack the chapter's sections onto pages: as many whole sections as fit, in written order.

    A section is never split across a page and never reordered — only grouped. A section that would
    push the page past :data:`PAGE_ROWS` starts the next one instead. One that cannot fit a page even
    alone still gets its own page: nothing is silently dropped, and the overflow test is what says so.
    """
    pages: list[str] = []
    current = ""
    for section in _sections(body):
        candidate = f"{current}\n\n{section}" if current else section
        if current and page_rows(candidate) > PAGE_ROWS:
            pages.append(current)
            current = section
        else:
            current = candidate
    if current:
        pages.append(current)
    return pages
