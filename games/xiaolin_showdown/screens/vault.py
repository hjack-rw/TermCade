"""Vault screen — the between-duel menu.

Three stacked panels: game state, both hands (element-coloured), and actions. Each panel's
content is a Rich grid that expands to fill the box; secondary labels are dimmed and names
are emphasised, and the whole screen rebuilds on return so deposits and draws show at once.
"""

from __future__ import annotations

from typing import cast

from rich.style import Style
from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Footer, Header, Static

from termcade.ui.screens.base import EngineScreen
from termcade.ui.screens.log import GameLogScreen
from termcade.ui.screens.save_slot import SaveSlotScreen
from termcade.ui.widgets import BoxedPanel, TooltipStatic

from ..logic.actions import (
    can_deposit,
    can_draw,
    can_early_bird,
    deposit_blocked,
    draw,
    draw_blocked,
    usable_powers,
    use_power_blocked,
)
from ..logic.mechanics.scoring import initiative, initiative_sources
from ..logic.models import Player
from ..logic.turn import DRAW
from ..logic.settings import XiaolinSettings
from ..logic.state import XiaolinState
from .deposit import DepositScreen
from .format import (
    affiliation_icon,
    bonus_tooltip,
    char_stats,
    display_name,
    hands_lines,
    your_move,
)
from .lookup import LookUpScreen
from .rules import RulesScreen
from .use_power import UsePowerScreen


