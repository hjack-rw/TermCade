"""Fixtures shared by every test: probing the per-span tooltips a ``TooltipStatic`` renders.

Textual's tooltip is per widget, so a panel that explains several facts tags each span with
``Style(meta={"tooltip": ...})``. Reading one back means finding a tagged cell, hovering it, and
asking the widget what it now shows — three steps that every tooltip test would otherwise repeat.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def hover_tooltip():
    """Hover the first tooltip-tagged cell in ``row`` of ``selector``; return the text it shows.

    Fails when the row carries no tooltip at all, rather than silently reporting ``None`` — an
    untagged span and an empty tooltip are different bugs.
    """

    async def _hover_tooltip(app, pilot, selector: str, row: int = 0) -> str | None:
        widget = app.screen.query_one(selector)
        region = widget.region
        tagged = [
            x
            for x in range(region.x, region.right)
            if app.screen.get_style_at(x, region.y + row).meta.get("tooltip")
        ]
        assert tagged, f"{selector} row {row} carries no tooltip meta"
        await pilot.hover(selector, offset=(tagged[0] - region.x, row))
        await pilot.pause()
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
