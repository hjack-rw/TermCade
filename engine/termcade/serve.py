"""Serve a termcade game to the browser with the bundled full-coverage font embedded.

``textual-serve`` renders the game in xterm.js using a webfont that lacks the Unicode symbols
games draw with, so the browser substitutes colour emoji (wrong width, broken alignment). We
patch textual-serve's page template at runtime — embedding our bundled font as a ``data:`` URI
and putting it first in the terminal's font stack — so every glyph renders consistently with no
host-side install. The xterm.js protocol and static assets are used exactly as shipped.

Configured by environment: ``GAME`` (the console command to run), ``PORT``, and ``PUBLIC_URL``
(the browser-reachable URL — it must not be ``0.0.0.0`` or the websocket cannot connect back).
"""

from __future__ import annotations

import base64
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
_MIN_PX = (660, 560)  # floor: below this even the smallest font can't fit a 140x56 board

# Runs first (synchronously, in <head>): pick the largest xterm font that fits a 140x56 board in this
# window, then reload once with ?fontsize=N so textual-serve renders that size. So the game fits any
# screen at the biggest readable font instead of a fixed size that's too big on laptops or too small
# on monitors. The per-font-px cell ratios (0.60 wide, 1.25 tall) slightly over-estimate the real
# cell so the fit always clears rather than overflowing by a row. Clamped to 8..18px.
_AUTOFIT = (
    "<script>(function(){var p=new URLSearchParams(location.search);"
    "if(!p.has('fontsize')){var a=Math.floor(window.innerWidth/(140*0.60)),"
    "b=Math.floor(window.innerHeight/(56*1.25)),f=Math.max(8,Math.min(a,b,18));"
    "p.set('fontsize',f);location.replace(location.pathname+'?'+p.toString());}})();</script>"
)


def _font_face(family: str, path: Path) -> str:
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"@font-face{{font-family:'{family}';src:url(data:font/ttf;base64,{b64}) format('truetype');}}"


def _templates_dir() -> Path | None:
    """A one-off templates dir holding textual-serve's page with our font embedded, or ``None`` if
    the upstream template can't be patched — then the game serves with the stock font."""
    template = Path(textual_serve.__file__).resolve().parent / "templates" / "app_index.html"
    if not (template.exists() and _FONT.exists()):
        return None
    html = template.read_text(encoding="utf-8")
    if _STOCK_STACK not in html:  # upstream changed shape — don't ship a half-patched page
        return None
    face = f"<style>{_font_face(_FAMILY, _FONT)}</style>"
    # A pure-CSS floor gate: only below _MIN_PX (where even an 8px font can't fit 140x56) does an
    # overlay ask the player to resize. Auto-fit handles every larger window, so this rarely shows.
    gate = (
        f"<style>#tc-toosmall{{position:fixed;inset:0;z-index:99999;display:none;"
        f"background:#000;color:#f2c14e;font-family:monospace;font-size:18px;padding:2rem;"
        f"align-items:center;justify-content:center;text-align:center}}"
        f"@media (max-width:{_MIN_PX[0] - 1}px),(max-height:{_MIN_PX[1] - 1}px)"
        f"{{#tc-toosmall{{display:flex}}}}</style>"
    )
    div = '<div id="tc-toosmall">Window too small &mdash; make it bigger to play.</div>'
    # Best-effort: open at the target size. Browsers block resizeTo on normal tabs (it only takes
    # for script-opened windows), so the CSS gate above is the real guarantee; this just helps where
    # the browser allows it.
    resize = (
        f"<script>window.addEventListener('load',function(){{"
        f"try{{window.resizeTo({_MIN_PX[0]},{_MIN_PX[1]});}}catch(e){{}}}});</script>"
    )
    # The page is a Jinja2 template (aiohttp_jinja2); wrap our snippets in {% raw %} so their CSS/JS
    # braces (e.g. `{#tc-toosmall`, a Jinja comment open) and the base64 aren't parsed as template tags.
    # _AUTOFIT goes first in <head> so it runs and reloads before textual.js reads the font size.
    html = html.replace("</head>", "{% raw %}" + _AUTOFIT + face + gate + "{% endraw %}</head>", 1)
    html = html.replace("</body>", "{% raw %}" + div + resize + "{% endraw %}</body>", 1)
    # Our font leads the stack: xterm.js renders text and the icons it covers from it, and only the
    # few glyphs it lacks fall through to the stock fonts and the browser's system fallback.
    html = html.replace(_STOCK_STACK, f'"{_FAMILY}", {_STOCK_STACK}')
    out = Path(tempfile.mkdtemp(prefix="termcade-serve-"))
    (out / "app_index.html").write_text(html, encoding="utf-8")
    return out


def make_server(*, port: int, public_url: str, game: str, host: str = "0.0.0.0") -> Server:
    """Build the textual-serve ``Server`` with our patched (font-embedded) page when available,
    else the stock page. Shared by ``serve`` (headless, for Docker) and the desktop launcher."""
    templates = _templates_dir()
    if templates is not None:
        return Server(
            game, host=host, port=port, title="TermCade",
            public_url=public_url, templates_path=templates,
        )
    return Server(game, host=host, port=port, title="TermCade", public_url=public_url)


def main() -> None:
    port = int(os.environ.get("PORT", "8000"))
    public_url = os.environ.get("PUBLIC_URL", f"http://localhost:{port}")
    game = os.environ.get("GAME", "xiaolin")
    make_server(port=port, public_url=public_url, game=game).serve()


if __name__ == "__main__":
    main()