class VaultScreen(EngineScreen):
    BINDINGS = [
        ("1", "gong_yi_tanpai", "Duel"),
        ("2", "draw", "Draw"),
        ("3", "deposit", "Deposit"),
        ("4", "use_power", "Power"),
        ("5", "lookup_cards", "Cards"),
        ("6", "lookup_characters", "Characters"),
        ("7", "game_log", "Log"),
        ("8", "rules", "Rules"),
        ("9", "save_game", "Save"),
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
            yield TooltipStatic(_state_grid(player, bot, init_player, init_bot), id="state")

        player_rows, bot_rows = hands_lines(player.whole_hand, bot.whole_hand)
        with Horizontal(id="hands"):
            yield _hand_panel(player.character.name, player_rows)
            yield _hand_panel(bot.character.name, bot_rows)

        settings = XiaolinSettings.from_settings(self.ctx.settings.current)
        # Keyed by the shown number, so the greying and the hover reason come from the same source.
        blocked: dict[str, str | None] = {
            "1": "The run is over." if state.has_ended else None,
            "2": draw_blocked(state, settings),
            "3": deposit_blocked(state, settings.actions_per_turn),
            # The Early Bird is a power like any other, so it opens this screen on its own — a
            # duelist fast enough to fly it has something to spend, even holding no Wu that acts.
            "4": (
                None
                if can_early_bird(state, settings)
                else use_power_blocked(state, settings.actions_per_turn)
            ),
        }
        with BoxedPanel(title="ACTIONS"):
            yield TooltipStatic(_actions_grid(blocked), id="actions")

        yield Footer()

    # Returning from a sub-screen (deposit / use-power / look-up) rebuilds the panels, so the
    # hands and points always reflect the latest state. Suspend→resume brackets that round trip.
    def on_screen_suspend(self) -> None:
        self._suspended = True

    def on_screen_resume(self) -> None:
        if self._suspended:
            self._suspended = False
            self.rebuild()

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
            self.app.notify(f"Drew {card.name}.", title=your_move(DRAW))
            self.rebuild()  # show the drawn Wu without leaving the vault

    def action_use_power(self) -> None:
        state = cast(XiaolinState, self.ctx.state)
        settings = XiaolinSettings.from_settings(self.ctx.settings.current)
        if usable_powers(state, settings.actions_per_turn) or can_early_bird(state, settings):
            self.app.push_screen(UsePowerScreen())

    def action_deposit(self) -> None:
        state = cast(XiaolinState, self.ctx.state)
        settings = XiaolinSettings.from_settings(self.ctx.settings.current)
        if can_deposit(state, settings.actions_per_turn):
            self.app.push_screen(DepositScreen())

    def action_lookup_cards(self) -> None:
        self.app.push_screen(LookUpScreen("cards"))

    def action_lookup_characters(self) -> None:
        self.app.push_screen(LookUpScreen("characters"))

    def action_game_log(self) -> None:
        self.app.push_screen(GameLogScreen())

    def action_rules(self) -> None:
        self.app.push_screen(RulesScreen())

    def action_save_game(self) -> None:
        state = cast(XiaolinState, self.ctx.state)
        title = f"{state.player.character.name} —  {state.player.points} pts"
        self.app.push_screen(SaveSlotScreen("save", title=title))


# Vault actions, laid out row-major into three columns that fill the panel (see _actions_grid).
_ACTIONS = [
    '1. "Gong Yi Tanpai!"',
    "2. Draw a Card",
    "3. Deposit a Card",
    "4. Use a Power",
    "5. Look up Cards",
    "6. Look up Characters",
    "7. Game Log",
    "8. Rules",
    "9. Save game",
    # Escape is NOT listed. It is on the footer, where every screen's escape is, and a panel of things
    # to *do* in the vault is not where "leave the vault" belongs. Nine actions fill the three columns
    # exactly; a tenth entry left one hanging alone on a fourth row.
]

# Hover text for an action that *is* available; a blocked one shows why instead (see _action_cell).
_ACTION_HELP = {
    "1": "Duel for the next Wu on the pile.",
    "2": "Take a Wu from your personal deck.",
    "3": "Cash a Wu from your hand for points.",
    "4": "Spend a Wu for its power.",
    "5": "Inspect any Wu in either hand.",
    "6": "Inspect either duelist.",
    "7": "Everything that has happened so far.",
    "8": "Rulebook for the game.",
    "9": "Save this run to a slot.",
}


def _labelled(label: str, value: str | Text) -> Text:
    """A dimmed label with its value — the muted-label pairing used across the state panel."""
    text = Text()
    text.append(f"{label}: ", style="dim")
    if isinstance(value, Text):
        text.append_text(value)
    else:
        text.append(value)
    return text


def _summary_line(player: Player, bot: Player, state: XiaolinState) -> Text:
    line = Text()  # centred by the #summary `text-align`, not Rich justify (which uses natural width)
    line.append_text(_labelled("Points", f"{player.points}/{bot.points}"))
    line.append("       ")
    line.append_text(_labelled("Remaining Wu", str(len(state.card_deck))))
    return line


def _state_grid(player: Player, bot: Player, init_player: int, init_bot: int) -> Table:
    # The Wu behind each initiative: this duelist's own buffs plus the opponent's debuffs, which is
    # why a card in your bracket may be sitting in their hand.
    player_sources, bot_sources = initiative_sources(player, bot)

    grid = Table.grid(expand=True, padding=(0, 1))
    grid.add_column(ratio=3, justify="left")  # Player n
    grid.add_column(ratio=6, justify="left")  # affiliation icon + name (stats)
    grid.add_column(ratio=3, justify="left")  # deck
    grid.add_column(ratio=4, justify="right")  # initiative
    rows = (
        ("Player 1", player, init_player, player_sources),
        ("Player 2", bot, init_bot, bot_sources),
    )
    for label, duelist, init, sources in rows:
        char = duelist.character
        name = Text(f"{affiliation_icon(char)} ")
        name.append(display_name(char.name).upper(), style="bold")
        name.append(f" ({char_stats(char)})", style="dim")  # stats in brackets, next to the name
        # The two rows share one Static, so a widget-level tooltip could not tell them apart — the
        # bonuses ride on this cell's own span instead (see TooltipStatic). Always tagged, even with
        # nothing applied, so a hover that shows nothing means the cursor missed, not that the
        # duelist is unbuffed.
        bonuses = [card.power.initiative_bonus for card in sources]
        initiative_cell = _labelled("Initiative", str(init))
        initiative_cell.stylize(Style(meta={"tooltip": bonus_tooltip(bonuses)}))
        grid.add_row(
            Text(f"{label}:", style="dim"),
            name,
            _labelled("Deck", str(len(duelist.deck))),
            initiative_cell,
        )
    return grid


def _actions_grid(blocked: dict[str, str | None]) -> Table:
    # Expand to the panel and split it into three equal columns, so the actions spread across the
    # width instead of huddling in a natural-width block in the middle. Each entry is centred in its
    # own column, which keeps the block balanced left-to-right at any panel width.
    grid = Table.grid(expand=True, padding=(0, 2))
    for _ in range(3):
        grid.add_column(ratio=1, justify="center")
    for start in range(0, len(_ACTIONS), 3):
        cells: list[Text] = [_action_cell(entry, blocked) for entry in _ACTIONS[start : start + 3]]
        cells += [Text("")] * (3 - len(cells))
        grid.add_row(*cells)
    return grid


def _action_cell(entry: str, blocked: dict[str, str | None]) -> Text:
    key, _, rest = entry.partition(". ")
    reason = blocked.get(key)
    cell = Text()
    if reason is None:
        cell.append(f"{key}. ", style="bold")
        cell.append(rest)
    else:
        cell.append(f"{key}. {rest}", style="dim")  # greyed out — you can't take this action now
    # Every action is tagged, so hovering a live one confirms what it does and a greyed one says why
    # it is out of reach (see TooltipStatic). Silence means the cursor missed the text.
    cell.stylize(Style(meta={"tooltip": reason or _ACTION_HELP.get(key, rest)}))
    return cell


def _hand_panel(character_name: str, rows: list[Text]) -> BoxedPanel:
    title = f"{display_name(character_name).split(' ')[0].upper()}'S HAND"
    # All rows in one Static so the panel centres them as a block (rows stay left-aligned within it).
    return BoxedPanel(Static(Text("\n").join(rows), classes="hand-block"), title=title)
