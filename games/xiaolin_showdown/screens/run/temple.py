"""Temple screen — the between-duel hub (the *deposit* screen is the Vault)."""

from __future__ import annotations

import os
from typing import Literal

from rich.text import Text
from termcade.ui.work import work
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.geometry import Size
from textual.widgets import Footer, Header

from termcade.ui.screens.base import TOUCH_ENV
from termcade.ui.screens.log import GameLogScreen
from termcade.ui.screens.save_slot import SaveSlotScreen
from termcade.ui.widgets import BoxedPanel, TooltipStatic

from ...logic.characters import jong
from ...logic.flow.actions import (
    can_combine_yoyo,
    can_construct,
    can_deposit,
    can_draw,
    can_early_bird,
    can_self_correct_yoyo,
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
from ...logic.mechanics.scoring import initiative
from ...logic.config.settings import player_actions
from ...logic.flow.training import TRAIN_LENGTH, payout_ready, raise_stat, trainable_stats
from ...logic.flow.turn import DRAW, TRAIN
from ...music import XIAOLIN, XIAOLIN_BOSS
from ..base import XiaolinScreen
from ..actions.deposit import DepositScreen
from ..display import temple_render
from ..display.format import card_options, prompt
from ..display.headline import your_move
from ..actions.lookup import LookUpScreen
from ..reference.rules import RulesScreen
from ..actions.use_power import UsePowerScreen


# Below this width/height ratio the grid is a portrait phone; landscape and desktop sit near 4.
_PORTRAIT_RATIO = 2.5


class TempleScreen(XiaolinScreen):
    # No Back: the temple is the run's root screen.
    BACK_ALLOWED = False

    # Seeded by `compose` with the value it actually rendered, so the first resize — which arrives
    # DURING mount — compares against the truth and does nothing. Defaulting to a guess meant a
    # narrow screen always rebuilt itself mid-mount, tearing down a Header still building.
    _bars_were_compact = False

    @property
    def _short_names(self) -> bool:
        """Whether to show a duelist by their first name alone.

        The DEVICE answers this, not the column width — a phone in landscape can report more
        columns than a laptop, so width alone can't tell them apart.
        """
        return bool(os.environ.get(TOUCH_ENV))

    def _compact_bars(self, size: Size | None = None) -> bool:
        """Whether the training bars should be a percentage instead of a bar.

        Portrait is judged by ASPECT RATIO, not column width: terminal cell aspect ratio varies
        by device, so a fixed column threshold lands on the wrong side of some phones.

        ``size`` must be the value the resize event carries, not ``app.size`` — during a
        rotation, ``app.size`` still holds the shape being left behind, so a check against it
        never detects the change.
        """
        size = size if size is not None else self.app.size
        if not size.height:
            return False
        return size.width / size.height < _PORTRAIT_RATIO

    def on_resize(self, event: events.Resize) -> None:
        """Rebuild when a rotation crosses the breakpoint, and only then.

        The bars are Rich text baked at compose time, so unlike the stylesheet they don't reflow
        on their own. Guarded on the value actually changing: a resize arrives as a burst, and
        rebuilding on every one would tear the screen apart mid-rotation.
        """
        compact = self._compact_bars(event.size)
        if compact != self._bars_were_compact:
            self._bars_were_compact = compact
            self.rebuild()

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
            # TooltipStatic, not Static: the Points figure carries a hover tooltip via `meta`,
            # which a plain Static never reads.
            yield TooltipStatic(
                temple_render._summary_line(
                    player, bot, state,
                    target=state.win_target(self.rules),
                    actions_left=player_actions(state, self.rules) - state.actions_taken,
                ),
                id="summary",
            )
            self._bars_were_compact = self._compact_bars()
            yield TooltipStatic(
                temple_render._state_grid(
                    player, bot, init_player, init_bot,
                    compact=self._bars_were_compact, short_names=self._short_names,
                ),
                id="state",
            )

        player_rows, bot_rows = temple_render.hands_lines(player.whole_hand, bot.whole_hand)
        with Horizontal(id="hands"):
            yield temple_render._hand_panel(jong.shown_name(player), player_rows)
            yield temple_render._hand_panel(jong.shown_name(bot), bot_rows)

        # Keyed by the shown number, so the greying and the hover reason come from one source.
        budget = player_actions(state, rules)
        blocked: dict[str, str | None] = {
            "1": "The run is over." if state.has_ended else None,
            "2": draw_blocked(state, rules),
            "3": deposit_blocked(state, budget),
            "4": (
                None
                if (
                    can_early_bird(state, rules)
                    or can_construct(state, budget)
                    or can_combine_yoyo(state, budget)
                    or can_self_correct_yoyo(state, budget)
                )
                else use_power_blocked(state, budget)
            ),
            "5": train_blocked(state, budget),
        }
        with BoxedPanel(title="ACTIONS"):
            yield TooltipStatic(temple_render._actions_grid(blocked, _ACTION_BY_KEY), id="actions")

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
        # Set here (not at character select) so loading a saved run into the temple also picks
        # the right tune. `play_tune` no-ops when it's already playing.
        boss = self.state.boss_run
        self.engine_app.play_tune(
            XIAOLIN_BOSS if boss else XIAOLIN, name="boss" if boss else ""
        )
        self._offer_payout()

    def _offer_payout(self) -> None:
        """Offer a full training bar's payout once per fill. The flag re-arms once the payout is
        claimed, so the next full bar is offered again."""
        if not payout_ready(self.state.player):
            self._payout_offered = False
            return
        if not self._payout_offered:
            self._payout_offered = True
            self._pick_training_stat()

    def action_gong_yi_tanpai(self) -> None:
        state = self.state
        if state.has_ended or max(state.player.points, state.bot.points) >= state.win_target(
            self.rules
        ):
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
        card = draw(self.state, rng=self.ctx.rng)  # rng lets a Hodoku Mouse take the draw back
        self.app.notify(f"Drew {card.name}.", title=your_move(DRAW))
        self.rebuild()  # show the drawn Wu without leaving the temple

    @work
    async def _swap_draw(self) -> None:
        """Full hand: choose a Wu to shelve, then draw one back — one action, hand size unchanged."""
        shelved = await self.choose(
            prompt("Your hand is full.", "Shelve which Wu to your Deck, and draw another?"),
            card_options(self.state.player.hand),
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
        budget = player_actions(state, rules)
        if (
            usable_powers(state, budget)
            or can_early_bird(state, rules)
            or can_construct(state, budget)
            or can_combine_yoyo(state, budget)
            or can_self_correct_yoyo(state, budget)
        ):
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
        if train(self.state, rng=self.ctx.rng):  # rng lets a Hodoku Mouse take the fill back
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
        """The player picks which base stat rises when a training bar pays out."""
        player = self.state.player
        stat = await self.choose(
            prompt("Your training paid off!", "Which stat do you raise?"),
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


# Read off the bindings rather than written out again, so a rebound key moves its click target
# with it instead of quietly pointing at the old action.
_ACTION_BY_KEY = {
    binding.key: binding.action
    for binding in Binding.make_bindings(TempleScreen.BINDINGS)
    if binding.key.isdigit()
}
