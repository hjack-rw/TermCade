"""The two things that made a fix invisible to the device it was for.

Both failures look identical from the outside — the game runs, the server logs a normal request, and
nothing that was changed appears to have changed. One is the page being cached; the other is the
page's own answer being cached in the URL, which is worse, because reloading is what carries it
forward.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Browser

pytestmark = [pytest.mark.browser, pytest.mark.slow]

_PORTRAIT = {"width": 390, "height": 844}
_LANDSCAPE = {"width": 844, "height": 390}

_FONT = "() => parseInt(new URLSearchParams(location.search).get('fontsize'), 10)"


def _open(browser: Browser, served: str, viewport: dict[str, int], query: str = ""):
    page = browser.new_page(viewport=viewport, is_mobile=True, has_touch=True)
    page.goto(served + query, wait_until="networkidle")
    page.wait_for_selector(".xterm-screen", timeout=30_000)
    page.wait_for_timeout(2500)
    return page


def test_the_page_is_never_served_from_cache(browser: Browser, served: str) -> None:
    """A restarted server has to reach the phone. Without this the device keeps running the build it
    first downloaded, and every later fix is invisible to the one place it was made for."""
    page = browser.new_page(viewport=_LANDSCAPE)
    try:
        response = page.goto(served, wait_until="domcontentloaded")
        assert response is not None
        assert "no-store" in response.header_value("cache-control").lower()
    finally:
        page.close()


def test_a_stale_size_in_the_url_is_corrected_on_load(browser: Browser, served: str) -> None:
    """The bookmark case, which is how a phone actually returns to the game. A URL carrying a size
    chosen for some other shape must not survive the visit."""
    page = _open(browser, served, _LANDSCAPE, query="/?fontsize=8")
    try:
        landscape = page.evaluate(_FONT)
    finally:
        page.close()

    fresh = _open(browser, served, _LANDSCAPE)
    try:
        assert landscape == fresh.evaluate(_FONT), "the stale size in the URL was kept"
    finally:
        fresh.close()


def test_the_size_is_refitted_per_shape_not_per_url(browser: Browser, served: str) -> None:
    """The premise of the correction: the two orientations want different sizes, so a size carried
    between them is wrong by definition."""
    upright = _open(browser, served, _PORTRAIT)
    sideways = _open(browser, served, _LANDSCAPE)
    try:
        assert upright.evaluate(_FONT) != sideways.evaluate(_FONT)
    finally:
        upright.close()
        sideways.close()


def test_the_fit_settles_instead_of_reloading_forever(browser: Browser, served: str) -> None:
    """The reload costs a run, so a disagreement it has already acted on must be left alone. A page
    that reached the terminal at all has stopped navigating."""
    page = _open(browser, served, _LANDSCAPE, query="/?fontsize=28")
    try:
        settled = page.evaluate(_FONT)
        page.wait_for_timeout(2500)
        assert page.evaluate(_FONT) == settled
        assert page.evaluate("!!document.querySelector('.xterm-screen')")
    finally:
        page.close()
