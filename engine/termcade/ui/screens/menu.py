"""``MenuScreen`` — the recurring screen shape: a titled panel of action buttons.

Most termcade screens are the same skeleton — a vertical list of buttons inside a bordered
:class:`BoxedPanel` between the Header and Footer — dispatching on the pressed button's id. This
base owns that skeleton so a new screen supplies only the title, the buttons, and what each does.

A screen that needs more than a flat button list (extra layout, art, inputs) subclasses
:class:`EngineScreen` and writes its own ``compose`` instead.
"""

from __future__ import annotations

from dataclasses import dataclass

from textual.app import ComposeResult
from textual.widgets import Button, Footer, Header, Static
from textual.widgets.button import ButtonVariant

from termcade.ui.widgets import BoxedPanel

from .base import EngineScreen


@dataclass(frozen=True)
class MenuItem:
    """One button in a :class:`MenuScreen`.

    ``id`` is the button's full DOM id — it is handed back verbatim to
    :meth:`MenuScreen.on_select`, so encode whatever the handler needs to decode (e.g.
    ``f"slot-{n}"``).
    """

    id: str
    label: str
    disabled: bool = False
    variant: ButtonVariant = "default"
    classes: str = ""


class MenuScreen(EngineScreen):
    # Non-root menus go back on escape; a root menu (no screen beneath it) overrides with `[]`.
    BINDINGS = [("escape", "app.pop_screen", "Back")]

    # Set on the class for a constant title, or in ``__init__`` when it depends on instance state.
    menu_title = ""
    # Optional line shown above the buttons (e.g. "Select a slot"); None omits it.
    menu_description: str | None = None

    def menu_items(self) -> list[MenuItem]:
        raise NotImplementedError

    def on_select(self, item_id: str) -> None:
        raise NotImplementedError

    def compose(self) -> ComposeResult:
        yield Header()
        with BoxedPanel(title=self.menu_title):
            if self.menu_description is not None:
                yield Static(self.menu_description, classes="panel-desc")
            for item in self.menu_items():
                yield Button(
                    item.label,
                    id=item.id,
                    disabled=item.disabled,
                    variant=item.variant,
                    classes=item.classes or None,
                )
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        assert event.button.id is not None
        self.on_select(event.button.id)
