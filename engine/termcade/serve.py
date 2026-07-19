"""Serve a termcade game to the browser with the bundled full-coverage font embedded.

``textual-serve`` renders the game in xterm.js using a webfont that lacks the Unicode symbols
games draw with, so the browser substitutes colour emoji (wrong width, broken alignment). We
patch textual-serve's page template at runtime — embedding our bundled font as a ``data:`` URI
and putting it first in the terminal's font stack — so every glyph renders consistently with no
host-side install. The xterm.js protocol and static assets are used exactly as shipped.

Configured by environment: ``GAME`` (the console command to run), ``PORT``, ``PUBLIC_URL``
(the browser-reachable URL — it must not be ``0.0.0.0`` or the websocket cannot connect back), and
``GAME_FACTORY`` (``pkg.module:callable`` returning the game's ``Game``), so the page's auto-fit
reads the cartridge's own sizes instead of a copy of them.
"""

from __future__ import annotations

import base64
import importlib
import os
import tempfile
from pathlib import Path

import textual_serve
from textual_serve.server import Server

# The embedded font gives xterm.js a clean mono text face *and* monochrome glyphs for the card /
# affiliation icons (all text-presentation Unicode symbols). It leads the terminal font stack; any
# glyph it lacks (e.g. the gear) falls through to the browser's own font fallback, which reaches a
# covering system font (Segoe UI Symbol on Windows) — still monochrome, since none of the icons are
# emoji-presentation.
_FONT = Path(__file__).resolve().parent / "assets" / "0xProtoNerdFont-Regular.ttf"
_FAMILY = "TermCade Mono"
_STOCK_STACK = '"Roboto Mono", menlo, monospace'  # textual-serve's terminal font stack

# An xterm cell measures about this much per px of font size. Both slightly over-estimate the real
# cell, so a fit always clears rather than overflowing by a row.
_CELL_W, _CELL_H = 0.60, 1.25
_MIN_FONT, _MAX_FONT = 8, 28  # max font 28

# Fallbacks when no game descriptor is on hand (``serve.main`` under Docker); override via env.
DEFAULT_FIT_SIZE = (110, 38)
# No floor by default: a game whose screens scroll needs no "too small" overlay. Games that really
# cannot reflow pass their own ``min_size``.
DEFAULT_MIN_SIZE: tuple[int, int] | None = None


def _autofit(fit_size: tuple[int, int]) -> str:
    """Runs first, in ``<head>``: pick the largest xterm font that fits ``fit_size`` in this window,
    then reload once with ``?fontsize=N``. Guarded on the param being absent, so it only ever runs
    before the game starts and never fights a size the player zoomed to.
    """
    cols, rows = fit_size
    return (
        "<script>(function(){var p=new URLSearchParams(location.search);"
        f"if(!p.has('fontsize')){{var a=Math.floor(window.innerWidth/({cols}*{_CELL_W})),"
        f"b=Math.floor(window.innerHeight/({rows}*{_CELL_H})),"
        f"f=Math.max({_MIN_FONT},Math.min(a,b,{_MAX_FONT}));"
        "p.set('fontsize',f);location.replace(location.pathname+'?'+p.toString());}})();</script>"
    )


def _min_px(min_size: tuple[int, int]) -> tuple[int, int]:
    """The window below which even the smallest font can't fit the game's floor grid."""
    cols, rows = min_size
    return round(cols * _CELL_W * _MIN_FONT), round(rows * _CELL_H * _MIN_FONT)


def _font_face(family: str, path: Path) -> str:
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"@font-face{{font-family:'{family}';src:url(data:font/ttf;base64,{b64}) format('truetype');}}"


def _too_small_gate(min_size: tuple[int, int]) -> tuple[str, str]:
    """A CSS overlay for a game that cannot reflow below ``min_size``. Empty for one that scrolls."""
    min_w, min_h = _min_px(min_size)
    style = (
        f"<style>#tc-toosmall{{position:fixed;inset:0;z-index:99999;display:none;"
        f"background:#000;color:#f2c14e;font-family:monospace;font-size:18px;padding:2rem;"
        f"align-items:center;justify-content:center;text-align:center}}"
        f"@media (max-width:{min_w - 1}px),(max-height:{min_h - 1}px)"
        f"{{#tc-toosmall{{display:flex}}}}</style>"
    )
    return style, '<div id="tc-toosmall">Window too small &mdash; make it bigger to play.</div>'


