"""Render a raster image as terminal cells, no image protocol required.

Each cell is one ``▀`` (U+2580 upper half block): its *foreground* paints the top pixel, its
*background* the bottom one. So a single character carries two vertically-stacked pixels, and a cell
grid ``cols`` wide by ``rows`` tall shows a ``cols`` by ``2*rows`` picture. This lives entirely inside
the cell grid Textual already draws, so it works over xterm.js with no sixel, no addon, no font surgery
- the one thing it leans on is truecolour, which the browser terminal has.

The pixels are treated as square: a cell is about twice as tall as it is wide, and it holds two pixels
stacked, so the two sub-cells come out roughly square. ``resample`` keeps that assumption when it fits
the image to a column budget.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

from PIL import Image
from rich.style import Style
from rich.text import Text

_HALF = "▀"  # ▀ upper half block


def _fit(img: Image.Image, cols: int) -> Image.Image:
    """Scale ``img`` to ``cols`` wide, height chosen to keep square pixels (and even, for the pairing)."""
    w, h = img.size
    rows2 = max(2, round(cols * h / w))
    if rows2 % 2:
        rows2 += 1
    return img.convert("RGBA").resize((cols, rows2), Image.Resampling.LANCZOS)


def render(path: str | Path, cols: int = 40) -> Text:
    """A :class:`rich.text.Text` of ``▀`` cells picturing ``path``, ``cols`` columns wide.

    A fully transparent pixel becomes an unstyled space, so art on a clear background sits on whatever
    is behind it rather than on a black rectangle.
    """
    img = _fit(Image.open(path), cols)
    px = img.load()
    assert px is not None  # a loaded RGBA image always has pixel access; narrows it for the typer
    _, rows2 = img.size
    text = Text(no_wrap=True)
    for y in range(0, rows2, 2):
        for x in range(cols):
            tr, tg, tb, ta = cast("tuple[int, int, int, int]", px[x, y])
            br, bg, bb, ba = cast("tuple[int, int, int, int]", px[x, y + 1])
            if ta == 0 and ba == 0:
                text.append(" ")
                continue
            top = f"#{tr:02x}{tg:02x}{tb:02x}" if ta else None
            bot = f"#{br:02x}{bg:02x}{bb:02x}" if ba else None
            # fg = top pixel, bg = bottom pixel. If only one half is opaque, use a space so the opaque
            # half is the background - a ▀ with a transparent top would punch a hole.
            if top and bot:
                text.append(_HALF, Style(color=top, bgcolor=bot))
            elif top:
                text.append(_HALF, Style(color=top))
            else:
                text.append(" ", Style(bgcolor=bot))
        if y + 2 < rows2:
            text.append("\n")
    return text
