"""``MenuScreen`` — the recurring screen shape: a titled panel of action buttons.

Most termcade screens are the same skeleton — a vertical list of buttons inside a bordered
:class:`BoxedPanel` between the Header and Footer — dispatching on the pressed button's id. This
base owns that skeleton so a new screen supplies only the title, the buttons, and what each does.

A screen that needs more than a flat button list (extra layout, art, inputs) subclasses
:class:`EngineScreen` and writes its own ``compose`` instead.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Footer, Header, Static
from textual.widgets.button import ButtonVariant

from termcade.ui.widgets import BoxedPanel, Button

from .base import EngineScreen


@dataclass(frozen=True)
class MenuItem:
    """One row of a :class:`MenuScreen` — a button, optionally with a small trailing one.

    ``id`` is the button's full DOM id — it is handed back verbatim to
    :meth:`MenuScreen.on_select`, so encode whatever the handler needs to decode (e.g.
    ``f"slot-{n}"``).

    ``action_id`` adds a narrow button beside the main one for a secondary verb on that row (delete,
    rename, …). It dispatches through :meth:`MenuScreen.on_select` like any other button, so the
    handler tells them apart by their id prefix.
    """

    id: str
    # Rich ``Text`` as well as plain: a game names its own nouns in its own colours, and a menu of
    # cards is still a menu. ``Button`` renders either.
    label: str | Text
    disabled: bool = False
    variant: ButtonVariant = "default"
    classes: str = ""
    action_id: str | None = None
    action_label: str = ""
    # Hover text for the row. A label has to stay short enough to read at a glance, so anything a
    # player would want *explained* rather than announced belongs here — a mark on a save that says
    # its rules are not the default ones, say, which is meaningless until you hover it.
    tooltip: str | None = None

    @classmethod
    def indexed(cls, prefix: str, index: int, label: str | Text, **kw: Any) -> MenuItem:
        """A row whose id encodes an integer key — a list index or an entity id — as
        ``id = f"{prefix}-{index}"``. Decode it back with :meth:`MenuScreen.index_of`; the two share
        ``prefix``, so it cannot drift between them."""
        return cls(id=f"{prefix}-{index}", label=label, **kw)


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

    @staticmethod
    def index_of(item_id: str, prefix: str) -> int:
        """The integer key :meth:`MenuItem.indexed` encoded into ``item_id`` under ``prefix``."""
        return int(item_id.removeprefix(f"{prefix}-"))

    def compose(self) -> ComposeResult:
        yield Header()
        with BoxedPanel(title=self.menu_title):
            if self.menu_description is not None:
                yield Static(self.menu_description, classes="panel-desc")
            items = self.menu_items()
            # One item with a trailing button puts every item in a row: a bare button keeps its
            # auto width and would sit short of the others, and the rows' main buttons must line up.
            # Rows only once something needs a trailing button — otherwise every item would reserve
            # an empty column for a button that isn't there.
            rows = any(item.action_id for item in items)
            for item in items:
                button = Button(
                    item.label,
                    id=item.id,
                    disabled=item.disabled,
                    variant=item.variant,
                    classes=item.classes or None,
                )
                if item.tooltip:
                    button.tooltip = item.tooltip
                if not rows:
                    yield button
                elif item.action_id is not None:
                    yield Horizontal(
                        button,
                        Button(item.action_label, id=item.action_id, classes="menu-action"),
                        classes="menu-row",
                    )
                else:
                    # A spacer the size of the trailing button, so this row's main button ends where
                    # the others' do.
                    yield Horizontal(
                        button, Static(classes="menu-action"), classes="menu-row"
                    )
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        assert event.button.id is not None
        # The touch Back button is mounted by `EngineScreen`, not composed as a menu item, but it is
        # still a Button on this screen — and Textual dispatches to every handler in the MRO, so
        # `event.stop()` in the base class does not spare this one. Without the guard a menu reads
        # "tc-back" as one of its own ids: LOOK UP hands it to `index_of`, which has no such item.
        if event.button.id == self.BACK_ID:
            return
        self.on_select(event.button.id)
