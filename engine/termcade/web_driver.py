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

from textual import events
from textual.drivers.web_driver import WebDriver

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
