"""Deposit screen — cash a chosen hand card for its points, then back to the vault."""

from __future__ import annotations

from typing import cast

from textual.app import ComposeResult
from textual.widgets import Button, Footer, Header

from termcade.ui.screens.base import EngineScreen
from termcade.ui.widgets import BoxedPanel

from ..logic.actions import deposit
from ..logic.state import XiaolinState


class DepositScreen(EngineScreen):
    BINDINGS = [("escape", "app.pop_screen", "Cancel")]

    def compose(self) -> ComposeResult:
        state = cast(XiaolinState, self.ctx.state)
        yield Header()
        with BoxedPanel(title="DEPOSIT — CHOOSE A CARD"):
            for index, card in enumerate(state.player.hand):
                yield Button(f"{card.name}   +{card.points} pts", id=f"dep-{index}")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        assert event.button.id is not None
        state = cast(XiaolinState, self.ctx.state)
        deposit(state, state.player.hand[int(event.button.id.removeprefix("dep-"))])
        self.app.pop_screen()
