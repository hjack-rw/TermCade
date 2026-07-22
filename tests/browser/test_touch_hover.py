"""No option is lit on a screen the finger has not touched yet.

This test only exists in the browser suite because the unit harness cannot see the bug. Drive the
same tap through `Pilot` and Textual clears `mouse_over` on `ScreenSuspend`, so the incoming screen
comes up clean and the test passes with the fix reverted. Through a real terminal the hover is
re-established at the last tap position, and the option that lands there arrives wearing the accent
border — the same look a chosen option has. Tapping Play lit Raimundo on the character screen.

Measured in pixels, because xterm.js paints to a canvas: there is no DOM node to ask about its style.
The invariant is that the options are drawn ALIKE, which needs no reference colour and survives a
retheme.
"""

from __future__ import annotations

import io

import pytest

pytest.importorskip("playwright", reason="browser tests need playwright")
pytest.importorskip("PIL", reason="the pixel comparison needs pillow")

from PIL import Image  # noqa: E402
from playwright.sync_api import Page  # noqa: E402

pytestmark = [pytest.mark.browser, pytest.mark.slow]

# The `phone` fixture waits for the terminal element and the fonts, neither of which means the game
# has drawn anything yet. A tap sent into a blank terminal hits nothing, and a test that taps nothing
# passes whatever the code does — this settle is what stops it lying.
_DRAWN = 2500

# The main menu on a landscape phone: the options sit in one column, one terminal row apart.
_MENU_X, _PLAY_Y = 416, 174

# The character screen that Play opens. Its four options land on these rows, and the second shares a
# row with the Play button just tapped.
_OPTION_YS = (138, 174, 210, 246)

# The left border of an option box. Deliberately the border and not the label: every option carries a
# different name in a different element colour, so the label columns differ between rows even when
# nothing is lit. Measured — a lit row reads (57, 40, 137) here against (37, 37, 37) at rest.
_OPTION_X = 293


def _shot(page: Page) -> Image.Image:
    return Image.open(io.BytesIO(page.screenshot())).convert("RGB")


def test_tapping_through_leaves_no_option_lit_on_the_next_screen(phone: Page) -> None:
    phone.wait_for_timeout(_DRAWN)
    menu = _shot(phone)

    phone.touchscreen.tap(_MENU_X, _PLAY_Y)
    phone.wait_for_timeout(2000)
    characters = _shot(phone)

    assert characters.tobytes() != menu.tobytes(), (
        "the tap changed nothing on screen — it never opened the next screen, so this test would "
        "have passed without ever looking at one"
    )

    borders = [characters.getpixel((_OPTION_X, y)) for y in _OPTION_YS]

    assert len(set(borders)) == 1, (
        f"one option is drawn differently from its neighbours: {borders}. "
        "The finger never touched this screen, so nothing on it should look chosen."
    )
