"""Serve a termcade game to the browser with the bundled full-coverage font embedded.

``textual-serve`` renders the game in xterm.js using a webfont that lacks the Unicode symbols
games draw with, so the browser substitutes colour emoji (wrong width, broken alignment). We
patch textual-serve's page template at runtime — embedding our bundled font as a ``data:`` URI
and putting it first in the terminal's font stack — so every glyph renders consistently with no
host-side install. The xterm.js protocol and static assets are used exactly as shipped.

Configured by environment: ``GAME`` (the console command to run), ``PORT``, ``PUBLIC_URL``
(the browser-reachable URL — it must not be ``0.0.0.0`` or the websocket cannot connect back), and
``GAME_FACTORY`` (``pkg.module:callable`` returning the game's ``Game``), so the page's auto-fit
reads the cartridge's own sizes instead of a copy of them. ``TERMCADE_CODES`` additionally puts the
closed-beta gate in front of everything — see :mod:`termcade.beta`.
"""

from __future__ import annotations

import importlib
import os
import shutil
import tempfile
from pathlib import Path

import textual_serve
from textual_serve.server import Server

from termcade import beta

# The embedded font gives xterm.js a clean mono text face *and* monochrome glyphs for the card /
# affiliation icons (all text-presentation Unicode symbols). It leads the terminal font stack; any
# glyph it lacks (e.g. the gear) falls through to the browser's own font fallback, which reaches a
# covering system font (Segoe UI Symbol on Windows) — still monochrome, since none of the icons are
# emoji-presentation.
_FONT = Path(__file__).resolve().parent / "assets" / "0xProtoNerdFont-Regular.ttf"
_FAMILY = "TermCade Mono"
_STOCK_STACK = '"Roboto Mono", menlo, monospace'  # textual-serve's terminal font stack

# Without this a phone lays the page out for an imaginary ~980px desktop and then scales the result
# down, so the auto-fit sizes the font against a width the device does not have and everything
# arrives shrunk. It goes in *before* the auto-fit script, which reads `window.innerWidth`.
_VIEWPORT = (
    '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
)

# An xterm cell measures about this much per px of font size. These were briefly made pessimistic to
# force the whole grid inside a phone's viewport — and the result was a font nobody could read. A
# player would rather scroll a legible board than squint at one that fits, and the way OUT of a
# screen no longer depends on the fit: it is a page-level button (see `_back_overlay`).
_CELL_W, _CELL_H = 0.60, 1.25
# The floor used to be 8, which is where a phone broke: fitting the game's 44 rows into a landscape
# viewport needs 7px, and clamping back up to 8 made the grid 50px taller than the screen — the page
# loaded overflowing and had to be pinched and scrolled. The floor only ever applies when even
# the smallest fit fails; landscape still resolves to 7, portrait to 5.
_MIN_FONT, _MAX_FONT = 8, 28

# Fallbacks when no game descriptor is on hand (``serve.main`` under Docker); override via env.
DEFAULT_FIT_SIZE = (110, 38)
# No floor by default: a game whose screens scroll needs no "too small" overlay. Games that really
# cannot reflow pass their own ``min_size``.
DEFAULT_MIN_SIZE: tuple[int, int] | None = None


def _autofit(fit_size: tuple[int, int], touch_fit_size: tuple[int, int] | None = None) -> str:
    """Runs first, in ``<head>``: pick the largest xterm font that fits the game's grid in this
    window, then reload once with ``?fontsize=N``. Guarded on the param being absent, so it only ever
    runs before the game starts and never fights a size the player zoomed to.

    A touch device fits a DIFFERENT grid when the cartridge offers one. A phone is short — 312px of
    height against a laptop's 800 — so fitting the desktop's row count means shrinking the font until
    it is unreadable. Asking for fewer rows there gives a legible font instead, and the screens that
    want the space scroll inside their own panel.
    """
    cols, rows = fit_size
    t_cols, t_rows = touch_fit_size or fit_size
    return (
        "<script>(function(){var p=new URLSearchParams(location.search);"
        f"if(!p.has('fontsize')){{var touch=window.matchMedia('(pointer: coarse)').matches;"
        f"var c=touch?{t_cols}:{cols},r=touch?{t_rows}:{rows};"
        f"var a=Math.floor(window.innerWidth/(c*{_CELL_W})),"
        f"b=Math.floor(window.innerHeight/(r*{_CELL_H})),"
        f"f=Math.max({_MIN_FONT},Math.min(a,b,{_MAX_FONT}));"
        "p.set('fontsize',f);location.replace(location.pathname+'?'+p.toString());}})();</script>"
    )