def _templates_dir(
    fit_size: tuple[int, int], min_size: tuple[int, int] | None
) -> Path | None:
    """A one-off templates dir holding textual-serve's page with our font embedded, or ``None`` if
    the upstream template can't be patched — then the game serves with the stock font."""
    template = Path(textual_serve.__file__).resolve().parent / "templates" / "app_index.html"
    if not (template.exists() and _FONT.exists()):
        return None
    html = template.read_text(encoding="utf-8")
    if _STOCK_STACK not in html:  # upstream changed shape — don't ship a half-patched page
        return None
    face = f"<style>{_font_face(_FAMILY, _FONT)}</style>"
    gate, div = _too_small_gate(min_size) if min_size is not None else ("", "")
    # The page is a Jinja2 template (aiohttp_jinja2); wrap our snippets in {% raw %} so their CSS/JS
    # braces (e.g. `{#tc-toosmall`, a Jinja comment open) and the base64 aren't parsed as template tags.
    # The auto-fit goes first in <head> so it runs and reloads before textual.js reads the font size.
    html = html.replace(
        "</head>", "{% raw %}" + _autofit(fit_size) + face + gate + "{% endraw %}</head>", 1
    )
    if div:
        html = html.replace("</body>", "{% raw %}" + div + "{% endraw %}</body>", 1)
    # Our font leads the stack: xterm.js renders text and the icons it covers from it, and only the
    # few glyphs it lacks fall through to the stock fonts and the browser's system fallback.
    html = html.replace(_STOCK_STACK, f'"{_FAMILY}", {_STOCK_STACK}')
    out = Path(tempfile.mkdtemp(prefix="termcade-serve-"))
    (out / "app_index.html").write_text(html, encoding="utf-8")
    return out


def make_server(
    *,
    port: int,
    public_url: str,
    game: str,
    host: str = "0.0.0.0",
    fit_size: tuple[int, int] = DEFAULT_FIT_SIZE,
    min_size: tuple[int, int] | None = DEFAULT_MIN_SIZE,
) -> Server:
    """Build the textual-serve ``Server`` with our patched (font-embedded) page when available,
    else the stock page. Shared by ``serve`` (headless, for Docker) and the desktop launcher.

    ``fit_size`` / ``min_size`` come from the game's ``Game`` descriptor. ``min_size=None`` (a game
    whose screens scroll) means no too-small overlay: zooming past the fit is the player's choice.
    """
    templates = _templates_dir(fit_size, min_size)
    if templates is not None:
        return Server(
            game, host=host, port=port, title="TermCade",
            public_url=public_url, templates_path=templates,
        )
    return Server(game, host=host, port=port, title="TermCade", public_url=public_url)


def _descriptor_sizes() -> tuple[tuple[int, int], tuple[int, int] | None]:
    """Read ``fit_size``/``min_size`` off the game named by ``GAME_FACTORY``.

    Without it (or if the import fails) the page falls back to the engine defaults, which is only
    ever a guess — a page sized to one grid while the game lays out for another opens scrolled.
    """
    factory = os.environ.get("GAME_FACTORY")
    if not factory:
        return DEFAULT_FIT_SIZE, DEFAULT_MIN_SIZE
    module_name, _, attr = factory.partition(":")
    game = getattr(importlib.import_module(module_name), attr)()
    return game.fit_size or DEFAULT_FIT_SIZE, game.min_size


def main() -> None:
    port = int(os.environ.get("PORT", "8000"))
    public_url = os.environ.get("PUBLIC_URL", f"http://localhost:{port}")
    game = os.environ.get("GAME", "xiaolin")
    fit_size, min_size = _descriptor_sizes()
    make_server(port=port, public_url=public_url, game=game, fit_size=fit_size, min_size=min_size).serve()


if __name__ == "__main__":
    main()
