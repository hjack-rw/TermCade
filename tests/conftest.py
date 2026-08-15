"""Fixtures shared by every test: probing the per-span tooltips a ``TooltipStatic`` renders.

Textual's tooltip is per widget, so a panel that explains several facts tags each span with
``Style(meta={"tooltip": ...})``. Reading one back means finding a tagged cell, hovering it, and
asking the widget what it now shows — three steps that every tooltip test would otherwise repeat.
"""

from __future__ import annotations

import os

import pytest

from termcade.core.audio import MUTE_ENV

# Before any app is built: an app test on Windows would otherwise resolve a real player and start
# the theme playing, once per test.
os.environ[MUTE_ENV] = "1"


@pytest.fixture
def hover_tooltip():
    """Hover the first tooltip-tagged cell in ``row`` of ``selector``; return the text it shows.

    Fails when the row carries no tooltip at all, rather than silently reporting ``None`` — an
    untagged span and an empty tooltip are different bugs.
    """

    async def _hover_tooltip(
        app, pilot, selector: str, row: int = 0, *, from_right: bool = False
    ) -> str | None:
        widget = app.screen.query_one(selector)
        region = widget.region
        tagged = [
            x
            for x in range(region.x, region.right)
            if app.screen.get_style_at(x, region.y + row).meta.get("tooltip")
        ]
        assert tagged, f"{selector} row {row} carries no tooltip meta"
        # A row may carry several tagged spans; ``from_right`` reads the rightmost one instead.
        target = tagged[-1] if from_right else tagged[0]
        await pilot.hover(selector, offset=(target - region.x, row))
        # One pause is usually enough, but the hover→tooltip update isn't guaranteed to land within
        # a single pump under load — poll instead of trusting a fixed wait (this is what made the
        # suite flaky under CI: a real update, just not always there after exactly one pause).
        # 10 iterations still wasn't always enough under the full suite's load (CI, 2026-08-15) —
        # each iteration only costs a pump when it isn't the one that finds it, so a bigger ceiling
        # doesn't slow a normal pass, only buys headroom for a genuinely loaded run.
        for _ in range(30):
            await pilot.pause()
            if widget.tooltip is not None:
                break
        return widget.tooltip

    return _hover_tooltip


@pytest.fixture
def tooltips_in():
    """Every distinct tooltip tagged anywhere inside ``selector``."""

    def _tooltips_in(app, selector: str) -> set[str]:
        region = app.screen.query_one(selector).region
        found = {
            app.screen.get_style_at(x, y).meta.get("tooltip")
            for y in range(region.y, region.bottom)
            for x in range(region.x, region.right)
        }
        return found - {None}

    return _tooltips_in


# Anything that drives a real app is `slow`; the rules layer is not. Marked by location rather than
# by hand, so a new app test cannot quietly land in the fast lane and slow it down for everyone.
_APP_TESTS = ("test_flow.py", "test_screens.py", "test_button_highlight.py", "test_saves.py")


def pytest_collection_modifyitems(items):
    for item in items:
        if item.path.name in _APP_TESTS:
            item.add_marker(pytest.mark.slow)
