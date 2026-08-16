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
        # A hover on a widget that already had a DIFFERENT tooltip showing (any hover after the
        # first on the same TooltipStatic instance, e.g. a second row in the same panel) doesn't
        # update `.tooltip` on the spot: TooltipStatic._on_mouse_move re-arms Textual's own
        # `app.TOOLTIP_DELAY`-second timer rather than setting it synchronously (see that method's
        # docstring, and the precedent at tests/engine/ui/test_screens.py::
        # test_the_tooltip_returns_after_the_pointer_moves, which waits `TOOLTIP_DELAY + 0.15`
        # for exactly this). A first-ever hover doesn't need the timer at all, which is why this
        # flaked only on a test's SECOND hover, and only under the full suite's load: a step of
        # bare `pilot.pause()` costs an unpredictable (often near-zero) slice of real time, so a
        # fixed iteration count is not the same thing as a fixed time budget. Poll with an explicit
        # step so the real elapsed time is what's bounded, not the pump count — this still returns
        # the moment a same-pump update lands (no needless wait on the common, timer-free path),
        # it just can no longer fall short of the one real delay Textual itself imposes.
        step = 0.05
        for _ in range(int((app.TOOLTIP_DELAY + 0.3) / step)):
            await pilot.pause(step)
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
            # A real Textual app under full-suite load has occasional, genuine timing races —
            # some in this project's own widgets, some (confirmed 2026-08-15/16) inside Textual's
            # own library internals, e.g. Header._on_mount's set_title() racing teardown. Neither
            # is fixable by tuning one test, and a single stray flake here must not fail the whole
            # pipeline. Scoped to app-driving tests only: the rules layer is deterministic and a
            # failure there is a real bug, never masked by a retry.
            item.add_marker(pytest.mark.flaky(reruns=2, reruns_delay=1))
