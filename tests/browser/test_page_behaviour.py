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

# What the glyph LOOKS like, not how wide it is. Width is not evidence: it only distinguishes our
# font from the fallback when the two happen to advance differently, and on a machine without a
# glyph for `♔` — or with one that happens to be 0.9em, as 0xProto's is — a correctly drawn
# character is indistinguishable from a missing one. That is not hypothetical: this test passed on
# Windows and in the Playwright image and failed on the CI runner, purely on which system fonts were
# installed. Pixels collide only when the same font really did the drawing.
_PIXELS_OF = """(args)=>{
  const draw = (font) => {
    const canvas = document.createElement('canvas');
    canvas.width = 64;
    canvas.height = 64;
    const ctx = canvas.getContext('2d');
    ctx.font = '40px ' + font;
    ctx.textBaseline = 'top';
    ctx.fillText(args.text, 4, 4);
    return canvas.toDataURL();
  };
  return [draw(args.font), draw('TcDefinitelyAbsent')];
}"""


def test_the_terminal_renders_at_all(phone: Page) -> None:
    """The floor. A page that loads its script but never builds a terminal reports no error — it
    just shows nothing, which is what happened when the script was first deferred past onload."""
    assert phone.evaluate("!!document.querySelector('.xterm-screen')")


@pytest.mark.parametrize("glyph", list(_GLYPHS))
def test_every_glyph_the_game_draws_comes_from_our_fonts(phone: Page, glyph: str) -> None:
    """Drawn twice — once with the terminal's stack, once with a family that does not exist — and
    compared as PIXELS. An identical image means the same font drew both, so ours supplied nothing.

    This is the check that would have caught the terminal drawing in Roboto Mono while the page
    cheerfully declared our fonts. It used to compare advance widths, which said the same thing only
    when our font and the device's happened to disagree about width: `♔` and `☯` are 0.9em in
    0xProto, a common enough advance that on the CI runner the fallback matched exactly and a
    correctly drawn glyph reported as missing."""
    ours, absent = phone.evaluate(
        _PIXELS_OF, {"text": glyph, "font": "'Roboto Mono', Monaco, 'Courier New', monospace"}
    )
    assert ours != absent, f"{glyph!r} fell through to the device's own fallback"


def test_ordinary_letters_come_from_the_text_face(phone: Page) -> None:
    """We declare our fonts under the name upstream also uses. If its Google Fonts link survives,
    a real Roboto Mono answers instead and the game's text face changes without a single test
    failing — so this pins the letterforms, not just the symbols."""
    shadowed, absent = phone.evaluate(
        _PIXELS_OF, {"text": "The quick brown fox", "font": "'Roboto Mono'"}
    )
    direct, _ = phone.evaluate(
        _PIXELS_OF, {"text": "The quick brown fox", "font": "'TermCade Mono'"}
    )
    assert shadowed == direct, "the shadowed name is not resolving to 0xProto"
    assert shadowed != absent


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
