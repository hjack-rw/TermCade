"""The touch player's way off a screen.

Every exit in the game is a key, and a phone has no keys — so a served touch session gets a Back
button that presses Escape for it. A terminal gets nothing new: there, Escape already works.
"""

from __future__ import annotations

import pytest

from termcade import session
from termcade.ui.screens.base import TOUCH_ENV


@pytest.fixture
def touch(monkeypatch):
    monkeypatch.setenv(TOUCH_ENV, "1")


@pytest.mark.parametrize(
    "agent",
    [
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15",
        "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Mobile Safari/537.36",
        "Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15",
    ],
)
def test_a_phone_is_recognised(agent: str) -> None:
    assert session.is_touch(agent)


@pytest.mark.parametrize(
    "agent",
    [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15",
        "",
    ],
)
def test_a_desktop_is_not(agent: str) -> None:
    assert not session.is_touch(agent)


def test_the_way_back_is_a_page_button_not_a_widget() -> None:
    """A readable font makes the grid taller than a phone, so the page scrolls — and anything drawn
    inside the grid scrolls away with it. The Back button is fixed to the viewport instead."""
    from termcade import serve

    templates = serve._templates_dir((110, 38), None)
    assert templates is not None
    html = (templates / "app_index.html").read_text(encoding="utf-8")
    assert "tc-back-fab" in html
    assert "position:fixed" in html
    assert "Escape" in html  # it sends the key each screen already answers
