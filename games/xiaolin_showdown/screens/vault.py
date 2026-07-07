"""Vault screen — the between-duel menu, styled after the reference layout.

Three stacked panels: game state, both hands (element-coloured), and actions. The duel and
card actions arrive with the duel state machine; for now they show greyed and Esc returns.
"""

from __future__ import annotations

from typing import cast

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Footer, Header, Static

from termcade.ui.screens.base import EngineScreen
from termcade.ui.screens.save_slot import SaveSlotScreen
from termcade.ui.widgets import BoxedPanel

from ..logic.mechanics import initiative
from ..logic.models import Player
from ..logic.state import XiaolinState
from .format import affiliation_icon, char_stats, hands_lines


class VaultScreen(EngineScreen):
    BINDINGS = [("s", "save_game", "Save"), ("escape", "app.pop_screen", "Menu")]

    def compose(self) -> ComposeResult:
        state = cast(XiaolinState, self.ctx.state)
        player, bot = state.player, state.bot
        init_player, init_bot = initiative(player, bot)

        yield Header()

        with BoxedPanel(title="STATE OF THE GAME"):
            yield Static(
                f"Points: {player.points}/{bot.points}     Remaining Wu: {len(state.card_deck)}",
                id="points",
                classes="subtitle",
            )
            yield Static(_player_line("Player 1", player, init_player))
            yield Static(_player_line("Player 2", bot, init_bot))

        player_rows, bot_rows = hands_lines(
            player.inalienable_hand + player.hand, bot.inalienable_hand + bot.hand
        )
        with Horizontal(id="hands"):
            yield _hand_panel(player.character.name, player_rows)
            yield _hand_panel(bot.character.name, bot_rows)

        with BoxedPanel(title="ACTIONS"):
            yield Static("1. Gong Yi Tanpai!   (duel — coming soon)", classes="disabled")
            yield Static("S. Save game        Esc. Return to menu")

        yield Footer()

    def action_save_game(self) -> None:
        state = cast(XiaolinState, self.ctx.state)
        title = f"{state.player.character.name} — {state.player.points} pts"
        self.app.push_screen(SaveSlotScreen("save", title=title))


def _player_line(label: str, player: Player, init: int) -> str:
    name = player.character.name.upper().replace("_", " ")
    return (
        f"{label}:  {affiliation_icon(player.character)} {name}  {char_stats(player.character)}"
        f"    Initiative: {init}    Deck: {len(player.deck)}"
    )


def _hand_panel(character_name: str, rows: list[str]) -> BoxedPanel:
    title = f"{character_name.split('_')[0].upper()}'S HAND"
    return BoxedPanel(*[Static(line) for line in rows], title=title)
