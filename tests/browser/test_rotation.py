"""Turning the phone. The one gesture whose whole failure mode is that nothing happens.

A rotation is not a small resize. Every other size change on a phone is the browser chrome sliding
in and out by a row; this one swaps the axes, and the layout the game picked for one shape is
unusable in the other. It is also the change the player cannot undo — there is no "drag it back".

The failure this pins had no error and no crash. The page did its part, the server was told the new
size, and the game simply kept drawing the old one until the player pressed a key. Nothing that
tests the page as a string can see that, because every string was correct.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Browser, Page

from xiaolin_showdown.game import build_game

pytestmark = [pytest.mark.browser, pytest.mark.slow]

_PORTRAIT = {"width": 390, "height": 844}
_LANDSCAPE = {"width": 844, "height": 390}

# Count the bytes the app sends AFTER the mark, so the question is "did the game answer the
# rotation", not "did anything ever arrive". Installed before the page's own scripts, because the
# terminal's socket is opened by them.
_SPY = """(() => {
  const Native = window.WebSocket;
  const Spy = function (url, protocols) {
    const socket = protocols ? new Native(url, protocols) : new Native(url);
    window.__marked = false;
    window.__after = 0;
    socket.addEventListener('message', (event) => {
      if (!window.__marked) return;
      const data = event.data;
      window.__after += (data && (data.byteLength || data.length)) || 0;
    });
    // The grid the terminal settled on, taken from what it asks the server for — the page has no
    // other way to see it, since the WebGL renderer leaves no rows in the DOM to count.
    const send = socket.send.bind(socket);
    socket.send = (frame) => {
      if (typeof frame === 'string' && frame.includes('resize')) {
        try { window.__cols = JSON.parse(frame)[1].width; } catch (error) { /* not ours */ }
      }
      return send(frame);
    };
    return socket;
  };
  Spy.prototype = Native.prototype;
  window.WebSocket = Spy;
})()"""


def _rotate(page: Page) -> None:
    """Turn the device, the way a browser reports it: the viewport changes, then the event."""
    page.evaluate("window.__marked = true")
    page.set_viewport_size(_LANDSCAPE)
    page.evaluate("window.dispatchEvent(new Event('orientationchange'))")
    page.wait_for_timeout(5000)  # the page re-fits in kicks over a second; then the app answers


@pytest.fixture
def upright(browser: Browser, served: str):
    """A booted game on a phone held upright, watching what the app sends back."""
    page = browser.new_page(viewport=_PORTRAIT, is_mobile=True, has_touch=True)
    page.add_init_script(_SPY)
    page.goto(served, wait_until="networkidle")
    page.wait_for_selector(".xterm-screen", timeout=30_000)
    page.wait_for_timeout(3000)
    try:
        yield page
    finally:
        page.close()


def test_the_game_redraws_when_the_phone_is_turned(upright: Page) -> None:
    """Untouched, unprompted. The app's own timer for this never fires under the web driver, so
    without the engine's driver the rotation sits in the app unapplied and this reads zero — while
    the very next keypress would produce a full repaint, which is the bug wearing a disguise."""
    _rotate(upright)
    assert upright.evaluate("window.__after") > 0, (
        "the game sent nothing after the rotation: it is still laid out for the old screen"
    )


def test_the_terminal_takes_the_width_the_rotation_gave_it(upright: Page) -> None:
    """The other half: the page has to hand the terminal the new shape in the first place. A grid
    still as narrow as the upright screen means the fit never ran, whatever the app did with it."""
    before = upright.evaluate("document.querySelector('#terminal').clientWidth")
    _rotate(upright)
    after = upright.evaluate("document.querySelector('#terminal').clientWidth")
    assert after > before, f"the terminal stayed {before}px wide on a screen twice that"


def test_the_sideways_grid_is_at_least_what_the_cartridge_asked_for(upright: Page) -> None:
    """At least, not exactly. Capping to exactly the cartridge's column count was tried, and the cap
    could only ever be as good as its guess at a cell — on a 3x screen it asked for 110 columns and
    produced 88, which is under the layout's own breakpoint, so the panels stacked and the state row
    truncated while a third of the display sat black beside them. Spare width costs nothing; being
    short of it costs the layout."""
    _rotate(upright)
    wanted = build_game().touch_fit_size[0]
    assert upright.evaluate("window.__cols") >= wanted
