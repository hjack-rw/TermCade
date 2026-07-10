"""``Button`` — Textual's button with click-to-focus disabled and a highlight that wins.

In termcade, focus *is* the keyboard navigation cursor: nothing is focused until the player tabs or
arrows into the options (``EngineScreen.AUTO_FOCUS = ""``), and the focused option wears a
reverse-video highlight. Textual focuses any focusable widget on mouse-down
(``Screen._forward_event`` → ``set_focus``), which would leave that cursor parked on whatever the
mouse last touched — so a click looked like a selection.

Clicking still presses the button; it just no longer moves the cursor.

A label may carry its own colour (a game colouring a Wu name by element). Inline span colours beat
the CSS ``color`` that the ``:hover`` / ``:focus`` rules set, so a highlighted button would keep its
label tinted and the highlight would only half-apply. The spans are dropped at *render* time, which
leaves ``label`` itself untouched — a screen may reassign it whenever it likes, and no snapshot of
it can go stale.
"""

from __future__ import annotations

from textual.app import RenderResult
from textual.content import Content
from textual.widgets import Button as TextualButton


class Button(TextualButton):
    FOCUS_ON_CLICK = False

    def render(self) -> RenderResult:
        label = super().render()
        assert isinstance(label, Content)
        if self.mouse_hover or self.has_focus:
            return Content(label.plain)  # let the CSS highlight take the whole label
        return label
