"""Touch input, measured where it is decided: the bytes the page puts on the websocket.

This is the layer that made a fool of the unit tests. `pilot.press(BACK_KEY)` injects straight into
Textual, so it proved the app answers the key — while xterm.js was refusing to encode it and the
button sat there sending nothing. Watching stdin is the only place that story falls apart.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page

from termcade import page as page_assets

pytestmark = [pytest.mark.browser, pytest.mark.slow]

# Wrap the socket before textual.js opens it and keep every stdin frame the page sends.
_TAP = """
(function(){
  window.__stdin = [];
  var W = window.WebSocket;
  window.WebSocket = function(u, p){
    var s = p ? new W(u, p) : new W(u);
    var send = s.send.bind(s);
    s.send = function(d){
      try { var m = JSON.parse(d); if (m && m[0] === 'stdin') window.__stdin.push(m[1]); } catch(_){}
      return send(d);
    };
    return s;
  };
  window.WebSocket.prototype = W.prototype;
})();
"""

_DRAG = """(a)=>{
  const el = document.querySelector('.xterm-screen') || document.body;
  const t = (x, y) => new Touch({identifier: 1, target: el, clientX: x, clientY: y});
  const fire = (type, x, y) => el.dispatchEvent(new TouchEvent(type, {
    bubbles: true, cancelable: true,
    touches: type === 'touchend' ? [] : [t(x, y)],
    changedTouches: [t(x, y)],
  }));
  fire('touchstart', a.x0, a.y0);
  for (let i = 1; i <= 6; i++) {
    fire('touchmove', a.x0 + (a.x1 - a.x0) * i / 6, a.y0 + (a.y1 - a.y0) * i / 6);
  }
  fire('touchend', a.x1, a.y1);
}"""

ARROW_RIGHT, ARROW_LEFT = "\x1b[C", "\x1b[D"


@pytest.fixture
def tapped(browser, served: str):
    """A booted phone page whose outgoing stdin is being recorded."""
    p = browser.new_page(viewport={"width": 844, "height": 390}, is_mobile=True, has_touch=True)
    p.add_init_script(_TAP)
    p.goto(served, wait_until="networkidle")
    p.wait_for_selector(".xterm-screen", timeout=30_000)
    p.wait_for_timeout(1500)
    try:
        yield p
    finally:
        p.close()


def _drag(page: Page, x0: int, y0: int, x1: int, y1: int) -> list[str]:
    page.evaluate("window.__stdin = []")
    page.evaluate(_DRAG, {"x0": x0, "y0": y0, "x1": x1, "y1": y1})
    page.wait_for_timeout(500)
    return page.evaluate("window.__stdin")


def test_swiping_left_turns_the_page_forward(tapped: Page) -> None:
    """The Lore book binds the arrows already; the swipe asks for the same thing the keyboard does,
    and the page follows the finger."""
    assert _drag(tapped, 600, 200, 200, 205) == [ARROW_RIGHT]


def test_swiping_right_turns_the_page_back(tapped: Page) -> None:
    assert _drag(tapped, 200, 200, 600, 205) == [ARROW_LEFT]


def test_dragging_up_scrolls_and_turns_nothing(tapped: Page) -> None:
    """A reader moving down a page must not lose their place to a page turn."""
    sent = _drag(tapped, 400, 300, 405, 120)
    assert sent, "a long vertical drag sent nothing at all"
    assert ARROW_RIGHT not in sent and ARROW_LEFT not in sent


def test_a_scroll_with_a_wandering_thumb_still_turns_nothing(tapped: Page) -> None:
    """The drift a real thumb has, which the 5px drag above is too tidy to produce.

    This failed before the fix and is the reason for it. The swipe gate compared the gesture's
    CUMULATIVE sideways travel against only the vertical travel since the last wheel event, because
    that one is reset on every scroll — so a growing number was measured against a resetting one. A
    200px scroll with 60px of drift read as 60 against about 10 and turned the page, in a browser,
    on the exact path a reader uses to get down the Lore book.
    """
    sent = _drag(tapped, 400, 320, 460, 120)
    assert sent, "the drag scrolled nothing at all"
    assert ARROW_RIGHT not in sent and ARROW_LEFT not in sent, (
        "a mostly-vertical scroll turned the page"
    )


def test_a_tap_that_wobbles_sends_nothing(tapped: Page) -> None:
    """The threshold exists because a wheel becomes an ESC-prefixed sequence, and Textual reads a
    stray ESC as Escape — which on the temple abandons the run."""
    assert _drag(tapped, 400, 300, 404, 303) == []


def test_the_back_button_actually_reaches_the_app(tapped: Page) -> None:
    """The F24 incident, pinned. The app announces `termcade_back` whenever a screen resumes, so a
    successful press produces a NEW announcement; a key xterm refuses to encode produces silence
    while every other test in the suite still passes."""
    tapped.evaluate(
        """() => {
            window.__back = [];
            const wrap = () => {
                if (!window.__tcMeta || !window.__tcMeta['termcade_back']) return false;
                const original = window.__tcMeta['termcade_back'];
                window.__tcMeta['termcade_back'] = (m) => { window.__back.push(m.allowed); return original(m); };
                return true;
            };
            if (!wrap()) { const t = setInterval(() => { if (wrap()) clearInterval(t); }, 50); }
        }"""
    )
    # Into a screen that HAS a way back: three steps down the menu, then select.
    for _ in range(3):
        tapped.press(".xterm-helper-textarea", "ArrowDown")
        tapped.wait_for_timeout(250)
    tapped.press(".xterm-helper-textarea", "Enter")
    tapped.wait_for_timeout(2500)
    assert tapped.evaluate("window.__back.length") > 0, "never reached a screen with a way back"

    before = tapped.evaluate("window.__back.length")
    tapped.click("#tc-back-fab")
    tapped.wait_for_timeout(2500)

    assert tapped.evaluate("window.__back.length") > before, (
        f"the app never answered {page_assets.BACK_KEY} — xterm.js may not encode it"
    )