def _centre() -> str:
    """Put the terminal in the middle of the window.

    Upstream's page styles the terminal for opacity and nothing else, so the grid sits at the
    document's top-left against the default body margin. On a desktop the window is usually bigger
    than the grid and the game ends up hugging one corner; on a phone the leftover is a visible
    band down one side. Flexing the body centres it on both axes with no effect on the terminal's
    own size — the auto-fit still decides that.

    ``overflow: auto``, not ``hidden``: a font large enough to read makes the grid taller than a
    phone, and hiding the overflow made the bottom rows unreachable rather than merely off-screen.
    The way out of a screen does not depend on this — that button is fixed to the viewport.

    ``safe`` is load-bearing. Plain centring of something TALLER than the window splits the overflow
    across both edges: a device reported the terminal starting 24px above the top of the screen, so
    the first row and the last were both cut. ``safe`` falls back to start-alignment when it does not
    fit, which loses rows only at the end — and nothing at all once it does fit.
    """
    return (
        "<style>html,body{height:100%;margin:0}"
        "body{display:flex;align-items:safe center;justify-content:safe center;overflow:auto}</style>"
    )


def _back_overlay() -> str:
    """A Back button that belongs to the PAGE, not to the terminal.

    A readable font makes the grid taller than a phone's viewport — that is the player's choice, not
    a bug — so the page scrolls. Anything drawn inside the grid scrolls with it, which is why a
    Textual widget in the corner kept ending up somewhere unreachable. Fixed to the viewport it stays
    under the thumb at any font, zoom or scroll position, and it sends the same Escape the keyboard
    would, so every screen keeps its own meaning for leaving.
    """
    return (
        "<style>#tc-back-fab{position:fixed;right:12px;bottom:12px;z-index:99998;"
        "font-size:15px;padding:10px 16px;border-radius:8px;"
        "cursor:pointer;-webkit-tap-highlight-color:transparent}</style>"
        "<button id='tc-back-fab' type='button' style='display:none'>◀ Back</button>"
        "<script>(function(){var b=document.getElementById('tc-back-fab');"
        "var paint=function(){var t=document.querySelector('.xterm');if(!t)return;"
        "var c=getComputedStyle(t);b.style.background=c.backgroundColor;"
        "b.style.color=c.color;b.style.border='1px solid '+c.color;"
        "b.style.fontFamily=c.fontFamily;};"
        "setTimeout(paint,600);setTimeout(paint,2500);"
        "b.addEventListener('click',function(e){e.preventDefault();"
        "var t=document.querySelector('.xterm-helper-textarea');if(!t)return;t.focus();"
        "['keydown','keyup'].forEach(function(k){t.dispatchEvent(new KeyboardEvent(k,"
        "{key:'Escape',code:'Escape',keyCode:27,which:27,bubbles:true}));});});})();</script>"
    )


def _back_signal() -> str:
    """Listen, in the HEAD, for the app saying whether this screen has a way back.

    Must be installed before ``textual.js`` opens its websocket — wrapping the constructor after the
    socket exists is too late.
    """
    return (
        "<script>(function(){var W=window.WebSocket;"
        "window.WebSocket=function(u,p){var s=p?new W(u,p):new W(u);"
        "s.addEventListener('message',function(e){if(typeof e.data!=='string')return;"
        "var m;try{m=JSON.parse(e.data);}catch(_){return;}"
        "if(m&&m[0]==='termcade_back'){var b=document.getElementById('tc-back-fab');"
        "if(b){b.style.display=m[1].allowed?'':'none';}}});return s;};"
        "window.WebSocket.prototype=W.prototype;})();</script>"
    )


