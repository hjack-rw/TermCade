"""What the page actually does in a browser — the claims no string assertion can make.

Each of these was verified by hand while the feature was written, then left un-automated. That is
exactly how the Back button shipped dead once: measured, working, and then nothing kept watching.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page

pytestmark = [pytest.mark.browser, pytest.mark.slow]

# One from each face and one from neither, so a regression names itself: `⚙` lives only in the
# symbol subset, `│` only in 0xProto, and the rest are spread across both.
_GLYPHS = "⛸⚙♔☯→—•│─"

_WIDTH_OF = """(args)=>{
  const c = document.createElement('canvas').getContext('2d');
  const w = (t, f) => { c.font = '40px ' + f; return c.measureText(t).width; };
  return [w(args.text, args.font), w(args.text, 'TcDefinitelyAbsent')];
}"""


def test_the_terminal_renders_at_all(phone: Page) -> None:
    """The floor. A page that loads its script but never builds a terminal reports no error — it
    just shows nothing, which is what happened when the script was first deferred past onload."""
    assert phone.evaluate("!!document.querySelector('.xterm-screen')")


@pytest.mark.parametrize("glyph", list(_GLYPHS))
def test_every_glyph_the_game_draws_comes_from_our_fonts(phone: Page, glyph: str) -> None:
    """Measured against a family that does not exist: equal widths mean the browser fell back for
    both, so ours supplied nothing. This is the check that would have caught the terminal drawing
    in Roboto Mono while the page cheerfully declared our fonts."""
    ours, absent = phone.evaluate(
        _WIDTH_OF, {"text": glyph, "font": "'Roboto Mono', Monaco, 'Courier New', monospace"}
    )
    assert abs(ours - absent) > 0.01, f"{glyph!r} fell through to the device's own fallback"


def test_ordinary_letters_come_from_the_text_face(phone: Page) -> None:
    """We declare our fonts under the name upstream also uses. If its Google Fonts link survives,
    a real Roboto Mono answers instead and the game's text face changes without a single test
    failing — so this pins the letterforms, not just the symbols."""
    shadowed, absent = phone.evaluate(
        _WIDTH_OF, {"text": "The quick brown fox 0123456789", "font": "'Roboto Mono'"}
    )
    direct, _ = phone.evaluate(
        _WIDTH_OF, {"text": "The quick brown fox 0123456789", "font": "'TermCade Mono'"}
    )
    assert abs(shadowed - direct) < 0.01, "the shadowed name is not resolving to 0xProto"
    assert abs(shadowed - absent) > 0.01


def test_the_page_asks_nothing_of_the_network_but_us(browser, served: str) -> None:
    """A third-party font request is both a privacy leak and the thing that would out-race our own
    declaration of the same name."""
    page = browser.new_page(viewport={"width": 844, "height": 390})
    external: list[str] = []
    page.on("request", lambda r: external.append(r.url) if served not in r.url else None)
    try:
        page.goto(served, wait_until="networkidle")
        page.wait_for_selector(".xterm-screen", timeout=30_000)
    finally:
        page.close()
    assert not external, f"the page reached outside itself: {external}"


def test_the_bundle_is_served_byte_for_byte(phone: Page, served: str) -> None:
    """The brittleness this whole design removed: nothing may edit textual.js on the way out."""
    body = phone.request.get(f"{served}/static/js/textual.js").body()
    from pathlib import Path

    import textual_serve

    upstream = Path(textual_serve.__file__).resolve().parent / "static" / "js" / "textual.js"
    assert body == upstream.read_bytes()
