"""Closed-beta gate: a passcode at the door, and one save directory per passcode.

Two problems, one mechanism. ``textual-serve`` spawns a fresh subprocess per browser session but
hands every one of them the same environment, so ``paths.app_dir`` resolves to the same directory
for every player and they overwrite each other's saves. The engine has no notion of a player — a
save is keyed by slot alone. Rather than teach the save layer about identity, the passcode a tester
types *becomes* the identity: it is checked at the door, then hashed into a directory name that
only that session's subprocess is told about.

The passcode is never interpolated into ``Server.command`` — that string is run through
``create_subprocess_shell``, so a code reaching it would be a shell injection. It travels in the
child's environment only, and only after clearing :data:`_CODE_RE`.

Configured by environment: ``TERMCADE_CODES`` (a file of one passcode per line; absent means no
gate, the pre-beta behaviour) and ``TERMCADE_DATA_DIR`` (the base the per-player directories are
made under, as in Docker).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
from collections.abc import Awaitable, Callable
from pathlib import Path

from aiohttp import web
from textual_serve.app_service import AppService
from textual_serve.server import Server, to_int

log = logging.getLogger("termcade.beta")

CODES_ENV = "TERMCADE_CODES"
DATA_DIR_ENV = "TERMCADE_DATA_DIR"
COOKIE = "termcade_beta"

# Passcodes are hashed into filesystem paths and put in a child's environment, so the safe set is
# the one that cannot mean anything anywhere: no dots, no slashes, no shell metacharacters, no
# whitespace. Long enough not to be guessed by hand, short enough to read off a message.
_CODE_RE = re.compile(r"^[A-Za-z0-9-]{4,32}$")

# The subdirectory of the data dir that per-player directories are made under, so a beta host's
# ``/data`` stays legible: codes.txt beside players/, rather than hashes strewn at the top level.
_PLAYERS = "players"


def load_codes(path: Path) -> frozenset[str]:
    """The valid passcodes in ``path``: one per line, ``#`` comments and blanks ignored.

    Read on each check rather than cached, so revoking a tester is editing a file — no restart, no
    admin screen, no second source of truth. A missing file is an empty set (nobody gets in), not an
    error: a typo'd path must not silently open the beta to everyone.
    """
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        log.warning("passcode file %s is unreadable — refusing every code", path)
        return frozenset()
    codes = {line.strip() for line in lines}
    return frozenset(code for code in codes if code and not code.startswith("#") and is_well_formed(code))


def is_well_formed(code: str) -> bool:
    """Whether ``code`` is shaped like a passcode. Checked on the file's contents as well as the
    player's input, so a malformed line in ``codes.txt`` can never become a directory name."""
    return bool(_CODE_RE.match(code))


def player_dir(base: Path, code: str) -> Path:
    """The data dir belonging to ``code``, under ``base``.

    The directory is named for a hash rather than the code itself, so a passcode never becomes a
    path a player could read off a filename, and no code shaped legally at the door can still
    surprise the filesystem. Truncated to 16 hex chars: this separates a handful of testers, it does
    not resist an attacker who already has the disk.
    """
    digest = hashlib.sha256(code.encode("utf-8")).hexdigest()[:16]
    return base / _PLAYERS / digest


class _PlayerAppService(AppService):
    """An ``AppService`` that adds to the child's environment instead of only inheriting ours.

    Upstream's ``_build_environment`` copies ``os.environ`` verbatim, which is exactly why every
    session lands in the same save directory. This is the one hook needed to break that.
    """

    def __init__(self, command: str, *, extra_env: dict[str, str], **kwargs: object) -> None:
        super().__init__(command, **kwargs)  # type: ignore[arg-type]
        self._extra_env = extra_env

    def _build_environment(self, width: int = 80, height: int = 24) -> dict[str, str]:
        environment = super()._build_environment(width=width, height=height)
        environment.update(self._extra_env)
        return environment