def _no_virtual_keyboard() -> str:
    """Stop a phone throwing its on-screen keyboard up on every tap.

    xterm.js keeps a hidden textarea focused to receive keystrokes, and focusing a textarea is what
    tells a mobile browser to open the keyboard — so every tap on the board covered half the screen
    with keys nobody typed on. ``inputmode="none"`` keeps the focus (and with it paste and IME) while
    telling the browser not to offer the keyboard. Desktop browsers ignore it: they have real keys.

    The textarea is created by xterm.js after this runs, and again whenever the terminal is rebuilt,
    so an observer sets the attribute rather than a one-off query.
    """
    return (
        "<script>(function(){var f=function(){"
        "document.querySelectorAll('.xterm-helper-textarea').forEach(function(t){"
        "if(t.getAttribute('inputmode')!=='none'){t.setAttribute('inputmode','none');}});};"
        "new MutationObserver(f).observe(document.documentElement,{childList:true,subtree:true});"
        "document.addEventListener('DOMContentLoaded',f);f();})();</script>"
    )


def _touch_scroll() -> str:
    """Turn a finger drag into wheel events, so scrollable screens scroll on a phone.

    xterm.js reports mouse buttons and wheels; a touch drag is neither, so the Rules book and the
    Game Log simply would not move. This translates vertical drags into `wheel` events on the
    terminal, which xterm forwards to the app as scrolling. Horizontal drags are left alone.

    The 24px travel threshold is not cosmetic. xterm turns a wheel into an ESC-prefixed sequence,
    and Textual reads a stray ESC as the Escape key — so a tap that wobbled a couple of pixels sent
    Escape, and on the temple that means leaving for the main menu. A gesture has to be a real drag
    before any of this fires.
    """
    return (
        "<script>(function(){var y=null,moved=0;"
        "document.addEventListener('touchstart',function(e){"
        "y=e.touches[0].clientY;moved=0;},{passive:true});"
        "document.addEventListener('touchmove',function(e){"
        "if(y===null)return;var n=e.touches[0].clientY,d=y-n;moved+=Math.abs(d);"
        "if(moved<24||Math.abs(d)<3)return;"
        "var t=document.querySelector('.xterm-screen')||document.body;"
        "t.dispatchEvent(new WheelEvent('wheel',{deltaY:d*2,bubbles:true,cancelable:true}));"
        "y=n;},{passive:true});"
        "document.addEventListener('touchend',function(){y=null;moved=0;},{passive:true});"
        "})();</script>"
    )


def _min_px(min_size: tuple[int, int]) -> tuple[int, int]:
    """The window below which even the smallest font can't fit the game's floor grid."""
    cols, rows = min_size
    return round(cols * _CELL_W * _MIN_FONT), round(rows * _CELL_H * _MIN_FONT)


def _font_face(family: str, path: Path) -> str:
    """Point at the font as a *file*, not a 2.4MB base64 blob inlined in the page.

    Inlined, the whole HTML document carried the font: mobile browsers never finished it, fell back
    to a system face, and the glyphs the game draws with went missing. Served from /static it
    streams, caches, and does not block the page."""
    return (
        f"@font-face{{font-family:'{family}';src:url('/static/{path.name}') format('truetype');"
        "font-display:block;}"
    )


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
    fit_size: tuple[int, int],
    min_size: tuple[int, int] | None,
    touch_fit_size: tuple[int, int] | None = None,
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
        "</head>",
        "{% raw %}"
        + _VIEWPORT
        + _autofit(fit_size, touch_fit_size)
        + _back_signal()
        + _no_virtual_keyboard()
        + _touch_scroll()
        + _centre()
        + face
        + gate
        + "{% endraw %}</head>",
        1,
    )
    html = html.replace(
        "</body>", "{% raw %}" + div + _back_overlay() + "{% endraw %}</body>", 1
    )
    # Our font leads the stack: xterm.js renders text and the icons it covers from it, and only the
    # few glyphs it lacks fall through to the stock fonts and the browser's system fallback.
    html = html.replace(_STOCK_STACK, f'"{_FAMILY}", {_STOCK_STACK}')
    out = Path(tempfile.mkdtemp(prefix="termcade-serve-"))
    (out / "app_index.html").write_text(html, encoding="utf-8")
    return out


