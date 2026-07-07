"""Use-a-Power screen — spend a Wu on its power (drawing, or nothing), then back to the vault.

Distinct from Deposit: this fires the Wu's power and discards it for *no* points, where Deposit
banks it for its points. The result (e.g. a draw, or the gag Wu's fizzle) shows as a toast.
"""

from __future__ import annotations

from typing import cast

from textual.app import ComposeResult
from textual.widgets import Button, Footer, Header

from termcade.ui.screens.base import EngineScreen
from termcade.ui.widgets import BoxedPanel

from ..logic.actions import usable_powers, use_power
from ..logic.models import Card
from ..logic.settings import XiaolinSettings
from ..logic.state import XiaolinState
from .format import trigger_label


class UsePowerScreen(EngineScreen):
    BINDINGS = [("escape", "app.pop_screen", "Cancel")]

    def compose(self) -> ComposeResult:
        state = cast(XiaolinState, self.ctx.state)
        deposit_limit = XiaolinSettings.from_settings(self.ctx.settings.current).deposit_limit
        self._usable: list[Card] = usable_powers(state, deposit_limit)

        yield Header()
        with BoxedPanel(title="USE A POWER — CHOOSE A WU"):
            for index, card in enumerate(self._usable):
                yield Button(f"{card.name}   ({trigger_label(card.power)})", id=f"pow-{index}")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        assert event.button.id is not None
        card = self._usable[int(event.button.id.removeprefix("pow-"))]
        message = use_power(cast(XiaolinState, self.ctx.state), card)
        self.app.pop_screen()
        self.app.notify(message)
