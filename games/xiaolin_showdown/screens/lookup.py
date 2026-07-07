"""Look-up — pick one card (from your hand) or a character (you / opponent), then see its detail."""

from __future__ import annotations

from typing import Literal, cast

from textual.app import ComposeResult
from textual.widgets import Button, Footer, Header

from termcade.ui.screens.base import EngineScreen
from termcade.ui.widgets import BoxedPanel

from ..logic.models import Card
from ..logic.state import XiaolinState
from .detail import DetailScreen
from .format import stats_line

Kind = Literal["cards", "characters"]


class LookUpScreen(EngineScreen):
    BINDINGS = [("escape", "app.pop_screen", "Back")]

    def __init__(self, kind: Kind) -> None:
        super().__init__()
        self._kind = kind
        self._hand: list[Card] = []

    def compose(self) -> ComposeResult:
        state = cast(XiaolinState, self.ctx.state)
        yield Header()
        if self._kind == "cards":
            self._hand = state.player.inalienable_hand + state.player.hand
            with BoxedPanel(title="LOOK UP — CHOOSE A CARD"):
                for index, card in enumerate(self._hand):
                    yield Button(f"{card.name}   {stats_line(card.stats)}", id=f"look-{index}")
        else:
            with BoxedPanel(title="LOOK UP — CHOOSE A CHARACTER"):
                yield Button(f"You — {state.player.character.name}", id="look-player")
                yield Button(f"Opponent — {state.bot.character.name}", id="look-bot")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        assert event.button.id is not None
        state = cast(XiaolinState, self.ctx.state)
        if self._kind == "cards":
            card = self._hand[int(event.button.id.removeprefix("look-"))]
            self.app.push_screen(DetailScreen(card, is_card=True))
        else:
            character = state.player.character if event.button.id == "look-player" else state.bot.character
            self.app.push_screen(DetailScreen(character, is_card=False))
