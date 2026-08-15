"""The browser driver, with a resize that reaches the screens instead of stalling one step short.

``App._on_resize`` does not lay the app out. It records the new size and hands the actual work to
``_check_resize`` on a 1/120s timer — and under the web driver that timer does not fire. So the app
takes the new size, agrees with it, and never tells its screens: the layout, and therefore everything
the browser is sent, stays at the size the session started with.

A phone is where it shows. Turning it changes the grid, the page re-fits the terminal and the server
passes the new size down — and the game keeps drawing the old one, cropped to whatever the new screen
can show, until the player touches something. Any event will do it: the first keypress after a
rotation drags the pending resize along with it, and the layout finally catches up. That is why the
same rotation looks fatal on a phone and harmless at a desk, where the mouse never stops moving.

Measured, driving the game's process directly: a resize packet alone produced zero bytes back and
``_check_resize`` was never entered, while ``App._on_resize`` was. The next keypress produced a full
repaint at the new size.

Nothing here reimplements the resize. The size still goes through upstream's own handler; this only
asks, immediately afterwards, for the step whose timer was lost — which is a no-op when the timer did
fire, since ``_check_resize`` clears the pending event it works from.
"""

from __future__ import annotations

import asyncio
from typing import Awaitable, BinaryIO, Callable, Final, TextIO

from textual import events
from textual._xterm_parser import XTermParser
from textual.driver import Driver
from textual.drivers.web_driver import WebDriver
from textual.geometry import Size

# Sentinel telling pump_output no more output is coming, distinct from any real (possibly empty)
# write -- module-level rather than a class attribute, since it is compared by identity, never by
# value, and never needs to vary per instance.
_STOP: Final = object()

# What ``TermCadeAppService`` puts in ``TEXTUAL_DRIVER``. Textual imports its driver by name, which
# is the seam that lets the engine supply this one without patching anything at runtime.
DRIVER = "termcade.web_driver:TermCadeWebDriver"


class TermCadeWebDriver(WebDriver):
    """Upstream's web driver, with the deferred half of a resize actually carried out."""

    def on_meta(self, packet_type: str, payload: dict[str, object]) -> None:
        super().on_meta(packet_type, payload)
        if packet_type != "resize":
            return
        # A message, not a direct call: this runs on the input thread, and the resize upstream just
        # posted has to be processed first — it is what sets the size `_check_resize` then publishes.
        # Queued behind it, so the order is the one the app expects.
        self.send_message(events.Callback(callback=self._app._check_resize))


class InProcessWebDriver(TermCadeWebDriver):
    """A session driver for hosting several :class:`EngineApp` instances in one process.

    ``WebDriver`` writes via ``os.write`` to the process's real stdout fd and reads input from a
    real background thread bound to real stdin — both correct only when a session owns a whole OS
    process to itself. Collapsing several sessions into one process makes both a shared, corrupting
    resource: two drivers writing to the same fd interleave mid-frame, and there is no "this
    session's own stdin" for either to read.

    Both are replaced with explicit, per-instance alternatives instead: output goes into a private
    queue instead of a real fd (drained by :meth:`pump_output`), and input arrives through
    :meth:`feed_input` (rather than a real thread reading a real fd) — called directly from
    whatever already decoded the browser's own websocket message, since there is no
    subprocess-stdin pipe left to frame for. A queue rather than a constructor-supplied callback:
    ``App`` builds its driver itself, as ``self.driver_class(self, debug=..., mouse=..., size=...)``
    (see ``App._get_driver``) — there is no seam there for an extra constructor argument, so the
    queue this instance owns is the only per-session hook available to the session owner.

    ``WebDriver.__init__`` is skipped on purpose: it unconditionally binds ``sys.__stdout__`` /
    ``sys.__stdin__`` and starts that real background thread before this class could redirect
    either. :class:`Driver` (the grandparent) sets up everything this class actually uses.

    Deliberately NOT done here, both already validated safe by the prototype this promotes:
    signal registration (``WebDriver.start_application_mode`` calls
    ``loop.add_signal_handler(SIGINT/SIGTERM, ...)``, which *replaces* — not adds to — the process's
    signal disposition; a shared process needs exactly one such handler, installed once by whatever
    owns the process, not one per session) and starting a real input thread (there is nothing for it
    to read).
    """

    def __init__(self, app: object, **kwargs: object) -> None:
        Driver.__init__(self, app, **kwargs)  # type: ignore[arg-type]
        self._deliveries: dict[str, BinaryIO | TextIO] = {}
        self._parser = XTermParser(debug=self._debug)
        self._out_queue: asyncio.Queue[object] = asyncio.Queue()
        # WebDriver.__init__ (skipped above, on purpose — see the class docstring) assigns
        # self._write a partial(os.write, fd), with no explicit annotation anywhere -- mypy infers
        # THAT as self._write's type for the whole hierarchy, from the static class body, whether
        # or not this class's __init__ actually runs it. Instance attributes are checked
        # invariantly, so no subclass redeclaration can honestly widen it to fit a queue's
        # put_nowait (which correctly returns None, not int) — only literally reproducing
        # partial(..., int) would satisfy mypy, which isn't a real fix, just a decoy return type.
        self._write = self._out_queue.put_nowait  # type: ignore[assignment]

    async def pump_output(self, send: Callable[[bytes], Awaitable[object]]) -> None:
        """Forward every frame this driver writes to ``send``, in the order written, until
        :meth:`stop_application_mode`'s sentinel arrives.

        Bridges this driver's synchronous ``_write`` calls (from ``write()`` / ``write_meta()`` /
        ``write_binary_encoded()``, invoked from many places during a render) to the real,
        asynchronous ``websocket.send_bytes`` — run as its own task by whoever hosts this session,
        for the life of the session.
        """
        while True:
            data = await self._out_queue.get()
            if data is _STOP:
                return
            await send(data)  # type: ignore[arg-type]

    def start_application_mode(self) -> None:
        self._write(b"__GANGLION__\n")
        self.write("\x1b[?1049h")
        self._enable_mouse_support()
        self.write("\x1b[?25l")
        size = Size(80, 24) if self._size is None else Size(*self._size)
        # Posted directly, not through on_meta("resize", ...): that path exists for a resize
        # ARRIVING mid-session, after a layout already exists to be stale against. Nothing has been
        # laid out yet at startup, so there is nothing for the deferred _check_resize fix to catch up.
        self._app.post_message(events.Resize(size, size))
        self._request_terminal_sync_mode_support()
        self._enable_bracketed_paste()

    def disable_input(self) -> None:
        pass

    def stop_application_mode(self) -> None:
        self.write_meta({"type": "exit"})
        # Queued behind the exit frame just written above, not ahead of it: pump_output must send
        # that frame before it sees the sentinel and returns.
        self._out_queue.put_nowait(_STOP)

    def feed_input(self, text: str) -> None:
        """Parse one browser ``["stdin", text]`` envelope's already-decoded text.

        Mirrors ``WebDriver.run_input_thread``'s own parsing (``XTermParser.feed`` then ``.tick()``)
        minus the ``ByteStream`` unframing step upstream needs to demultiplex a real stdin pipe —
        the browser's envelope already hands over plain text, so there is nothing left to unframe.
        Safe to call directly rather than via ``send_message``'s thread-safe wrapper: this runs on
        the app's own event loop already, not a separate input thread.
        """
        for event in self._parser.feed(text):
            self.process_message(event)
        for event in self._parser.tick():
            self.process_message(event)
