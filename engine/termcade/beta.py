"""Closed-beta gate: a passcode at the door, and one save directory per passcode.

Two problems, one mechanism. ``textual-serve`` spawns a fresh subprocess per browser session but
hands every one of them the same environment, so ``paths.app_dir`` resolves to the same directory
for every player and they overwrite each other's saves. The engine has no notion of a player — a
save is keyed by slot alone. Rather than teach the save layer about identity, the passcode a tester
types *becomes* the identity: it is checked at the door, then hashed into a directory name that
only that session's subprocess is told about.

Everything about a session that is *not* the gate — the per-session environment and the meta
channel to the page — lives in :mod:`termcade.session`, so the open server has it too.

The passcode is never interpolated into ``Server.command`` — that string is run through
``create_subprocess_shell``, so a code reaching it would be a shell injection. It travels in the
child's environment only, and only after clearing :data:`_CODE_RE`.

Configured by environment: ``TERMCADE_CODES`` (a file of one passcode per line; absent means no
gate, the pre-beta behaviour) and ``TERMCADE_DATA_DIR`` (the base the per-player directories are
made under, as in Docker).
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
import time
from collections.abc import Awaitable, Callable
from pathlib import Path

from aiohttp import web

from termcade import asset
from termcade.session import DATA_DIR_ENV as DATA_DIR_ENV  # re-exported: beta.DATA_DIR_ENV is public
from termcade.session import TermCadeServer

log = logging.getLogger("termcade.beta")

CODES_ENV = "TERMCADE_CODES"
# Comma-separated passcodes given directly through the environment, for a host with no writable,
# persistent, or uploadable filesystem to point TERMCADE_CODES at — e.g. Back4app Containers,
# which has neither a file-upload API nor a free-tier volume. Loaded once at startup (env vars
# don't change under a running process the way a file can), unlike TERMCADE_CODES's file, which is
# re-read per request specifically so a host that CAN edit a live file gets revoke-without-restart.
CODES_INLINE_ENV = "TERMCADE_CODES_INLINE"
COOKIE = "termcade_beta"

# Bad-guess lockout: enough to blunt a naive brute force against a handful of short codes, not a
# defense against a distributed attacker — this gate was never sized for that threat model.
_MAX_ATTEMPTS = 20
_LOCKOUT_WINDOW = 300.0  # seconds

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


def codes_from_env() -> frozenset[str] | None:
    """Passcodes given via :data:`CODES_INLINE_ENV`, or ``None`` if it is unset — the same shape
    :func:`load_codes` returns, so a caller can use either source interchangeably."""
    raw = os.environ.get(CODES_INLINE_ENV)
    if raw is None:
        return None
    codes = {c.strip() for c in raw.split(",")}
    return frozenset(c for c in codes if c and is_well_formed(c))


def is_well_formed(code: str) -> bool:
    """Whether ``code`` is shaped like a passcode. Checked on the file's contents as well as the
    player's input, so a malformed line in ``codes.txt`` can never become a directory name."""
    return bool(_CODE_RE.match(code))


def _matches(code: str, codes: frozenset[str]) -> bool:
    """Whether ``code`` is one of ``codes`` — every candidate compared, not short-circuited, so a
    guess's timing carries no signal about which valid code it came closest to."""
    return any(hmac.compare_digest(code, valid) for valid in codes)


class _RateLimiter:
    """Sliding-window lockout for repeated bad passcode guesses, keyed by remote address.

    In-memory and per-process: a restart clears it, and it does not share state across workers in a
    multi-process deployment. Sized for blunting a naive brute force against a handful of short
    testers' codes, not a distributed attacker.
    """

    def __init__(self, *, max_attempts: int = _MAX_ATTEMPTS, window: float = _LOCKOUT_WINDOW) -> None:
        self._max_attempts = max_attempts
        self._window = window
        self._attempts: dict[str, list[float]] = {}

    def record_failure(self, key: str) -> None:
        self._recent(key).append(time.monotonic())

    def is_locked(self, key: str) -> bool:
        return len(self._recent(key)) >= self._max_attempts

    def _recent(self, key: str) -> list[float]:
        now = time.monotonic()
        kept = [t for t in self._attempts.get(key, []) if now - t < self._window]
        self._attempts[key] = kept
        return kept


