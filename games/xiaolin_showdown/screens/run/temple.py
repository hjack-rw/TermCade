"""Temple screen — the between-duel hub (the *deposit* screen is the Vault)."""

from __future__ import annotations

import asyncio
import os
from typing import Literal

from rich.table import Table
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
from ...logic.flow.training import payout_ready, raise_stat, trainable_stats
from ...logic.flow.turn import DRAW, TRAIN
from ...music import XIAOLIN, XIAOLIN_BOSS
from ..base import XiaolinScreen
from ..actions.deposit import DepositScreen
from ..display import temple_render
from ..display.format import card_options, display_name, prompt
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

    def __init__(
        self,
        *,
        player_training_before: int | None = None,
        player_points_before: int | None = None,
        is_run_start: bool = False,
    ) -> None:
        super().__init__()
        self._suspended = False
        self._payout_offered = False  # offer a waiting training payout once, not on every return
        self._flash_actions_next_resume = False
        # A prior Temple instance's training value, carried across the `switch_screen` a showdown
        # does on its way back — this instance never rebuilds from that one, so without this the
        # bar would just jump straight to its new total with nothing to tween from. Cleared after
        # the first mount reads it (see `on_mount`) so a later `rebuild()` doesn't reapply it.
        self._player_training_before = player_training_before
        # Same idea, for Points — set here for the cross-`switch_screen` return from a duel, and
        # also set transiently by `on_screen_resume` for the same-instance return from Deposit or
        # Use a Power (both push/pop, so no constructor is involved for that path).
        self._player_points_before = player_points_before
        self._points_before_suspend: int | None = None
        # True only for the Temple that opens a fresh run (see `character_select._begin_run`) —
        # every return-to-temple from a duel switches screens too, and would replay a boss intro
        # on every single showdown if this weren't distinguished from a genuine run start.
        self._is_run_start = is_run_start

    def flag_power_used(self) -> None:
        """Set by `UsePowerScreen._return_to_temple` right before it pops back to this screen, so
        the next resume gives the Actions panel a beat of colour once its own rebuild has actually
        landed — flashing before that rebuild would land on the widget it's about to tear down."""
        self._flash_actions_next_resume = True

    def _flash_actions(self) -> None:
        panel = self.query_one("#actions", TooltipStatic)
        self.set_timer(0.05, lambda: panel.add_class("flash"))
        self.set_timer(0.55, lambda: panel.remove_class("flash"))

    def _render_summary(self, *, player_points_override: int | None = None) -> Text:
        """The summary line — factored out of `compose` so `_tween_points` can re-render just this
        Static's content mid-fill, the same way `_render_state_grid` serves the training tween."""
        state, rules = self.state, self.rules
        return temple_render._summary_line(
            state.player, state.bot, state,
            target=state.win_target(rules),
            actions_left=player_actions(state, rules) - state.actions_taken,
            player_points_override=player_points_override,
        )

    def _render_state_grid(self, *, player_training_override: int | None = None) -> Table:
        """The P1/P2 row grid — factored out of `compose` so `_tween_training` can re-render just
        this cell's content mid-fill without re-running the whole screen's `compose`.

        ``player_training_override`` shows a value other than the real ``player.training`` for one
        frame, without ever writing it — the tween must never touch the actual persisted stat."""
        state, rules = self.state, self.rules
        player, bot = state.player, state.bot
        init_player, init_bot = initiative(player, bot)
        return temple_render._state_grid(
            player, bot, init_player, init_bot,
            train_length_player=rules.train_length_player,
            train_length_bot=rules.train_length_bot,
            settings=rules,
            compact=self._bars_were_compact, short_names=self._short_names,
            player_training_override=player_training_override,
        )

    def compose(self) -> ComposeResult:
        state, rules = self.state, self.rules
        player, bot = state.player, state.bot

        yield Header()

        with BoxedPanel(title="STATE OF THE GAME"):
            # TooltipStatic, not Static: the Points figure carries a hover tooltip via `meta`,
            # which a plain Static never reads. First paint shows the OLD points when one is
            # carried in, same as the training bar just below, so `on_mount`/`on_screen_resume`
            # have somewhere to tween from.
            yield TooltipStatic(
                self._render_summary(player_points_override=self._player_points_before), id="summary"
            )
            self._bars_were_compact = self._compact_bars()
            # The first paint shows the OLD value when one is carried in, so `on_mount`'s tween has
            # somewhere to climb from — everything else on this grid is already the true, current
            # state, only the bar itself is deliberately shown a beat behind.
            yield TooltipStatic(
                self._render_state_grid(player_training_override=self._player_training_before), id="state"
            )

        player_rows, bot_rows = temple_render.hands_lines(
            player.whole_hand, bot.whole_hand, wear_limit=rules.wear_limit
        )
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
                else use_power_blocked(state, budget, rules)
            ),
            "5": train_blocked(state, budget, rules),
        }
        with BoxedPanel(title="ACTIONS"):
            yield TooltipStatic(temple_render._actions_grid(blocked, _ACTION_BY_KEY), id="actions")

        yield Footer()

    # A sub-screen may have changed the hands or the points, so the panels rebuild on the way back.
    def on_screen_suspend(self) -> None:
        self._suspended = True
        # Deposit and Use a Power (both push/pop) are the only same-instance ways Points can
        # change — snapshotted here so `on_screen_resume` has something to tween from, the same
        # role `_training_before` plays for a duel's `switch_screen` return.
        self._points_before_suspend = self.state.player.points

    def on_screen_resume(self) -> None:
        if self._suspended:
            self._suspended = False
            before = self._points_before_suspend
            after = self.state.player.points
            if before is not None and before != after:
                # Seed the value `compose` shows on this rebuild, same trick `on_mount` plays with
                # the constructor-supplied `_player_points_before` — then clear it so a later
                # rebuild renders the live figure, and tween once this recompose has landed.
                self._player_points_before = before
                self.rebuild()
                self.call_after_refresh(lambda: self._start_points_tween(before))
            else:
                self.rebuild()
        if self._flash_actions_next_resume:
            self._flash_actions_next_resume = False
            # Deferred past the rebuild above: `rebuild()`'s own recompose isn't done yet at this
            # point (see its docstring) — flashing now would land on the `#actions` widget about to
            # be torn down, not the one that replaces it.
            self.call_after_refresh(self._flash_actions)
        self._offer_payout()

    def on_mount(self) -> None:
        # Set here (not at character select) so loading a saved run into the temple also picks
        # the right tune. `play_tune` no-ops when it's already playing.
        boss = self.state.boss_run
        self.engine_app.play_tune(
            XIAOLIN_BOSS if boss else XIAOLIN, name="boss" if boss else ""
        )
        if self._is_run_start and boss:
            self._show_boss_intro()

        # Warm the outcome jingles here, off the run's own critical path — see `prerender_tune`.
        # Lazy: outcome.py imports the temple's siblings, a top-level import here would cycle.
        from ...music import XIAOLIN_DEFEAT, XIAOLIN_VICTORY
        from .outcome import VICTORY_SEED

        self.engine_app.prerender_tune(XIAOLIN_VICTORY, name="victory", seed=VICTORY_SEED)
        self.engine_app.prerender_tune(XIAOLIN_DEFEAT, name="defeat", seed=self.game.game_id)

        # Only the very first compose should ever show the old value — clear it now so a later
        # `rebuild()` on this same instance renders the real, live training figure.
        before = self._player_training_before
        self._player_training_before = None
        if (
            before is not None
            and before != self.state.player.training
            # A full bar is about to raise its own modal (see `_offer_payout` below) — that already
            # reads as the moment of confirmation, so animating the bar first would either finish
            # invisibly under it or just delay it for no reason.
            and not payout_ready(self.state.player, self.rules)
        ):
            self._tween_training(before, full_rebuild=False)

        # Same idea, for Points: the very first compose already showed the old value (see
        # `compose`) — clear it now so a later `rebuild()` on this instance renders the live one.
        points_before = self._player_points_before
        self._player_points_before = None
        if points_before is not None and points_before != self.state.player.points:
            self._tween_points(points_before, full_rebuild=False)
        self._offer_payout()

    def _show_boss_intro(self) -> None:
        """A beat of menace before the run's first temple turn, in place of the usual summary line —
        the boss's name, briefly. Nothing else about a boss run needed a screen of its own for this."""
        summary = self.query_one("#summary", TooltipStatic)
        name = display_name(self.state.bot.character.name, upper=True)
        summary.update(Text(f"⚔  {name}  ⚔", justify="center"))
        summary.add_class("boss-intro")
        self.set_timer(1.4, lambda: summary.remove_class("boss-intro"))
        self.set_timer(1.4, self._restore_summary)

    def _restore_summary(self) -> None:
        self.query_one("#summary", TooltipStatic).update(self._render_summary())

    def _offer_payout(self) -> None:
        """Offer a full training bar's payout once per fill. The flag re-arms once the payout is
        claimed, so the next full bar is offered again."""
        if not payout_ready(self.state.player, self.rules):
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
            usable_powers(state, budget, rules)
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
        if train_blocked(self.state, player_actions(self.state, self.rules), self.rules) is not None:
            return
        if payout_ready(self.state.player, self.rules):
            self._pick_training_stat()  # the bar is already full: picking the stat is free
            return
        before = self.state.player.training
        if train(self.state, self.rules, rng=self.ctx.rng):  # rng lets a Hodoku Mouse take the fill back
            self._pick_training_stat()  # this very turn filled it
            return
        self.app.notify(
            "You trained for +1 progress.\n"
            f"Progress towards the next Stat upgrade: "
            f"{self.state.player.training}/{self.rules.train_length_player}!",
            title=your_move(TRAIN),
        )
        self._tween_training(before)

    @work
    async def _tween_training(self, before: int, *, full_rebuild: bool = True) -> None:
        """Ease the training bar from its old value to its new one.

        The state grid is one Rich table baked into a single Static, not live per-cell widgets, so
        this re-renders just that Static a few times with an interpolated value rather than tearing
        down the whole screen for every intermediate step. The interpolated value is only ever passed
        into the render, never written to `player.training` — that field is real, persisted game
        state, and a save (or this worker getting cancelled by navigating away mid-tween) must never
        see anything but the true value `train()` already committed.

        ``full_rebuild`` decides how it ends: the explicit Train action spends an action, which can
        also change what the Actions panel allows, so that caller wants the whole screen refreshed.
        A fresh Temple mounting after a showdown already composed everything else from current truth —
        the bar was the one cell deliberately shown a beat behind, so finishing it just needs one more
        plain render, not a full recompose.
        """
        after = self.state.player.training
        grid_widget = self.query_one("#state", TooltipStatic)
        steps = 4
        for step in range(1, steps):
            shown = round(before + (after - before) * step / steps)
            grid_widget.update(self._render_state_grid(player_training_override=shown))
            await asyncio.sleep(0.05)
        if full_rebuild:
            self.rebuild()
        else:
            grid_widget.update(self._render_state_grid())

    def _start_points_tween(self, before: int) -> None:
        """Deferred entry point for the same-instance return from Deposit/Use a Power — clears the
        seeded override once this recompose has actually landed (see `on_screen_resume`), the same
        role `on_mount` plays for the constructor-supplied value, then starts the tween."""
        self._player_points_before = None
        self._tween_points(before, full_rebuild=False)

    @work
    async def _tween_points(self, before: int, *, full_rebuild: bool = True) -> None:
        """Ease the summary line's Points figure from its old value to its new one — same trick as
        `_tween_training`, on `#summary` instead of `#state`."""
        after = self.state.player.points
        summary_widget = self.query_one("#summary", TooltipStatic)
        steps = 4
        for step in range(1, steps):
            shown = round(before + (after - before) * step / steps)
            summary_widget.update(self._render_summary(player_points_override=shown))
            await asyncio.sleep(0.05)
        if full_rebuild:
            self.rebuild()
        else:
            summary_widget.update(self._render_summary())

    @work
    async def _pick_training_stat(self) -> None:
        """The player picks which base stat rises when a training bar pays out."""
        player = self.state.player
        stat = await self.choose(
            prompt("Your training paid off!", "Which stat do you raise?"),
            [(stat.capitalize(), stat) for stat in trainable_stats(player, self.rules)],
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
