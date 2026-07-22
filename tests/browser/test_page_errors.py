"""Nothing in the page throws.

A script with a broken bracket does not 404, does not fail a request, and does not stop the page:
the browser reports it to a console nobody is reading and carries on parsing the next tag. The
terminal still renders, the fonts still resolve — the only thing that changed is that some feature
quietly stopped answering.

What this covers that the rest of the suite does not, measured rather than assumed:

* Breaking ``touch-gestures.js`` fails three swipe tests as well as these — that file is exercised
  directly, so it was never the gap.
* Breaking ``no-virtual-keyboard.js`` fails **only** these. 34 other browser tests and the whole
  Python suite stayed green, because nothing else drives it.
* Handing a bad value to a placeholder — a Python-side mistake that leaves the template perfectly
  valid — fails **only** these. ESLint exits 0, because the error does not exist until the page is
  rendered. That is the half of the problem no linter can reach.

So: eslint checks the template, this checks the page. Neither substitutes for the other.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from playwright.sync_api import Browser, ConsoleMessage, Error, Page

pytestmark = [pytest.mark.browser, pytest.mark.slow]

_VIEWPORT = {"width": 844, "height": 390}


class _Complaints:
    """Everything the browser objected to, with the listeners attached BEFORE navigation.

    That ordering is the whole trick: the scripts this is watching run in ``<head>``, so a page
    fixture that has already loaded is a page whose errors have already been and gone.
    """

    def __init__(self) -> None:
        self.messages: list[str] = []

    def watch(self, page: Page) -> None:
        page.on("pageerror", lambda error: self._add("uncaught", error))
        page.on("console", self._console)

    def _console(self, message: ConsoleMessage) -> None:
        if message.type == "error":
            self._add("console", message.text)

    def _add(self, kind: str, detail: object) -> None:
        text = detail.message if isinstance(detail, Error) else str(detail)
        self.messages.append(f"[{kind}] {text}")


@pytest.fixture
def watched(browser: Browser, served: str) -> Iterator[tuple[Page, _Complaints]]:
    complaints = _Complaints()
    page = browser.new_page(viewport=_VIEWPORT, is_mobile=True, has_touch=True)
    complaints.watch(page)
    page.goto(served, wait_until="networkidle")
    page.wait_for_selector(".xterm-screen", timeout=30_000)
    page.wait_for_function("document.fonts.status === 'loaded'", timeout=30_000)
    try:
        yield page, complaints
    finally:
        page.close()


def test_the_page_loads_without_a_single_script_error(
    watched: tuple[Page, _Complaints],
) -> None:
    """The gate. A syntax error in any inlined block lands here and nowhere else."""
    _, complaints = watched
    assert not complaints.messages, "the page complained:\n  " + "\n  ".join(complaints.messages)


def test_a_gesture_does_not_make_the_page_throw(watched: tuple[Page, _Complaints]) -> None:
    """The listeners are installed by the touch scripts and only run when a finger arrives, so a
    page that loads clean says nothing about them. A tap also wakes the audio context, which is the
    one path that constructs WebAudio objects for real."""
    page, complaints = watched
    page.touchscreen.tap(400, 200)
    page.wait_for_timeout(500)
    assert not complaints.messages, "a tap made the page complain:\n  " + "\n  ".join(
        complaints.messages
    )


def test_the_watcher_would_actually_notice(watched: tuple[Page, _Complaints]) -> None:
    """Guards the two above against being vacuous. A listener attached to the wrong event, or a
    filter that quietly drops everything, gives a permanently green test that checks nothing — which
    is the exact failure mode this whole file was written to replace."""
    page, complaints = watched
    page.evaluate("setTimeout(function(){ throw new Error('tc-canary'); }, 0)")
    page.wait_for_timeout(200)
    assert any("tc-canary" in message for message in complaints.messages), (
        "a thrown error did not reach the watcher — these tests prove nothing"
    )