class BetaServer(Server):
    """A ``Server`` that checks a passcode at the door and gives each one its own save directory.

    ``codes_path`` is the file of valid passcodes; ``data_dir`` the base the per-player directories
    are made under.
    """

    def __init__(self, *args: object, codes_path: Path, data_dir: Path, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self._codes_path = codes_path
        self._data_dir = data_dir

    def authorized_code(self, request: web.Request) -> str | None:
        """The valid passcode carried by ``request``, or ``None``. Re-read per request, so removing
        a line from the codes file locks that tester out of their *next* session."""
        code = request.cookies.get(COOKIE, "")
        if not is_well_formed(code):
            return None
        return code if code in load_codes(self._codes_path) else None

    async def _make_app(self) -> web.Application:
        app = await super()._make_app()
        app.middlewares.append(self._gate)  # before freeze, so the list is still mutable
        return app

    @web.middleware
    async def _gate(
        self, request: web.Request, handler: Callable[[web.Request], Awaitable[web.StreamResponse]]
    ) -> web.StreamResponse:
        """Refuse everything to a request with no valid passcode.

        A code arriving as ``?code=`` is moved into a cookie and the player redirected, so the
        passcode does not sit in the address bar for the length of the beta — and so the auto-fit's
        own reload cannot carry it around. Both happen before the game session starts; nothing here
        can reload a *running* session out from under a player.
        """
        if self.authorized_code(request) is not None:
            return await handler(request)

        offered = request.query.get("code", "")
        if is_well_formed(offered) and offered in load_codes(self._codes_path):
            # Raised rather than returned: aiohttp deprecated returning an HTTPException, and the
            # cookie set on it survives being raised.
            redirect = web.HTTPFound(request.path)
            redirect.set_cookie(
                COOKIE, offered, httponly=True, samesite="Lax",
                secure=self.public_url.startswith("https://"),
                max_age=60 * 60 * 24 * 30,
            )
            raise redirect

        if request.path == "/":
            return web.Response(
                text=_login_page(bad=bool(offered)), content_type="text/html", status=401
            )
        return web.Response(status=403, text="Beta access only.")

    async def handle_websocket(self, request: web.Request) -> web.WebSocketResponse:
        """As upstream, but the session's subprocess is told its own data directory.

        Mirrors ``textual_serve.server.Server.handle_websocket`` rather than calling it, because
        upstream names ``AppService`` directly and offers no seam for the environment. ``textual
        -serve`` is hard-pinned in ``pyproject.toml`` for this class of patch (``serve.py`` rewrites
        its page template on the same grounds); this must be re-read when that pin moves.
        """
        code = self.authorized_code(request)
        if code is None:  # the gate covers this; belt and braces on the one route that spawns
            return web.WebSocketResponse()

        websocket = web.WebSocketResponse(heartbeat=15)
        width = to_int(request.query.get("width", "80"), 80)
        height = to_int(request.query.get("height", "24"), 24)

        app_service: _PlayerAppService | None = None
        try:
            await websocket.prepare(request)
            app_service = _PlayerAppService(
                self.command,
                extra_env={DATA_DIR_ENV: str(player_dir(self._data_dir, code))},
                write_bytes=websocket.send_bytes,
                write_str=websocket.send_str,
                close=websocket.close,
                download_manager=self.download_manager,
                debug=self.debug,
            )
            await app_service.start(width, height)
            try:
                await self._process_messages(websocket, app_service)
            finally:
                await app_service.stop()
        except asyncio.CancelledError:
            await websocket.close()
        except Exception as error:  # noqa: BLE001 — upstream's own contract: log, close, move on
            log.exception(error)
        finally:
            if app_service is not None:
                await app_service.stop()
        return websocket


def _login_page(*, bad: bool) -> str:
    """The door. Deliberately one plain form served inline: it must render before the player is
    allowed to fetch anything from ``/static``."""
    message = "That code is not on the list." if bad else "This build is closed beta."
    return (
        "<!doctype html><meta charset=utf-8><title>TermCade &mdash; beta</title>"
        "<style>body{background:#000;color:#f2c14e;font-family:monospace;display:flex;"
        "min-height:100vh;margin:0;align-items:center;justify-content:center;text-align:center}"
        "input{background:#111;color:#f2c14e;border:1px solid #f2c14e;font-family:inherit;"
        "font-size:1.2rem;padding:.5rem;text-align:center}"
        "button{background:#f2c14e;color:#000;border:0;font-family:inherit;font-size:1.2rem;"
        "padding:.55rem 1.2rem;margin-left:.5rem;cursor:pointer}</style>"
        "<form method=get action=/><h1>TermCade</h1>"
        f"<p>{message}</p>"
        "<input name=code autofocus autocapitalize=off autocomplete=off spellcheck=false "
        "placeholder=passcode><button type=submit>Enter</button></form>"
    )


def codes_path() -> Path | None:
    """The configured passcode file, or ``None`` when the beta gate is switched off."""
    configured = os.environ.get(CODES_ENV)
    return Path(configured) if configured else None
