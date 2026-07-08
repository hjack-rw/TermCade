"""Vault screen — the between-duel menu.

Three stacked panels: game state, both hands (element-coloured), and actions. Each panel's
content is a Rich grid that expands to fill the box; secondary labels are dimmed and names
are emphasised, and the whole screen rebuilds on return so deposits and draws show at once.
"""

from __future__ import annotations

from typing import cast

from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Footer, Header, Static

from termcade.ui.screens.base import EngineScreen
from termcade.ui.screens.save_slot import SaveSlotScreen
from termcade.ui.widgets import BoxedPanel

from ..logic.actions import can_deposit, can_draw, draw, usable_powers
from ..logic.mechanics import initiative
from ..logic.models import Player
from ..logic.settings import XiaolinSettings
from ..logic.state import XiaolinState
from .deposit import DepositScreen
from .format import affiliation_icon, char_stats, display_name, hands_lines
from .lookup import LookUpScreen
from .use_power import UsePowerScreen


class VaultScreen(EngineScreen):
    BINDINGS = [
        ("g", "gong_yi_tanpai", "Duel"),
        ("p", "use_power", "Power"),
        ("d", "deposit", "Deposit"),
        ("w", "draw", "Draw"),
        ("c", "lookup_cards", "Cards"),
        ("h", "lookup_characters", "Characters"),
        ("s", "save_game", "Save"),
        ("escape", "app.pop_screen", "Menu"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._suspended = False

    def compose(self) -> ComposeResult:
        state = cast(XiaolinState, self.ctx.state)
        player, bot = state.player, state.bot
        init_player, init_bot = initiative(player, bot)

        yield Header()

        with BoxedPanel(title="STATE OF THE GAME"):
            yield Static(_summary_line(player, bot, state), id="summary")
            yield Static(_state_grid(player, bot, init_player, init_bot), id="state")

        player_rows, bot_rows = hands_lines(player.whole_hand, bot.whole_hand)
        with Horizontal(id="hands"):
            yield _hand_panel(player.character.name, player_rows)
            yield _hand_panel(bot.character.name, bot_rows)

        settings = XiaolinSettings.from_settings(self.ctx.settings.current)
        available = {
            "G": not state.has_ended,
            "P": bool(usable_powers(state, settings.deposit_limit)),
            "D": can_deposit(state, settings.deposit_limit),
            "W": can_draw(state, settings),
        }
        with BoxedPanel(title="ACTIONS"):
            yield Static(_actions_grid(available), id="actions")

        yield Footer()

    # Returning from a sub-screen (deposit / use-power / look-up) rebuilds the panels, so the
    # hands and points always reflect the latest state. Suspend→resume brackets that round trip.
    def on_screen_suspend(self) -> None:
        self._suspended = True

    def on_screen_resume(self) -> None:
        if self._suspended:
            self._suspended = False
            self.refresh(recompose=True)

    def action_gong_yi_tanpai(self) -> None:
        state = cast(XiaolinState, self.ctx.state)
        settings = XiaolinSettings.from_settings(self.ctx.settings.current)
        if state.has_ended or max(state.player.points, state.bot.points) >= settings.point_limit:
            state.has_ended = True  # someone already reached the point limit — end now, no more duels
            from .outcome import OutcomeScreen

            self.app.switch_screen(OutcomeScreen())
            return

        from .duel import DuelScreen  # lazy: DuelScreen returns here, so a top import would cycle

        self.app.switch_screen(DuelScreen())

    def action_draw(self) -> None:
        state = cast(XiaolinState, self.ctx.state)
        settings = XiaolinSettings.from_settings(self.ctx.settings.current)
        if can_draw(state, settings):
            card = draw(state)
            self.app.notify(f"Drew {card.name}.")
            self.refresh(recompose=True)  # show the drawn Wu without leaving the vault

    def action_use_power(self) -> None:
        state = cast(XiaolinState, self.ctx.state)
        settings = XiaolinSettings.from_settings(self.ctx.settings.current)
        if usable_powers(state, settings.deposit_limit):
            self.app.push_screen(UsePowerScreen())

    def action_deposit(self) -> None:
        state = cast(XiaolinState, self.ctx.state)
        settings = XiaolinSettings.from_settings(self.ctx.settings.current)
        if can_deposit(state, settings.deposit_limit):
            self.app.push_screen(DepositScreen())

    def action_lookup_cards(self) -> None:
        self.app.push_screen(LookUpScreen("cards"))

    def action_lookup_characters(self) -> None:
        self.app.push_screen(LookUpScreen("characters"))

    def action_save_game(self) -> None:
        state = cast(XiaolinState, self.ctx.state)
        title = f"{state.player.character.name} — {state.player.points} pts"
        self.app.push_screen(SaveSlotScreen("save", title=title))


# Vault actions, laid out row-major into three columns that fill the panel (see _actions_grid).
_ACTIONS = [
    'G. "Gong Yi Tanpai!"',
    "W. Draw a Card",
    "D. Deposit a Card",
    "P. Use a Power",
    "C. Look up Cards",
    "H. Look up Characters",
    "S. Save game",
    "Esc. Return to menu",
]


def _labelled(label: str, value: str) -> Text:
    """A dimmed label with its value — the muted-label pairing used across the state panel."""
    text = Text()
    text.append(f"{label}: ", style="dim")
    text.append(value)
    return text


def _summary_line(player: Player, bot: Player, state: XiaolinState) -> Text:
    line = Text()  # centred by the #summary `text-align`, not Rich justify (which uses natural width)
    line.append_text(_labelled("Points", f"{player.points}/{bot.points}"))
    line.append("       ")
    line.append_text(_labelled("Remaining Wu", str(len(state.card_deck))))
    return line


def _state_grid(player: Player, bot: Player, init_player: int, init_bot: int) -> Table:
    grid = Table.grid(expand=True, padding=(0, 1))
    grid.add_column(ratio=3, justify="left")  # Player n
    grid.add_column(ratio=6, justify="left")  # affiliation icon + name (stats)
    grid.add_column(ratio=4, justify="left")  # initiative
    grid.add_column(ratio=3, justify="right")  # deck
    for label, duelist, init in (("Player 1", player, init_player), ("Player 2", bot, init_bot)):
        char = duelist.character
        name = Text(f"{affiliation_icon(char)} ")
        name.append(display_name(char.name).upper(), style="bold")
        name.append(f" ({char_stats(char)})", style="dim")  # stats in brackets, next to the name
        grid.add_row(
            Text(f"{label}:", style="dim"),
            name,
            _labelled("Initiative", str(init)),
            _labelled("Deck", str(len(duelist.deck))),
        )
    return grid


def _actions_grid(available: dict[str, bool]) -> Table:
    grid = Table.grid(padding=(0, 4))  # natural width so the panel can centre the whole block
    for _ in range(3):
        grid.add_column(justify="left")
    for start in range(0, len(_ACTIONS), 3):
        cells: list[Text] = [_action_cell(entry, available) for entry in _ACTIONS[start : start + 3]]
        cells += [Text("")] * (3 - len(cells))
        grid.add_row(*cells)
    return grid


def _action_cell(entry: str, available: dict[str, bool]) -> Text:
    key, _, rest = entry.partition(". ")
    cell = Text()
    if available.get(key, True):
        cell.append(f"{key}. ", style="bold")
        cell.append(rest)
    else:
        cell.append(f"{key}. {rest}", style="dim")  # greyed out — you can't take this action now
    return cell


def _hand_panel(character_name: str, rows: list[Text]) -> BoxedPanel:
    title = f"{display_name(character_name).split(' ')[0].upper()}'S HAND"
    # All rows in one Static so the panel centres them as a block (rows stay left-aligned within it).
    return BoxedPanel(Static(Text("\n").join(rows), classes="hand-block"), title=title)
