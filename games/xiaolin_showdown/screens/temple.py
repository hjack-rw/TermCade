"""Temple screen — the between-duel hub (the *deposit* screen is the Vault).

Three stacked panels: game state, both hands (element-coloured), and actions. Each panel's
content is a Rich grid that expands to fill the box; secondary labels are dimmed and names
are emphasised, and the whole screen rebuilds on return so deposits and draws show at once.
"""

from __future__ import annotations

from typing import Literal

from rich.style import Style
from rich.table import Table
from rich.text import Text
from termcade.ui.work import work
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Footer, Header, Static

from termcade.ui.screens.log import GameLogScreen
from termcade.ui.screens.save_slot import SaveSlotScreen
from termcade.ui.widgets import BoxedPanel, TooltipStatic, render_bar

from ..logic.actions import (
    can_deposit,
    can_draw,
    can_early_bird,
    deposit_blocked,
    draw,
    draw_blocked,
    draw_swaps,
    swap_from_hand,
    train,
    train_blocked,
    usable_powers,
    use_power_blocked,
)
from ..logic.mechanics.scoring import initiative, initiative_sources
from ..logic.models import Player
from ..logic.settings import player_actions
from ..logic.state import XiaolinState
from ..logic.training import TRAIN_LENGTH, payout_ready, raise_stat, trainable_stats
from ..logic.turn import DRAW, TRAIN
from .base import XiaolinScreen
from .deposit import DepositScreen
from .format import (
    affiliation_icon,
    bonus_tooltip,
    card_label,
    char_stats,
    display_name,
    hands_lines,
    labelled,
    your_move,
)
from .lookup import LookUpScreen
from .rules import RulesScreen
from .use_power import UsePowerScreen


