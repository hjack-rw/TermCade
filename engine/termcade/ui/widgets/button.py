"""``Button`` — Textual's button with click-to-focus disabled.

In termcade, focus *is* the keyboard navigation cursor: nothing is focused until the player tabs or
arrows into the options (``EngineScreen.AUTO_FOCUS = ""``), and the focused option wears a
reverse-video highlight. Textual focuses any focusable widget on mouse-down
(``Screen._forward_event`` → ``set_focus``), which would leave that cursor parked on whatever the
mouse last touched — so a click looked like a selection.

Clicking still presses the button; it just no longer moves the cursor.
"""

from __future__ import annotations

from textual.widgets import Button as TextualButton


class Button(TextualButton):
    FOCUS_ON_CLICK = False