def player_dir(base: Path, code: str) -> Path:
    """The data dir belonging to ``code``, under ``base``.

    The directory is named for a hash rather than the code itself, so a passcode never becomes a
    path a player could read off a filename, and no code shaped legally at the door can still
    surprise the filesystem. Truncated to 16 hex chars: this separates a handful of testers, it does
    not resist an attacker who already has the disk.
    """
    digest = hashlib.sha256(code.encode("utf-8")).hexdigest()[:16]
    return base / _PLAYERS / digest


class BetaServer(TermCadeServer):
    """A ``Server`` that checks a passcode at the door and gives each one its own save directory.

    Exactly one of ``codes_path`` (a file, re-read per request) or ``inline_codes`` (loaded once
    from :data:`CODES_INLINE_ENV`) is expected to carry the valid codes; ``data_dir`` is the base
    the per-player directories are made under.
    """

    def __init__(
        self,
        *args: object,
        codes_path: Path | None = None,
        inline_codes: frozenset[str] | None = None,
        data_dir: Path,
        **kwargs: object,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._codes_path = codes_path
        self._inline_codes = inline_codes
        self._data_dir = data_dir
        self._limiter = _RateLimiter()

    def _current_codes(self) -> frozenset[str]:
        """The valid codes right now — the file re-read fresh (so a host that can edit it gets
        revoke-without-restart), or the inline set fixed at startup, whichever this server has."""
        if self._inline_codes is not None:
            return self._inline_codes
        codes_path = self._codes_path
        if codes_path is not None:
            return load_codes(codes_path)
        return frozenset()

    def authorized_code(self, request: web.Request) -> str | None:
        """The valid passcode carried by ``request``, or ``None``. Re-read per request, so removing
        a line from the codes file locks that tester out of their *next* session."""
        code = request.cookies.get(COOKIE, "")
        if not is_well_formed(code):
            return None
        return code if _matches(code, self._current_codes()) else None

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

        remote = request.remote or "unknown"
        if self._limiter.is_locked(remote):
            return web.Response(
                status=429, text="Too many attempts. Try again later.",
                headers={"Retry-After": str(int(_LOCKOUT_WINDOW))},
            )

        offered = request.query.get("code", "")
        if is_well_formed(offered) and _matches(offered, self._current_codes()):
            # Raised rather than returned: aiohttp deprecated returning an HTTPException, and the
            # cookie set on it survives being raised.
            redirect = web.HTTPFound(request.path)
            redirect.set_cookie(
                COOKIE, offered, httponly=True, samesite="Lax",
                # Either signal saying HTTPS is enough — a proxy that terminates TLS in front of us
                # means our own view of the request scheme is plain http even in production, so
                # public_url alone has to be trusted there; a bare request.scheme check alone would
                # have broken exactly that deployment.
                secure=self.public_url.startswith("https://") or request.scheme == "https",
                max_age=60 * 60 * 24 * 30,
            )
            raise redirect

        if offered:  # a guess was made and it was wrong — just visiting the door is not an attempt
            self._limiter.record_failure(remote)

        if request.path == "/":
            return web.Response(
                text=_login_page(bad=bool(offered)), content_type="text/html", status=401
            )
        return web.Response(status=403, text="Beta access only.")

    def reject(self, request: web.Request) -> bool:
        """The gate covers this; belt and braces on the one route that spawns a subprocess."""
        return self.authorized_code(request) is None

    def session_env(self, request: web.Request) -> dict[str, str]:
        """This session's own save directory, on top of what every session is told."""
        env = super().session_env(request)
        code = self.authorized_code(request)
        if code is not None:
            env[DATA_DIR_ENV] = str(player_dir(self._data_dir, code))
        return env


def _login_page(*, bad: bool) -> str:
    """The door. Deliberately one plain form served inline — it must render before the player is
    allowed to fetch anything from ``/static``, which is also why its styling is in the same file
    rather than a stylesheet the gate would have to let through."""
    message = "That code is not on the list." if bad else "This build is closed beta."
    return asset.read("beta-login.html", message=message, theme=asset.style(asset.THEME))


def codes_path() -> Path | None:
    """The configured passcode file, or ``None`` when the beta gate is switched off."""
    configured = os.environ.get(CODES_ENV)
    return Path(configured) if configured else None
