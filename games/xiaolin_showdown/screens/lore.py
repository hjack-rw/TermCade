"""The Lore book — one page on screen, turned by hand.

A **book, not a scrolling document**. The split into pages is authored (see `logic/lore.py`); this
screen only shows one of them and moves between them. There is deliberately **no scrollbar**: a
scrollbar turns prose into a wall of text with a position indicator, and the position a scrollbar
would carry is in the footer instead, as `page 3 / 24`.

The reader turns from the last page of a chapter straight into the first of the next, so the six
chapters read as one continuous text. The contents page opens the book and doubles as a jump menu.
"""

from __future__ import annotations

from rich.console import RenderableType
from rich.style import Style
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header, Static

from termcade.ui.widgets import BoxedPanel

from ..logic.lore import Chapter, load_book, page_renderable
from .base import XiaolinScreen

CONTENTS = "Contents"


class LoreScreen(XiaolinScreen):
    # No panel to follow — the book is a page and a counter, so the button takes the screen's corner.
    BACK_RIGHT = True
    """The book. `_page` is the reader's place in a flat run of every page, contents first."""

    BINDINGS = [
        # Back first, so the footer reads left-to-right the way the arrows point.
        Binding("left,p", "previous", "Back", show=True),
        Binding("right,space,n", "next", "Next", show=True),
        Binding("c", "contents", "Contents", show=True),
        Binding("escape", "leave", "Leave", show=True),
        # The chapter jumps answer from anywhere, not just the contents page: a reader who knows they
        # want the Elements should not have to walk back to the front of the book to say so.
        *(Binding(str(n), f"chapter({n - 1})", show=False) for n in range(1, 10)),
    ]

    def compose(self) -> ComposeResult:
        self._book = load_book()
        # Contents is page 0, then every chapter's pages in order — so "next" from the last page of a
        # chapter lands on the first of the next one with no special case anywhere.
        self._pages: list[tuple[Chapter | None, int]] = [(None, 0)]
        for chapter in self._book:
            self._pages += [(chapter, index) for index in range(len(chapter.pages))]
        self._page = 0

        yield Header()
        with BoxedPanel(title="LORE", id="lore-panel"):
            yield Static(self._page_content(), id="lore-page")
        yield Static("", id="lore-footer")
        yield Footer()

    def on_mount(self) -> None:
        self._show()

    # --- turning -----------------------------------------------------------------------------
    def action_next(self) -> None:
        self._turn(1)

    def action_previous(self) -> None:
        self._turn(-1)

    def action_contents(self) -> None:
        self._page = 0
        self._show()

    def action_chapter(self, index: int) -> None:
        """Jump to the first page of chapter ``index``. Out of range is a key with nothing behind it."""
        if index >= len(self._book):
            return
        chapter = self._book[index]
        self._page = next(i for i, (owner, n) in enumerate(self._pages) if owner is chapter and n == 0)
        self._show()

    def action_leave(self) -> None:
        self.app.pop_screen()

    def _turn(self, step: int) -> None:
        """Move a page, stopping at the covers. The book does not wrap: running off the last page back
        to the contents would read as the text having restarted."""
        self._page = max(0, min(len(self._pages) - 1, self._page + step))
        self._show()

    # --- drawing -----------------------------------------------------------------------------
    def _show(self) -> None:
        self.query_one("#lore-page", Static).update(self._page_content())
        self.query_one("#lore-footer", Static).update(self._position())

    # NOT `_render`: `Widget._render` is Textual's own, and overriding it by accident replaces how the
    # widget draws itself rather than deciding what this screen shows.
    def _page_content(self) -> RenderableType:
        chapter, index = self._pages[self._page]
        if chapter is None:
            return self._contents()
        return page_renderable(chapter.pages[index])

    def _contents(self) -> Text:
        """The front of the book, and the jump menu — the number beside a chapter is the key that opens it.

        Laid out to breathe: the page is 32 rows and the list is five, so the space is there to use.
        """
        text = Text()
        text.append("\n")
        text.append("  Table of Contents\n", style="bold")
        text.append("\n\n")
        for number, chapter in enumerate(self._book, 1):
            # The number IS the key that opens the chapter — and a phone has no number
            # row, so the line itself opens it too: the same span the key would trigger.
            start = len(text.plain)
            # ONE styled run for the whole row, number included. Styled separately — the number bold,
            # the title plain — they render as two segments, and the hover highlight follows the
            # segment under the cursor rather than the clickable span: the row lit up from the title
            # onwards and left its own number outside the highlight, looking like the number was not
            # part of the target. It always was; only the lighting disagreed.
            text.append(f"      {number}    {chapter.title}\n\n", style="bold")
            text.stylize(
                Style(meta={"@click": f"screen.chapter({number - 1})"}),
                start,
                len(text.plain) - 2,
            )
        text.append("\n")
        text.append("      Press a number to open a chapter, or ")
        text.append("Space", style="bold")
        text.append(" to read from the beginning.")
        return text

    def _position(self) -> Text:
        """What a scrollbar would have said: where you are, and in which chapter.

        The middle dot (U+00B7) divides the parts — the same character the training bar uses for its
        remainder, so it is already known to render in the fonts this game ships with.
        """
        chapter, index = self._pages[self._page]
        if chapter is None:
            return Text(f"{CONTENTS}  ·  {len(self._book)} chapters", style="dim")
        return Text(
            f"{chapter.title}  ·  page {index + 1} / {len(chapter.pages)}"
            f"  ·  {self._page} / {len(self._pages) - 1} of the book",
            style="dim",
        )
