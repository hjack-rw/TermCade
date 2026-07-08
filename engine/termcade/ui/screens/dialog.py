"""``ChoiceModal`` — a generic list-of-buttons dialog that resolves with the chosen value.

The one modal shape every game needs: raise it with ``push_screen_wait`` inside a worker (or push
it with a callback), and it dismisses with the value behind the pressed button. Typed on that
value, so ``await``-ing it yields the option's type with no cast. The convenience wrappers
``EngineScreen.confirm`` / ``show_message`` / ``choose`` build the common cases for you.
"""

from __future__ import annotations

from typing import TypeVar

from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Button, Static

from termcade.ui.widgets import BoxedPanel

T = TypeVar("T")


class ChoiceModal(ModalScreen[T]):
    """A list of buttons; dismisses with the value behind the chosen one. With ``title`` set, that is
    the border label and ``prompt`` shows inside; otherwise ``prompt`` is the border label itself."""

    # No pre-selected option on open — same rule as EngineScreen, but ModalScreen doesn't inherit it.
    # Must be "" (not None): None makes Textual fall back to the app's "*" and auto-focus the first
    # button; the empty string is what actually leaves the modal un-highlighted until the player tabs.
    AUTO_FOCUS = ""

    def __init__(self, prompt: str, options: list[tuple[str, T]], *, title: str | None = None) -> None:
        super().__init__()
        self._prompt = prompt
        self._options = options
        self._title = title

    def compose(self) -> ComposeResult:
        with BoxedPanel(title=self._title or self._prompt):
            if self._title is not None:
                yield Static(self._prompt, classes="modal-prompt")
            for index, (label, _value) in enumerate(self._options):
                yield Button(label, id=f"opt-{index}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        assert event.button.id is not None
        self.dismiss(self._options[int(event.button.id.removeprefix("opt-"))][1])
