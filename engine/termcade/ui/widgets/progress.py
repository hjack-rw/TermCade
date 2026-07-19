"""Progress bar — half-block segments and a percent.

The glyphs are the progress-bar pair made for the job: ``▰`` (U+25B0) filled, ``▱`` (U+25B1) empty.
The outlined remainder IS the track, so the bar needs no brackets — and no brackets means no gap to
fight over. The render is a pure function so it can be tested with no TTY; the widget is a thin
``Static`` over it.
"""

from __future__ import annotations

from textual.widgets import Static

_FILL = "▰"
_EMPTY = "▱"


def render_bar(fraction: float, width: int = 10) -> str:
    """``▰ ▰ ▰ ▰ ▰ ▰ ▰ ▱ ▱ ▱  70%`` — ``fraction`` (clamped to 0..1) of ``width`` segments filled.

    A space between segments, so no two glyphs ever touch — glyphs that fill their cell edge-to-edge
    would otherwise merge into one solid strip. Two spaces before the percent, always exactly two:
    the number is NOT right-justified into a slot, which read as a hole at low percentages.
    """
    fraction = max(0.0, min(1.0, fraction))
    filled = round(fraction * width)
    bar = " ".join(_FILL * filled + _EMPTY * (width - filled))
    return f"{bar}  {round(fraction * 100)}%"


class ProgressBar(Static):
    """A bar showing a 0..1 fraction. ``set_progress`` redraws it in place."""

    def __init__(self, fraction: float = 0.0, *, width: int = 10, **kwargs) -> None:
        self._fraction = fraction
        self._width = width
        super().__init__(render_bar(fraction, width), **kwargs)

    def set_progress(self, fraction: float) -> None:
        self._fraction = max(0.0, min(1.0, fraction))
        self.update(render_bar(self._fraction, self._width))
