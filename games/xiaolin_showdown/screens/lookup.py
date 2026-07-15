"""Look-up — pick a card (from either hand) or a character (you / opponent), then see its detail."""

from __future__ import annotations

from typing import Literal

from textual.app import ComposeResult
from textual.widgets import Footer, Header, Static

from termcade.ui.widgets import BoxedPanel, Button

from ..logic.models import Card
from .base import XiaolinScreen
from .detail import DetailScreen
from .format import card_label, char_stats, display_name, stats_line

Kind = Literal["cards", "characters"]


class LookUpScreen(XiaolinScreen):
    BINDINGS = [("escape", "app.pop_screen", "Back")]

    def __init__(self, kind: Kind) -> None:
        super().__init__()
        self._kind = kind
        self._cards: list[Card] = []

    def compose(self) -> ComposeResult:
        yield Header()
        if self._kind == "cards":
            self._cards = self.state.player.whole_hand + self.state.bot.whole_hand
            mine = len(self.state.player.whole_hand)  # first this many are the player's
            with BoxedPanel(title="LOOK UP"):
                yield Static("Choose a card", classes="panel-desc")
                for index, card in enumerate(self._cards):
                    who = "You" if index < mine else "Opp"
                    label = card_label(card, f"  ({stats_line(card.stats)})", prefix=f"{who}: ")
                    yield Button(label, id=f"look-{index}")
        else:
            with BoxedPanel(title="LOOK UP"):
                yield Static("Choose a character", classes="panel-desc")
                you, opp = self.state.player.character, self.state.bot.character
                yield Button(f"You: {display_name(you.name)}  ({char_stats(you)})", id="look-player")
                yield Button(f"Opp: {display_name(opp.name)}  ({char_stats(opp)})", id="look-bot")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        assert event.button.id is not None
        if self._kind == "cards":
            card = self._cards[int(event.button.id.removeprefix("look-"))]
            self.app.push_screen(DetailScreen(card, is_card=True))
        else:
            character = self.state.player.character if event.button.id == "look-player" else self.state.bot.character
            self.app.push_screen(DetailScreen(character, is_card=False))
