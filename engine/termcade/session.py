"""One browser session: the environment its subprocess gets, and the meta channel back to the page.

``textual-serve`` spawns a subprocess per browser session and pipes it to a websocket. Two things
the engine needs are not offered by upstream, and both live on the same seam:

* **What the session knows about itself.** Upstream copies ``os.environ`` verbatim, so every
  session is told the same thing. The beta gate needs to hand each one its own save directory, and
  every session needs to know whether it reached us from a phone.
* **Talking to the page.** The engine puts a Back button and a speaker in the browser, and both are
  driven by the app: ``write_meta`` in the app, out through the subprocess's stdout, forwarded here
  to the websocket, read by the script :mod:`termcade.serve` injects. Upstream drops any meta type
  it does not recognise, which is every one of ours.

``Server.handle_websocket`` is mirrored rather than called because upstream names ``AppService``
directly and offers no seam for either. This is the one place the engine still depends on
upstream's *shape* rather than its behaviour — but it depends on a Python API, so a change breaks
loudly at import or attribute lookup instead of silently at render. ``pyproject.toml`` bounds
``textual-serve`` to 1.x on the strength of that; the page itself no longer needs a hard pin.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import logging
import os
import re
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import cast

from aiohttp import web
from textual_serve.app_service import AppService
from textual_serve.server import Server, to_int

from termcade import asset
from termcade.app.game import Game
from termcade.ui.app import EngineApp
from termcade.web_driver import DRIVER, InProcessWebDriver

try:
    import resource  # POSIX only — absent on Windows dev boxes
except ImportError:
    resource = None  # type: ignore[assignment]

log = logging.getLogger("termcade.session")

TOUCH_ENV = "TERMCADE_TOUCH"
# Defined here rather than in beta.py: session.py cannot import FROM beta.py (beta.py already
# imports TermCadeServer from here), and this in-process path needs the value below.
# beta.py imports it from here instead of keeping its own copy.
DATA_DIR_ENV = "TERMCADE_DATA_DIR"

# Opt-in switch for the in-process session model (InProcessSession, below) over the default
# subprocess-per-session one (TermCadeAppService). Off by default: catalog mutation-safety and a
# concurrent-session blocking-call audit are still open, and those are exactly what turns from
# theoretical into real the moment actual concurrent duels share a process. Once both land, this
# can become the only path rather than an opt-in.
INPROCESS_ENV = "TERMCADE_INPROCESS"

# `GAME_FACTORY`'s own env var name lives in serve.py today (where it is read for page sizing);
# duplicated as a literal there deliberately rather than imported, since serve.py already imports
# FROM session.py and importing back would cycle. resolve_game_factory's signature (spec: str) is
# the actual shared logic; the env var name each caller reads it from is theirs to own.
GAME_FACTORY_ENV = "GAME_FACTORY"


def resolve_game_factory(spec: str) -> Callable[[], Game] | None:
    """``"pkg.module:callable"`` -> the callable, or ``None`` if the spec can't be resolved.

    Shared by serve.py (which only ever calls the result once, to read a game's page-sizing
    descriptor) and InProcessSession (which calls it once per new session, to build that
    session's own Game) — both need the exact same ``pkg.module:attr`` parse, and a factory
    resolved two different ways in two places is a bug waiting for the two to drift.
    """
    module_name, _, attr = spec.partition(":")
    if not attr:
        log.warning("GAME_FACTORY %r is not of the form 'pkg.module:callable'", spec)
        return None
    try:
        factory = getattr(importlib.import_module(module_name), attr)
    except Exception:  # noqa: BLE001 — import or attribute error; either means "can't resolve"
        log.exception("GAME_FACTORY %r could not be imported", spec)
        return None
    if not callable(factory):
        log.warning("GAME_FACTORY %r resolved to a non-callable", spec)
        return None
    return cast("Callable[[], Game]", factory)


def game_factory_from_env() -> Callable[[], Game] | None:
    """The env's ``GAME_FACTORY``, resolved — or ``None`` if unset or unresolvable, which is the
    in-process path's actual prerequisite: without it, :class:`InProcessSession` has nothing to
    build a session's ``Game`` from, and :meth:`TermCadeServer.handle_websocket` falls back to the
    subprocess model regardless of :data:`INPROCESS_ENV`."""
    spec = os.environ.get(GAME_FACTORY_ENV)
    return resolve_game_factory(spec) if spec else None


def _use_inprocess() -> bool:
    """Whether :data:`INPROCESS_ENV` asks for the in-process session model over the default
    subprocess-per-session one. See that constant for why the default is off."""
    return bool(os.environ.get(INPROCESS_ENV))

# Bounds for the client-supplied width/height query params, which flow unchecked into the spawned
# session subprocess's COLUMNS/LINES env vars otherwise — a client could hand it a negative number or
# a value in the millions. Generous enough for any real terminal; narrow enough to stop that.
MIN_TERMINAL_SIZE = 10
MAX_TERMINAL_SIZE = 1000


def _clamp_terminal_size(value: int) -> int:
    return max(MIN_TERMINAL_SIZE, min(value, MAX_TERMINAL_SIZE))

# The most players served at once. Under the default subprocess model (TERMCADE_INPROCESS off),
# each is a full Textual render process, so on a RAM-metered host too many at once trips the OOM
# killer and the box goes down for EVERYONE, with no auto-restart on a free host — one session over
# budget costs every player until someone manually restarts it. Better to turn the next player away
# than lose it for all. Raise TERMCADE_MAX_SESSIONS in the environment to lift the cap with no
# redeploy.
#
# 6 was the original guess and OOM-killed the box in production. A settled subprocess session
# measures ~64 MB (24 MB interpreter/import baseline -> 64 MB after mount, Windows-measured so if
# anything an overestimate of Linux); steady-state isn't the peak, since several players joining at
# once each pay a boot-time import burst on top. Every no-card free host found tops out at 256-512
# MB, tighter than the box 6 already died on — 2 was the number that left real headroom under that
# model. 3 (2026-08-15) trades some of it back: no live host has logged real production RSS under
# the subprocess model to confirm 3 is safe there (~192 MB worst case, and nothing is currently
# deployed to test it against) — the confidence instead comes from the shared-process redesign
# (TERMCADE_INPROCESS, see project memory), whose real Docker-measured cost for 3 concurrent
# sessions is ~40 MB total, comfortably safe if that flag is ever the one actually running. Drop
# back to 2 if the subprocess model stays what's live somewhere and turns out tight.
MAX_SESSIONS_ENV = "TERMCADE_MAX_SESSIONS"
DEFAULT_MAX_SESSIONS = 3

# The page a visitor gets when the arcade is full — a real styled page (see ``web/full.html``), served
# through the same asset reader as the beta door, not a terminal that loads and then cannot connect.
_FULL_PAGE_ASSET = "full.html"


def _max_sessions() -> int:
    """The session cap from the environment, or the default. A garbage value falls back rather than
    crashing the server at boot — a wrong cap must not be worse than no server."""
    try:
        return max(1, int(os.environ.get(MAX_SESSIONS_ENV, DEFAULT_MAX_SESSIONS)))
    except ValueError:
        return DEFAULT_MAX_SESSIONS


# Every meta type the engine sends is namespaced, so forwarding is a prefix test rather than a list
# that has to be kept in step with the app. Anything else is upstream's own business (`exit`,
# `open_url`) and goes to upstream's handler untouched.
_OURS = "termcade_"

# Enough to tell a phone or tablet from a desktop browser. Deliberately crude: the cost of being
# wrong is a Back button that a mouse user did not need, or its absence for someone who can still
# press Escape. Screen *size* cannot answer this — a phone in landscape reports a grid the same
# shape as a laptop's, so the device has to say so itself.
_TOUCH_UA = re.compile(r"Android|iPhone|iPad|iPod|Mobile|Silk|Kindle", re.I)


def is_touch(user_agent: str) -> bool:
    """Whether ``user_agent`` belongs to a device with no keyboard, so its session gets a Back
    button. See :data:`_TOUCH_UA` for why the terminal's own size cannot answer this."""
    return bool(_TOUCH_UA.search(user_agent))


def _log_child_rss(active_at_end: int) -> None:
    """Log the peak RSS the OS has ever recorded for a reaped session subprocess, so
    :data:`DEFAULT_MAX_SESSIONS` can eventually be tuned from real numbers off this box instead of
    the Windows-measured estimate in its comment. POSIX only.

    ``RUSAGE_CHILDREN`` is a running high-water mark across every child reaped since this process
    started, not this one session's own number — that is what capacity planning actually needs: the
    worst single session this box has ever had to hold.
    """
    if resource is None:
        return
    peak_kb = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    log.info("session ended (was %d concurrent); worst child RSS seen so far: %.1f MB", active_at_end, peak_kb / 1024)


class TermCadeAppService(AppService):
    """An ``AppService`` that forwards the engine's own meta packets and can be told extra
    environment for its subprocess."""

    def __init__(self, command: str, *, extra_env: dict[str, str], **kwargs: object) -> None:
        super().__init__(command, **kwargs)  # type: ignore[arg-type]
        self._extra_env = extra_env

    async def on_meta(self, data: bytes) -> None:
        """Forward our own meta packets to the browser; everything else is upstream's business."""
        # Anything that is not a JSON OBJECT is not ours, and must reach upstream unchanged rather
        # than raising: `json.loads(b'[1,2]')` parses fine and returns a list, whose `.get` does not
        # exist. That AttributeError propagates into the websocket loop and takes the whole session
        # down — one malformed frame costing a player their run.
        try:
            payload = json.loads(data)
        except ValueError:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        meta_type = payload.get("type", "")
        if isinstance(meta_type, str) and meta_type.startswith(_OURS):
            await self.remote_write_str(json.dumps([meta_type, payload]))
            return
        await super().on_meta(data)

    def _build_environment(self, width: int = 80, height: int = 24) -> dict[str, str]:
        environment = super()._build_environment(width=width, height=height)
        # Textual chooses its driver by name from the environment, which is the seam that lets the
        # engine fix a resize the stock driver queues without waking the app. See
        # :mod:`termcade.web_driver` for what upstream does and why a phone is where it shows.
        environment["TEXTUAL_DRIVER"] = DRIVER
        environment.update(self._extra_env)
        return environment


class InProcessSession:
    """An ``AppService``-shaped session that hosts an ``EngineApp`` as a task in THIS process,
    instead of spawning a subprocess for it — see :class:`~termcade.web_driver.InProcessWebDriver`
    for what that requires on the driver side.

    Implements only the subset of ``AppService``'s public interface
    ``Server._process_messages`` actually calls (``send_bytes``, ``set_terminal_size``, ``blur``,
    ``focus``) — reusing that dispatch loop unchanged, rather than re-deriving its own copy of the
    same four-way branch on the websocket's JSON envelope.
    """

    def __init__(
        self,
        game_factory: Callable[[], Game],
        *,
        data_dir: Path | None,
        is_touch: bool,
        write_bytes: Callable[[bytes], Awaitable[object]],
    ) -> None:
        self._app = EngineApp(game_factory(), data_dir=data_dir, is_touch=is_touch)
        self._app.driver_class = InProcessWebDriver
        self._write_bytes = write_bytes
        self._run_task: asyncio.Task[None] | None = None
        self._pump_task: asyncio.Task[None] | None = None

    @property
    def _driver(self) -> InProcessWebDriver | None:
        return cast("InProcessWebDriver | None", self._app._driver)

    async def start(self, width: int, height: int) -> None:
        self._run_task = asyncio.create_task(
            self._app.run_async(headless=False, mouse=True, size=(width, height))
        )
        # The driver does not exist until run_async's own startup reaches _get_driver -- give
        # that a moment before handing back control, bounded rather than a fixed sleep so a slow
        # box gets more time and a stuck one fails loudly instead of silently pumping nothing.
        for _ in range(50):
            if self._driver is not None:
                break
            await asyncio.sleep(0.01)
        else:
            raise RuntimeError("EngineApp did not construct its driver within 0.5s of starting")
        self._pump_task = asyncio.create_task(self._driver.pump_output(self._write_bytes))

    async def send_bytes(self, data: bytes) -> bool:
        driver = self._driver
        if driver is None:
            return False
        # _process_messages hands over envelope[1].encode("utf-8") -- undone here rather than
        # changed there, so that upstream-shared dispatch loop stays reusable byte-for-byte
        # instead of forked for this one difference.
        driver.feed_input(data.decode("utf-8"))
        return True

    async def set_terminal_size(self, width: int, height: int) -> None:
        driver = self._driver
        if driver is not None:
            driver.on_meta("resize", {"width": width, "height": height})

    async def blur(self) -> None:
        driver = self._driver
        if driver is not None:
            driver.on_meta("blur", {})

    async def focus(self) -> None:
        driver = self._driver
        if driver is not None:
            driver.on_meta("focus", {})

    async def stop(self) -> None:
        if self._run_task is None:
            return
        self._app.exit()
        try:
            await asyncio.wait_for(self._run_task, timeout=5)
        except Exception:  # noqa: BLE001 — best-effort teardown; a stuck session must not wedge the server
            log.exception("in-process session did not shut down cleanly")
        if self._pump_task is not None:
            try:
                await asyncio.wait_for(self._pump_task, timeout=1)
            except Exception:  # noqa: BLE001 — same: report, do not propagate into the caller's finally
                log.exception("in-process session's output pump did not stop cleanly")


class TermCadeServer(Server):
    """A ``Server`` whose sessions get the engine's meta channel and a per-session environment.

    Subclasses extend :meth:`session_env` to add to what a session is told; the meta channel is the
    same for every session and needs no hook.

    It also caps concurrent sessions (:data:`MAX_SESSIONS_ENV`): each is a full render process, and a
    CPU-metered free host kills the box once too many run at once. Over the cap, a visitor gets the
    "full" page rather than a session, so the overflow costs one player instead of everyone.
    """

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self._active = 0
        self._max_sessions = _max_sessions()
        # Resolved once at boot, not per session: importlib.import_module is a real (if small)
        # cost, and the factory a session gets never varies within one running server anyway.
        self._game_factory = game_factory_from_env()

    async def _make_app(self) -> web.Application:
        """As upstream, plus: the PAGE is never cached.

        The page is not a document, it is the current build of the app — it carries every script the
        engine injects, inline. Cached, a phone keeps running whatever was served the first time it
        visited, and a server restarted with new code changes nothing it can see. That failure is
        invisible from both ends: the server logs a normal request, the browser shows a working game,
        and the only symptom is a fix that "did not work".

        Only the page. ``/static`` is fonts and the terminal bundle, which are large, change with a
        release rather than with an edit, and are exactly what a phone on a slow link should keep.
        """
        app = await super()._make_app()
        app.middlewares.append(self._no_store)
        app.middlewares.append(self._security_headers)
        app.middlewares.append(self._full_gate)
        return app

    @web.middleware
    async def _full_gate(
        self, request: web.Request, handler: Callable[[web.Request], Awaitable[web.StreamResponse]]
    ) -> web.StreamResponse:
        """Serve the "full" page to a new visitor once the cap is reached, so they never load a
        terminal that cannot get a session. Only the page GET is gated — assets and the websocket of
        players already in are left alone."""
        if request.method == "GET" and request.path == "/" and self._active >= self._max_sessions:
            return web.Response(
                text=asset.read(_FULL_PAGE_ASSET, theme=asset.style(asset.THEME)),
                content_type="text/html", status=503, headers={"Retry-After": "120"},
            )
        return await handler(request)

    @staticmethod
    @web.middleware
    async def _no_store(
        request: web.Request, handler: Callable[[web.Request], Awaitable[web.StreamResponse]]
    ) -> web.StreamResponse:
        response = await handler(request)
        if response.content_type == "text/html":
            response.headers["Cache-Control"] = "no-store, must-revalidate"
        return response

    @staticmethod
    @web.middleware
    async def _security_headers(
        request: web.Request, handler: Callable[[web.Request], Awaitable[web.StreamResponse]]
    ) -> web.StreamResponse:
        """Two headers with no functional risk: MIME-sniffing and framing get shut off site-wide.

        A Content-Security-Policy is deliberately NOT set here — the page :mod:`termcade.serve`
        renders carries the engine's own inline script (the meta channel), and upstream's own
        terminal bundle is unverified against any policy; a wrong CSP breaks the game rather than
        hardening it, which is worse than the gap it would close.
        """
        response = await handler(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        return response

    def session_env(self, request: web.Request) -> dict[str, str]:
        """What this session's subprocess is told beyond what it inherits."""
        if is_touch(request.headers.get("User-Agent", "")):
            return {TOUCH_ENV: "1"}
        return {}

    def reject(self, request: web.Request) -> bool:
        """Whether to refuse this session outright. The open server never does; the beta gate does
        for a request carrying no valid passcode."""
        return False

    def _build_session(
        self, request: web.Request, websocket: web.WebSocketResponse
    ) -> TermCadeAppService | InProcessSession:
        """This request's session, in-process or subprocess-backed — see :meth:`handle_websocket`
        for why the caller does not need to know which."""
        env = self.session_env(request)
        if _use_inprocess() and self._game_factory is not None:
            data_dir_str = env.get(DATA_DIR_ENV)
            return InProcessSession(
                self._game_factory,
                data_dir=Path(data_dir_str) if data_dir_str else None,
                is_touch=env.get(TOUCH_ENV) == "1",
                write_bytes=websocket.send_bytes,
            )
        return TermCadeAppService(
            self.command,
            extra_env=env,
            write_bytes=websocket.send_bytes,
            write_str=websocket.send_str,
            close=websocket.close,
            download_manager=self.download_manager,
            debug=self.debug,
        )

    async def handle_websocket(self, request: web.Request) -> web.WebSocketResponse:
        """As upstream, but with our own session and this session's environment.

        Two session shapes, chosen per-request: :class:`TermCadeAppService` (default — a real
        subprocess, one per session) or :class:`InProcessSession` (opt-in via
        :data:`INPROCESS_ENV`, when :attr:`_game_factory` resolved — an ``EngineApp`` task in
        this process instead). Both expose the same four methods :meth:`_process_messages`
        (upstream's own dispatch loop, unchanged) actually calls, so everything below this point
        does not need to know which one it has.
        """
        if self.reject(request):
            return web.WebSocketResponse()
        if self._active >= self._max_sessions:
            # Full. The page gate already turns visitors away; this only trips on a direct websocket
            # hit or a race, so refuse without starting a session. Single-threaded loop, so the
            # check-then-increment below has no await between it and cannot oversubscribe.
            return web.WebSocketResponse()

        self._active += 1
        websocket = web.WebSocketResponse(heartbeat=15)
        width = _clamp_terminal_size(to_int(request.query.get("width", "80"), 80))
        height = _clamp_terminal_size(to_int(request.query.get("height", "24"), 24))

        session: TermCadeAppService | InProcessSession | None = None
        try:
            await websocket.prepare(request)
            session = self._build_session(request, websocket)
            await session.start(width, height)
            try:
                await self._process_messages(websocket, session)  # type: ignore[arg-type]
            finally:
                await session.stop()
        except asyncio.CancelledError:
            await websocket.close()
        except Exception as error:  # noqa: BLE001 — upstream's own contract: log, close, move on
            log.exception(error)
        finally:
            if session is not None:
                await session.stop()
            _log_child_rss(self._active)
            self._active -= 1
        return websocket
