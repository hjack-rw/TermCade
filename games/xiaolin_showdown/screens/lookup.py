"""Look-up — pick a card (from either hand) or a character (you / opponent), then see its detail."""

from __future__ import annotations

from typing import Literal

from termcade.ui.screens.menu import MenuItem

from ..logic.models import Card
from .base import XiaolinMenu
from .detail import DetailScreen
from .format import card_label, char_stats, display_name, stats_line

Kind = Literal["cards", "characters"]


class LookUpScreen(XiaolinMenu):
    menu_title = "LOOK UP"

    def __init__(self, kind: Kind) -> None:
        super().__init__()
        self._kind = kind
        self._cards: list[Card] = []
        self.menu_description = "Choose a card" if kind == "cards" else "Choose a character"

    def menu_items(self) -> list[MenuItem]:
        if self._kind == "characters":
            you, opp = self.state.player.character, self.state.bot.character
            return [
                MenuItem(id="look-player", label=f"You: {display_name(you.name)}  ({char_stats(you)})"),
                MenuItem(id="look-bot", label=f"Opp: {display_name(opp.name)}  ({char_stats(opp)})"),
            ]

        self._cards = self.state.player.whole_hand + self.state.bot.whole_hand
        mine = len(self.state.player.whole_hand)  # the first this many are yours
        return [
            MenuItem.indexed(
                "look",
                index,
                card_label(
                    card,
                    f"  ({stats_line(card.stats)})",
                    prefix=f"{'You' if index < mine else 'Opp'}: ",
                ),
            )
            for index, card in enumerate(self._cards)
        ]

    def on_select(self, item_id: str) -> None:
        if self._kind == "cards":
            self.app.push_screen(
                DetailScreen(self._cards[self.index_of(item_id, "look")], is_card=True)
            )
            return
        player = item_id == "look-player"
        character = self.state.player.character if player else self.state.bot.character
        self.app.push_screen(DetailScreen(character, is_card=False))
