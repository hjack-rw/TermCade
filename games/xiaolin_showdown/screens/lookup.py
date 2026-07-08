"""Look-up — pick a card (from either hand) or a character (you / opponent), then see its detail."""

from __future__ import annotations

from typing import Literal, cast

from textual.app import ComposeResult
from textual.widgets import Button, Footer, Header, Static

from termcade.ui.screens.base import EngineScreen
from termcade.ui.widgets import BoxedPanel

from ..logic.models import Card
from ..logic.state import XiaolinState
from .detail import DetailScreen
from .format import char_stats, display_name, stats_line

Kind = Literal["cards", "characters"]


class LookUpScreen(EngineScreen):
    BINDINGS = [("escape", "app.pop_screen", "Back")]

    def __init__(self, kind: Kind) -> None:
        super().__init__()
        self._kind = kind
        self._cards: list[Card] = []

    def compose(self) -> ComposeResult:
        state = cast(XiaolinState, self.ctx.state)
        yield Header()
        if self._kind == "cards":
            self._cards = state.player.whole_hand + state.bot.whole_hand
            mine = len(state.player.whole_hand)  # first this many are the player's
            with BoxedPanel(title="LOOK UP"):
                yield Static("Choose a card", classes="panel-desc")
                for index, card in enumerate(self._cards):
                    who = "You" if index < mine else "Opp"
                    yield Button(f"{who}: {display_name(card.name)}  ({stats_line(card.stats)})", id=f"look-{index}")
        else:
            with BoxedPanel(title="LOOK UP"):
                yield Static("Choose a character", classes="panel-desc")
                you, opp = state.player.character, state.bot.character
                yield Button(f"You: {display_name(you.name)}  ({char_stats(you)})", id="look-player")
                yield Button(f"Opp: {display_name(opp.name)}  ({char_stats(opp)})", id="look-bot")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        assert event.button.id is not None
        state = cast(XiaolinState, self.ctx.state)
        if self._kind == "cards":
            card = self._cards[int(event.button.id.removeprefix("look-"))]
            self.app.push_screen(DetailScreen(card, is_card=True))
        else:
            character = state.player.character if event.button.id == "look-player" else state.bot.character
            self.app.push_screen(DetailScreen(character, is_card=False))
