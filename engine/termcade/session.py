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
import json
import logging
import os
import re
from collections.abc import Awaitable, Callable

from aiohttp import web
from textual_serve.app_service import AppService
from textual_serve.server import Server, to_int

from termcade import asset
from termcade.web_driver import DRIVER

log = logging.getLogger("termcade.session")

TOUCH_ENV = "TERMCADE_TOUCH"

# The most players served at once. Each is a full Textual render process, so on a CPU-metered host
# too many at once trips the governor and the box is killed for EVERYONE — better to turn the next
# player away than lose it for all. Raise TERMCADE_MAX_SESSIONS in the environment to lift the cap
# with no redeploy. The default is a guess until one player's steady CPU is measured on the box.
MAX_SESSIONS_ENV = "TERMCADE_MAX_SESSIONS"
DEFAULT_MAX_SESSIONS = 6

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

    def session_env(self, request: web.Request) -> dict[str, str]:
        """What this session's subprocess is told beyond what it inherits."""
        if is_touch(request.headers.get("User-Agent", "")):
            return {TOUCH_ENV: "1"}
        return {}

    def reject(self, request: web.Request) -> bool:
        """Whether to refuse this session outright. The open server never does; the beta gate does
        for a request carrying no valid passcode."""
        return False

    async def handle_websocket(self, request: web.Request) -> web.WebSocketResponse:
        """As upstream, but with our own ``AppService`` and this session's environment."""
        if self.reject(request):
            return web.WebSocketResponse()
        if self._active >= self._max_sessions:
            # Full. The page gate already turns visitors away; this only trips on a direct websocket
            # hit or a race, so refuse without starting a session. Single-threaded loop, so the
            # check-then-increment below has no await between it and cannot oversubscribe.
            return web.WebSocketResponse()

        self._active += 1
        websocket = web.WebSocketResponse(heartbeat=15)
        width = to_int(request.query.get("width", "80"), 80)
        height = to_int(request.query.get("height", "24"), 24)

        app_service: TermCadeAppService | None = None
        try:
            await websocket.prepare(request)
            app_service = TermCadeAppService(
                self.command,
                extra_env=self.session_env(request),
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
            self._active -= 1
        return websocket
