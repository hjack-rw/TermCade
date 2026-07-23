"""Serve a termcade game to the browser with the bundled full-coverage fonts embedded.

``textual-serve`` renders the game in xterm.js using a webfont that lacks the Unicode symbols games
draw with, so the browser substitutes colour emoji (wrong width, broken alignment). We serve our own
fonts from ``/static`` and declare them in the page, so every glyph renders consistently with no
host-side install. The xterm.js protocol and static assets are used exactly as shipped.

**We do not rewrite the bundle.** The terminal's font stack is hardcoded inside ``textual.js``, and
the obvious fix — reaching in and putting our families in front of it — worked but bound the game to
a minified expression that changes shape on any upstream rebuild. Instead we declare our fonts under
the name that stack already asks for (``Roboto Mono``; see ``_shadowed_faces``) and strip the Google
Fonts link that would otherwise answer to it. Nothing is matched inside generated JavaScript: the
only two things read out of upstream are hand-written tags in its HTML template.

Configured by environment: ``GAME`` (the console command to run), ``PORT``, ``PUBLIC_URL``
(the browser-reachable URL — it must not be ``0.0.0.0`` or the websocket cannot connect back), and
``GAME_FACTORY`` (``pkg.module:callable`` returning the game's ``Game``), so the page's auto-fit
reads the cartridge's own sizes instead of a copy of them. ``TERMCADE_CODES`` additionally puts the
closed-beta gate in front of everything — see :mod:`termcade.beta`.
"""

from __future__ import annotations

import atexit
import importlib
import logging
import os
import shutil
import tempfile
from pathlib import Path

import textual_serve
from textual_serve.server import Server

from termcade import beta
from termcade.page import (
    FAMILY,
    GOOGLE_FONTS,
    ICON,
    STOCK_STACK,
    TERMINAL_SCRIPT,
    body,
    deferred_terminal_script,
    faces,
    head,
)
from termcade.session import TermCadeServer

log = logging.getLogger("termcade.serve")

# Fallbacks when no game descriptor is on hand (``serve.main`` under Docker); override via env.
DEFAULT_FIT_SIZE = (110, 38)
# No floor by default: a game whose screens scroll needs no "too small" overlay. Games that really
# cannot reflow pass their own ``min_size``.
DEFAULT_MIN_SIZE: tuple[int, int] | None = None


def _templates_dir(
    fit_size: tuple[int, int],
    min_size: tuple[int, int] | None,
    touch_fit_size: tuple[int, int] | None = None,
) -> Path | None:
    """A one-off templates dir holding textual-serve's page with our font embedded, or ``None`` if
    the upstream template can't be patched — then the game serves with the stock font."""
    template = Path(textual_serve.__file__).resolve().parent / "templates" / "app_index.html"
    if not (template.exists() and all(p.exists() for _, p in faces())):
        return None
    html = template.read_text(encoding="utf-8")
    if GOOGLE_FONTS not in html:  # upstream changed shape — don't ship a half-patched page
        return None
    # Upstream fetches Roboto Mono from Google. It has to go: we declare that same name to mean our
    # own files, and with both declarations live the browser may answer an ordinary letter from
    # either. Removing it also drops a third-party request from a page that otherwise needs none.
    html = html.replace(GOOGLE_FONTS, "", 1)
    # The page is a Jinja2 template (aiohttp_jinja2); wrap our snippets in {% raw %} so their CSS/JS
    # braces (e.g. `{#tc-toosmall`, a Jinja comment open) are not parsed as template tags. The
    # deferred script is deliberately NOT wrapped — its URL is a Jinja expression that must expand.
    html = html.replace(
        "</head>", "{% raw %}" + head(fit_size, min_size, touch_fit_size) + "{% endraw %}</head>", 1
    )
    html = html.replace("</body>", "{% raw %}" + body(min_size) + "{% endraw %}</body>", 1)
    if TERMINAL_SCRIPT in html:
        html = html.replace(TERMINAL_SCRIPT, deferred_terminal_script(), 1)
    else:
        # Not fatal: the terminal still loads on upstream's own terms, it just may build its atlas
        # before the fonts land. Said out loud, because the symptom — a game drawn in the wrong
        # font — looks like a font bug rather than a timing one.
        log.warning(
            "textual-serve's script tag has changed shape — the terminal may be built before the "
            "fonts finish loading, and will draw with whatever was ready at that moment"
        )
    # The intro dialog and Start button, which are the page's own furniture rather than the game.
    # Cosmetic, and allowed to miss: if upstream restyles them the game still renders correctly.
    html = html.replace(STOCK_STACK, f'"{FAMILY}", {STOCK_STACK}')
    out = _scratch("termcade-serve-")
    (out / "app_index.html").write_text(html, encoding="utf-8")
    return out


def _scratch(prefix: str) -> Path:
    """A temp directory that goes away when the process does.

    Both callers hand their directory to the server, which serves out of it for as long as it runs
    — so it cannot be a context manager, and for a real server "until the process exits" is the
    right lifetime anyway. What made it worth fixing is the test suite, which is not one process
    serving one page: ``test_serve.py`` builds a template directory on nearly every test and a full
    copy of upstream's static tree six times over, and none of it was ever removed. Measured at
    roughly 20MB of orphaned temp data per run, left behind on every CI invocation.
    """
    out = Path(tempfile.mkdtemp(prefix=prefix))
    atexit.register(shutil.rmtree, out, ignore_errors=True)
    return out


def _statics_dir(assets: tuple[Path, ...]) -> Path | None:
    """textual-serve's own static tree, copied, with our fonts and icon added — so they can be
    *served* — and its terminal script patched to draw with them."""
    upstream = Path(textual_serve.__file__).resolve().parent / "static"
    if not (upstream.exists() and all(a.exists() for a in assets)):
        return None
    out = _scratch("termcade-static-")
    shutil.copytree(upstream, out, dirs_exist_ok=True)
    for asset in assets:
        shutil.copy2(asset, out / asset.name)
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
    statics = _statics_dir(tuple(p for _, p in faces()) + (ICON,))
    kwargs: dict[str, object] = {
        "host": host, "port": port, "title": "TermCade", "public_url": public_url
    }
    if templates is not None:
        kwargs["templates_path"] = templates
    if statics is not None:
        kwargs["statics_path"] = statics

    codes = beta.codes_path()
    if codes is None:
        return TermCadeServer(game, **kwargs)
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

    The fallback is now real. It was documented and not implemented: a typo in ``GAME_FACTORY``
    raised out of ``main`` and the container died at boot, which is a much worse answer than a
    slightly wrong grid. Logged rather than swallowed, because a guessed size looks like a layout
    bug from the outside and the reason has to be findable.
    """
    factory = os.environ.get("GAME_FACTORY")
    if not factory:
        return DEFAULT_FIT_SIZE, DEFAULT_MIN_SIZE, None
    module_name, _, attr = factory.partition(":")
    try:
        game = getattr(importlib.import_module(module_name), attr)()
    except Exception:  # noqa: BLE001 — import, attribute, or the factory itself; all mean "guess"
        log.exception("GAME_FACTORY %r could not be read — sizing the page from engine defaults",
                      factory)
        return DEFAULT_FIT_SIZE, DEFAULT_MIN_SIZE, None
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
