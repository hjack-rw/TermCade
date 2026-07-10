"""``TooltipStatic`` — a ``Static`` whose tooltip follows the span under the cursor.

Textual's tooltip is per *widget*, so a panel that packs several facts into one ``Static`` cannot
explain any of them individually. Rich carries arbitrary data on a style, though, and Textual hands
the hovered style to the widget as ``hover_style``. Tag a span with
``Style(meta={"tooltip": "..."})`` and hovering it shows that text; hovering anywhere else clears it.

Mouse only — a keyboard player never sees a tooltip, so never hide anything they *need* behind one.
"""

from __future__ import annotations

from functools import partial

from rich.style import Style
from textual import events
from textual.widgets import Static


class TooltipStatic(Static):
    def watch_hover_style(self, previous_hover_style: Style, hover_style: Style) -> None:
        # The base implementation drives link highlighting; keep it.
        super().watch_hover_style(previous_hover_style, hover_style)
        tooltip = hover_style.meta.get("tooltip")
        if tooltip != self.tooltip:
            self.tooltip = tooltip

    def _on_mouse_move(self, event: events.MouseMove) -> None:
        """Bring the tooltip back after the pointer moves.

        ``Screen._handle_mouse_move`` hides the tooltip on *any* move within the widget it belongs
        to, and only restarts its timer when a *different* widget is hovered. A panel that tooltips
        per span is a single widget, so the pointer never leaves it and the tooltip, once dismissed,
        would never return. Re-arm the same timer Textual would have.

        Watching ``hover_style`` is not enough: moving between two cells that share a style leaves
        the reactive unchanged, so no watcher runs — only the move event fires.
        """
        if self.hover_style.meta.get("tooltip") is None:
            return
        screen = self.screen
        timer = getattr(screen, "_tooltip_timer", None)
        if timer is not None:
            timer.stop()
        screen._tooltip_widget = self
        screen._tooltip_timer = screen.set_timer(
            self.app.TOOLTIP_DELAY,
            partial(screen._handle_tooltip_timer, self),
            name="tooltip-timer",
        )