def _statics_dir(font: Path) -> Path | None:
    """textual-serve's own static tree, copied, with our font added — so it can be *served*."""
    upstream = Path(textual_serve.__file__).resolve().parent / "static"
    if not (upstream.exists() and font.exists()):
        return None
    out = Path(tempfile.mkdtemp(prefix="termcade-static-"))
    shutil.copytree(upstream, out, dirs_exist_ok=True)
    shutil.copy2(font, out / font.name)
    return out


def make_server(
    *,
    port: int,
    public_url: str,
    game: str,
    host: str = "0.0.0.0",
    fit_size: tuple[int, int] = DEFAULT_FIT_SIZE,
    min_size: tuple[int, int] | None = DEFAULT_MIN_SIZE,
    touch_fit_size: tuple[int, int] | None = None,
) -> Server:
    """Build the textual-serve ``Server`` with our patched (font-embedded) page when available,
    else the stock page. Shared by ``serve`` (headless, for Docker) and the desktop launcher.

    ``fit_size`` / ``min_size`` come from the game's ``Game`` descriptor. ``min_size=None`` (a game
    whose screens scroll) means no too-small overlay: zooming past the fit is the player's choice.

    With ``TERMCADE_CODES`` set this is a :class:`~termcade.beta.BetaServer` instead: a passcode at
    the door and a save directory per code. Without it, the open server as before — a player serving
    the game to their own machine should not have to hold a passcode.
    """
    templates = _templates_dir(fit_size, min_size, touch_fit_size)
    statics = _statics_dir(_FONT)
    kwargs: dict[str, object] = {
        "host": host, "port": port, "title": "TermCade", "public_url": public_url
    }
    if templates is not None:
        kwargs["templates_path"] = templates
    if statics is not None:
        kwargs["statics_path"] = statics

    codes = beta.codes_path()
    if codes is None:
        return Server(game, **kwargs)  # type: ignore[arg-type]
    return beta.BetaServer(game, codes_path=codes, data_dir=_data_dir(), **kwargs)


def _data_dir() -> Path:
    """The base the beta's per-player directories are made under — the same ``TERMCADE_DATA_DIR``
    the game itself reads (``/data`` in the image), so codes.txt and players/ sit side by side."""
    configured = os.environ.get(beta.DATA_DIR_ENV)
    return Path(configured) if configured else Path.cwd()


def _descriptor_sizes() -> tuple[tuple[int, int], tuple[int, int] | None, tuple[int, int] | None]:
    """Read ``fit_size``/``min_size`` off the game named by ``GAME_FACTORY``.

    Without it (or if the import fails) the page falls back to the engine defaults, which is only
    ever a guess — a page sized to one grid while the game lays out for another opens scrolled.
    """
    factory = os.environ.get("GAME_FACTORY")
    if not factory:
        return DEFAULT_FIT_SIZE, DEFAULT_MIN_SIZE, None
    module_name, _, attr = factory.partition(":")
    game = getattr(importlib.import_module(module_name), attr)()
    return game.fit_size or DEFAULT_FIT_SIZE, game.min_size, game.touch_fit_size


def main() -> None:
    port = int(os.environ.get("PORT", "8000"))
    public_url = os.environ.get("PUBLIC_URL", f"http://localhost:{port}")
    game = os.environ.get("GAME", "xiaolin")
    fit_size, min_size, touch_fit = _descriptor_sizes()
    make_server(
        port=port, public_url=public_url, game=game,
        fit_size=fit_size, min_size=min_size, touch_fit_size=touch_fit,
    ).serve()


if __name__ == "__main__":
    main()
