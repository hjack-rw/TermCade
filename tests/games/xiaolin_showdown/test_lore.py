"""The Lore book: the prose loads, it splits into the pages the author cut, and no page overflows.

The overflow test is the one that makes the no-scroll promise keepable — an over-long page becomes
something the author fixes while writing, not something a player discovers with prose missing.
"""

from __future__ import annotations

import pytest

from xiaolin_showdown.logic.lore import (
    PAGE_COLS,
    PAGE_ROWS,
    _sections,
    load_book,
    page_rows,
)


def test_every_chapter_loads_with_a_title_and_at_least_one_page():
    book = load_book()

    assert book, "the book is empty"
    for chapter in book:
        assert chapter.title, "a chapter loaded without a title"
        assert chapter.pages, f"{chapter.title} has no pages"


def test_an_authored_rule_ends_a_section():
    """`---` is the author's break, and it wins over the heading fallback."""
    parts = _sections("# X\n\nfirst\n\n---\n\n## Two\n\nsecond")

    assert len(parts) == 2
    assert parts[0].endswith("first")


def test_a_chapter_with_no_rule_falls_back_to_its_headings():
    """Never to the viewport — a section computed from the window is a scrolling column in disguise."""
    parts = _sections("# X\n\nopening\n\n## A\n\na\n\n## B\n\nb")

    assert len(parts) == 3  # the opening, then one per heading


def test_short_sections_share_a_page(tmp_path):
    """The point of packing: one section per page left pages a third full."""
    (tmp_path / "01-x.md").write_text("# X\n\nopening\n\n## A\n\na\n\n## B\n\nb\n", encoding="utf-8")

    (chapter,) = load_book(tmp_path)

    assert len(chapter.pages) == 1  # three tiny sections, one sheet


def test_a_section_that_does_not_fit_starts_the_next_page(tmp_path):
    """Whole sections only — one is never split across a page, so it moves rather than breaks."""
    tall = "\n\n".join(f"line {n}" for n in range(PAGE_ROWS))
    (tmp_path / "01-x.md").write_text(f"# X\n\n{tall}\n\n---\n\n## Later\n\nafter\n", encoding="utf-8")

    (chapter,) = load_book(tmp_path)

    assert len(chapter.pages) == 2
    assert chapter.pages[1].endswith("after")


def test_a_00_file_is_kept_beside_the_book_but_never_in_it(tmp_path):
    """The retiring drawer: cut prose without deleting it."""
    (tmp_path / "00-deferred.md").write_text("# Retired\n\ncut, but kept\n", encoding="utf-8")
    (tmp_path / "01-x.md").write_text("# X\n\nin the book\n", encoding="utf-8")

    titles = [chapter.title for chapter in load_book(tmp_path)]

    assert titles == ["X"]


def test_a_chapter_without_a_title_is_a_broken_file(tmp_path):
    (tmp_path / "01-x.md").write_text("no heading here\n", encoding="utf-8")

    with pytest.raises(ValueError):
        load_book(tmp_path)


def test_an_empty_lore_folder_raises_rather_than_rendering_an_empty_book(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_book(tmp_path)


def test_no_page_overflows_the_contract_size():
    """The promise the screen makes: one page, no scrollbar. This is what keeps it true."""
    too_long = [
        (chapter.title, number, rows)
        for chapter in load_book()
        for number, page in enumerate(chapter.pages, 1)
        if (rows := page_rows(page)) > PAGE_ROWS
    ]

    assert not too_long, f"pages over {PAGE_ROWS} rows at {PAGE_COLS} cols: {too_long}"