class TempleScreen(XiaolinScreen):
    BINDINGS = [
        ("1", "gong_yi_tanpai", "Duel"),
        ("2", "draw", "Draw"),
        ("3", "deposit", "Deposit"),
        ("4", "use_power", "Power"),
        ("5", "train", "Train"),
        ("6", "lookup", "Lookup"),
        ("7", "game_log", "Log"),
        ("8", "rules", "Rules"),
        ("9", "save_game", "Save"),
        ("escape", "app.pop_screen", "Menu"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._suspended = False
        self._payout_offered = False  # offer a waiting training payout once, not on every return

    def compose(self) -> ComposeResult:
        state, rules = self.state, self.rules
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

        # Keyed by the shown number, so the greying and the hover reason come from one source.
        # "4" opens on the Early Bird alone: it is a power, and a fast duelist has one to spend even
        # holding no Wu that acts.
        budget = player_actions(state, rules)  # 3 to the boss's one in a boss run
        blocked: dict[str, str | None] = {
            "1": "The run is over." if state.has_ended else None,
            "2": draw_blocked(state, rules),
            "3": deposit_blocked(state, budget),
            "4": (
                None
                if can_early_bird(state, rules)
                else use_power_blocked(state, budget)
            ),
            "5": train_blocked(state, budget),
        }
        with BoxedPanel(title="ACTIONS"):
            yield TooltipStatic(_actions_grid(blocked), id="actions")

        yield Footer()

    # A sub-screen may have changed the hands or the points, so the panels rebuild on the way back.
    def on_screen_suspend(self) -> None:
        self._suspended = True

    def on_screen_resume(self) -> None:
        if self._suspended:
            self._suspended = False
            self.rebuild()
        self._offer_payout()

    def on_mount(self) -> None:
        self._offer_payout()

    def _offer_payout(self) -> None:
        """A bar filled by a lost showdown waits for its stat pick — offer it the moment the player
        is back at the temple. Once per fill: a dismissed offer stays claimable through Train, and
        the flag re-arms when the payout is gone so the NEXT full bar is offered again."""
        if not payout_ready(self.state.player):
            self._payout_offered = False
            return
        if not self._payout_offered:
            self._payout_offered = True
            self._pick_training_stat()

    def action_gong_yi_tanpai(self) -> None:
        state = self.state
        if state.has_ended or max(state.player.points, state.bot.points) >= self.rules.point_limit:
            self.end_run()  # someone is already at the limit — no more duels
            return

        from .duel import DuelScreen  # lazy: DuelScreen returns here, so a top import would cycle

        self.app.switch_screen(DuelScreen())

    def action_draw(self) -> None:
        if not can_draw(self.state, self.rules):
            return
        if draw_swaps(self.state, self.rules):
            self._swap_draw()  # a full hand cycles: pick one to shelve, take one back
            return
        card = draw(self.state)
        self.app.notify(f"Drew {card.name}.", title=your_move(DRAW))
        self.rebuild()  # show the drawn Wu without leaving the temple

    @work
    async def _swap_draw(self) -> None:
        """Full hand: choose a Wu to shelve, then draw one back — one action, hand size unchanged."""
        asked = Text("Your hand is full.")
        asked.append("\n\n")
        asked.append("Shelve which Wu to your Deck, and draw another?")
        shelved = await self.choose(
            asked,
            [(card_label(card), card) for card in self.state.player.hand],
            title="SWAP",
        )
        if shelved is None:
            return
        drawn = swap_from_hand(self.state, shelved, rng=self.ctx.rng)
        self.app.notify(f"Shelved {shelved.name}, drew {drawn.name}.", title=your_move(DRAW))
        # No rebuild here: the picker suspended this screen, so `on_screen_resume` rebuilds on the way
        # back. A second recompose races the Header's title-setter.

    def action_use_power(self) -> None:
        state, rules = self.state, self.rules
        if usable_powers(state, player_actions(state, rules)) or can_early_bird(state, rules):
            self.app.push_screen(UsePowerScreen())

    def action_deposit(self) -> None:
        if can_deposit(self.state, player_actions(self.state, self.rules)):
            self.app.push_screen(DepositScreen())

    def action_train(self) -> None:
        if train_blocked(self.state, player_actions(self.state, self.rules)) is not None:
            return
        if payout_ready(self.state.player):
            self._pick_training_stat()  # the bar is already full: picking the stat is free
            return
        if train(self.state):
            self._pick_training_stat()  # this very turn filled it
            return
        self.app.notify(
            "You trained for +1 progress.\n"
            f"Progress towards the next Stat upgrade: {self.state.player.training}/{TRAIN_LENGTH}!",
            title=your_move(TRAIN),
        )
        self.rebuild()

    @work
    async def _pick_training_stat(self) -> None:
        """A full bar pays out: the player picks which base stat rises (the bot shores up its lowest
        on its own — see `logic.training`). Free, even on a spent turn: the ten fills paid for it."""
        player = self.state.player
        asked = Text("Your training paid off!")
        asked.append("\n\n")
        asked.append("Which stat do you raise?")
        stat = await self.choose(
            asked,
            [(stat.capitalize(), stat) for stat in trainable_stats(player)],
            title="TRAINING",
        )
        if stat is None:
            return  # decide later — Train reopens the choice
        raise_stat(player, stat)
        self.app.notify(
            f"Your {stat} rose to {player.character.stats[stat]}.", title=your_move(TRAIN)
        )
        self.ctx.journal.add(
            f"You completed your training: your {stat} rose.", title=your_move(TRAIN)
        )

    def action_lookup(self) -> None:
        self._lookup()

    @work
    async def _lookup(self) -> None:
        """One Lookup for both inspect screens: ask what to look at, then open it."""
        options: list[tuple[str, Literal["cards", "characters"]]] = [
            ("Hand", "cards"),
            ("Character", "characters"),
        ]
        what = await self.choose(Text("What would you like to look up?"), options, title="LOOKUP")
        if what is not None:
            self.app.push_screen(LookUpScreen(what))

    def action_game_log(self) -> None:
        self.app.push_screen(GameLogScreen())

    def action_rules(self) -> None:
        self.app.push_screen(RulesScreen())

    def action_save_game(self) -> None:
        player = self.state.player
        title = f"{player.character.name} —  {player.points} pts"
        self.app.push_screen(SaveSlotScreen("save", title=title))


# Temple actions, laid out row-major into three columns that fill the panel (see _actions_grid).
_ACTIONS = [
    '1. "Gong Yi Tanpai!"',
    "2. Draw a Card",
    "3. Deposit a Card",
    "4. Use a Power",
    "5. Train a Stat",
    "6. Look Things Up",
    "7. Game Log",
    "8. Game Rules",
    "9. Save game",
    # Escape is NOT listed. It is on the footer, where every screen's escape is, and a panel of things
    # to *do* in the temple is not where "leave the temple" belongs. Nine actions fill the three columns
    # exactly; a tenth entry left one hanging alone on a fourth row.
]

# Hover text for an action that *is* available; a blocked one shows why instead (see _action_cell).
_ACTION_HELP = {
    "1": "Duel for the next Wu on the pile.",
    "2": "Take a Wu from your personal deck.",
    "3": "Cash a Wu from your hand for points.",
    "4": "Spend a Wu for its power.",
    "5": "Fill your training bar.",
    "6": "Inspect either hand or duelist.",
    "7": "Everything that has happened so far.",
    "8": "Rulebook for the game.",
    "9": "Save this run to a slot.",
}


def _summary_line(player: Player, bot: Player, state: XiaolinState) -> Text:
    line = Text()  # centred by the #summary `text-align`, not Rich justify (which uses natural width)
    line.append_text(labelled("Points", f"{player.points}/{bot.points}"))
    line.append("       ")
    line.append_text(labelled("Remaining Wu", str(len(state.card_deck))))
    return line


def _state_grid(player: Player, bot: Player, init_player: int, init_bot: int) -> Table:
    # The Wu behind each initiative: this duelist's own buffs plus the opponent's debuffs, which is
    # why a card in your bracket may be sitting in their hand.
    player_sources, bot_sources = initiative_sources(player, bot)

    # Columns size to their content, so a short name leaves no trailing gap. One flex column eats the
    # slack, pushing Deck and Initiative to the right; everything left of it packs tight.
    grid = Table.grid(expand=True, padding=(0, 1))
    grid.add_column(no_wrap=True)  # Player n
    grid.add_column(no_wrap=True)  # affiliation icon + name (stats)
    grid.add_column(width=3)  # gap between
    grid.add_column(no_wrap=True)  # training bar
    grid.add_column(ratio=1)  # flex — absorbs the slack, pushing Deck/Initiative right
    grid.add_column(justify="right", no_wrap=True)  # deck
    grid.add_column(width=4)  # gap between
    grid.add_column(justify="right", no_wrap=True)  # initiative
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
        initiative_cell = labelled("Initiative", str(init))
        initiative_cell.stylize(Style(meta={"tooltip": bonus_tooltip(bonuses)}))
        grid.add_row(
            Text(f"{label}:", style="dim"),
            name,
            Text(""),  # gap column
            _training_cell(duelist),
            Text(""),  # flex spacer
            labelled("Deck", str(len(duelist.deck))),
            Text(""),  # gap before Initiative
            initiative_cell,
        )
    return grid


def _training_cell(duelist: Player) -> Text:
    """A duelist's training bar (see ``logic.training``). A boss is at the stat cap and *cannot*
    train — it reads MASTER, centred in a dashed ruler as wide as the bar, and its tooltip is
    ``-/-``, not a full bar.

    Both rows start with the same ``Training:`` prefix in a left-justified column, so their labels line
    up under each other; a spacer column holds them clear of the name."""
    cell = Text("Training: ", style="dim")
    if duelist.character.tier == "boss":
        width = 2 * TRAIN_LENGTH - 1  # the bar's own footprint: segments with a space between
        word = " MASTER "
        dashes = (width - len(word)) // 2  # the same run both sides: symmetry beats exact width
        cell.append("-" * dashes + word + "-" * dashes)
        cell.stylize(Style(meta={"tooltip": "-/-"}))
        return cell
    cell.append(render_bar(duelist.training / TRAIN_LENGTH, TRAIN_LENGTH))
    cell.stylize(Style(meta={"tooltip": f"{duelist.training}/{TRAIN_LENGTH}"}))
    return cell


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
    # All rows in one widget so the panel centres them as a block (rows stay left-aligned within
    # it) — a TooltipStatic, so each row's own wear tooltip answers on hover (see format._rows).
    return BoxedPanel(TooltipStatic(Text("\n").join(rows), classes="hand-block"), title=title)
