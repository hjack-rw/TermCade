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
import re
from aiohttp import web
from textual_serve.app_service import AppService
from textual_serve.server import Server, to_int

log = logging.getLogger("termcade.session")

TOUCH_ENV = "TERMCADE_TOUCH"

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
        environment.update(self._extra_env)
        return environment


class TermCadeServer(Server):
    """A ``Server`` whose sessions get the engine's meta channel and a per-session environment.

    Subclasses extend :meth:`session_env` to add to what a session is told; the meta channel is the
    same for every session and needs no hook.
    """

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
        return websocket
