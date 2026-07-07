"""Duel screen — one showdown, driven by the async :class:`~..logic.duel.Duel` stage machine.

The stage machine awaits the player's decisions; here each ``await`` raises a :class:`ChoiceModal`
via ``push_screen_wait`` and resolves with the chosen value. The whole showdown runs in an async
worker so the UI stays responsive and the pure game logic never touches Textual.

One press of "Gong Yi Tanpai" plays exactly one showdown (stages 1→6→0). The vault turn that
refills the hands runs here too, at the end, so control returns to a balanced vault — or, when the
draw pile is spent, to the :class:`~.outcome.OutcomeScreen`.

v1 simplification: the vault turn auto-sends a surplus card to the player's own deck rather than
prompting; interactive over-limit discard can come with the outcome slice.
"""

from __future__ import annotations

import asyncio
from typing import cast

from textual import work
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Static

from termcade.ui.screens.base import EngineScreen
from termcade.ui.widgets import BoxedPanel

from ..logic.duel import Duel, DuelChoices, DuelState
from ..logic.elements import ELEMENTS
from ..logic.models import Card, Player
from ..logic.settings import XiaolinSettings
from ..logic.state import XiaolinState
from ..logic.turn import bot_turn, refill_hands
from .format import stats_line

Option = tuple[str, object]


class ChoiceModal(ModalScreen[object]):
    """A titled list of buttons; dismisses with the value behind the chosen one."""

    def __init__(self, prompt: str, options: list[Option]) -> None:
        super().__init__()
        self._prompt = prompt
        self._options = options

    def compose(self) -> ComposeResult:
        with BoxedPanel(title=self._prompt):
            for index, (label, _value) in enumerate(self._options):
                yield Button(label, id=f"opt-{index}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        assert event.button.id is not None
        self.dismiss(self._options[int(event.button.id.removeprefix("opt-"))][1])


class DuelScreen(EngineScreen):
    """One showdown, stepped through a phase at a time — the player presses Continue to advance,
    seeing each phase resolve, and the choice phases raise their modal inline."""

    BINDINGS = [("enter,space", "continue", "Continue")]

    def __init__(self) -> None:
        super().__init__()
        self._continue = asyncio.Event()

    def compose(self) -> ComposeResult:
        yield Header()
        with BoxedPanel(title="XIAOLIN SHOWDOWN", id="duel-panel"):
            yield Static("Gong Yi Tanpai!", id="duel-body")
            yield Static("", id="duel-prompt")
        yield Footer()

    def on_mount(self) -> None:
        self._run_showdown()

    def action_continue(self) -> None:
        self._continue.set()

    async def _await_continue(self, prompt: str) -> None:
        self.query_one("#duel-prompt", Static).update(f"▶  {prompt}")
        self._continue.clear()
        await self._continue.wait()
        self.query_one("#duel-prompt", Static).update("")

    @work
    async def _run_showdown(self) -> None:
        state = cast(XiaolinState, self.ctx.state)
        settings = XiaolinSettings.from_settings(self.ctx.settings.current)
        rng = self.ctx.rng
        duel = Duel(state, rng, self._choices())

        self._show_board(duel)
        await self._await_continue("Continue to begin the showdown")
        while True:
            stage = await duel.advance()  # one phase; a choice phase raises its modal inline
            self._show_board(duel)
            if stage == 0:  # the end phase (the loser's stakes change hands) has run
                break
            await self._await_continue("Continue")
        await self._await_continue("Continue — back to the vault")

        # The vault turn: the bot banks points, then both hands refill (which may flag the run over
        # on the point limit). Skip it when the showdown already spent the pile.
        if not state.has_ended:
            bot_turn(state, settings)
            refill_hands(state, settings, pick_discard=_discard_first, rng=rng)
        self._leave()

    def _leave(self) -> None:
        # Lazy imports: the vault imports this screen, so importing it at module load would cycle.
        if cast(XiaolinState, self.ctx.state).has_ended:
            from .outcome import OutcomeScreen

            self.app.switch_screen(OutcomeScreen())
        else:
            from .vault import VaultScreen

            self.app.switch_screen(VaultScreen())

    def _show_board(self, duel: Duel) -> None:
        self.query_one("#duel-body", Static).update(_board_text(duel.duel, cast(XiaolinState, self.ctx.state)))

    # --- player decisions: raise a modal, resolve with what they pick ---------------------
    def _choices(self) -> DuelChoices:
        return DuelChoices(
            challenge=self._pick_challenge,
            background=self._pick_background,
            boost=self._pick_boost,
            card=self._pick_card,
            element=self._pick_element,
        )

    async def _pick_challenge(self, options: list[str]) -> str:
        return cast(str, await self._ask(ChoiceModal("Choose the challenge stat", _stat_options(options))))

    async def _pick_background(self, options: list[str]) -> str:
        return cast(str, await self._ask(ChoiceModal("Choose the background element", _stat_options(options))))

    async def _pick_element(self, _background: str) -> str:
        return cast(str, await self._ask(ChoiceModal("Choose an element", _stat_options(list(ELEMENTS)))))

    async def _pick_boost(self, cards: list[Card]) -> Card | None:
        options = _card_options(cards) + [("Play none", None)]
        return cast("Card | None", await self._ask(ChoiceModal("Play a boost Wu?", options)))

    async def _pick_card(self, cards: list[Card]) -> Card:
        return cast(Card, await self._ask(ChoiceModal("Play a card", _card_options(cards))))

    async def _ask(self, modal: ChoiceModal) -> object:
        return await self.app.push_screen_wait(modal)


def _discard_first(cards: list[Card]) -> Card:
    return cards[0]  # v1: auto-send the first surplus card to the deck (see module docstring)


def _stat_options(values: list[str]) -> list[Option]:
    return [(value.upper(), value) for value in values]


def _card_options(cards: list[Card]) -> list[Option]:
    return [(f"{card.name}   {stats_line(card.stats)}", card) for card in cards]


_PHASE_NAMES = {
    0: "End",
    1: "Initiative",
    2: "Commitment",
    3: "Challenge & Background",
    4: "Power",
    5: "Card",
    6: "Resolvement",
}


def _won(duel: DuelState) -> str:
    return (duel.winner_character or "").upper().replace("_", " ")


def _board_text(duel: DuelState, state: XiaolinState) -> str:
    stakes = duel.stakes.name if duel.stakes else "—"
    lines = [
        f"— {_PHASE_NAMES.get(duel.stage, '')} —",
        "",
        f"Prize: {stakes}      Challenge: {(duel.challenge or '—').upper()}"
        f"      Background: {(duel.background or '—').upper()}",
        f"Initiative — P1 {duel.player_initiative}   P2 {duel.bot_initiative}",
        "",
        _side_line("P1", state.player, duel.player_queue, duel.player_result),
        _side_line("P2", state.bot, duel.bot_queue, duel.bot_result),
    ]
    if duel.winner_character:
        prize = "  (won the prize!)" if duel.card_won else ""
        lines += ["", f"{_won(duel)} WINS!{prize}"]
    return "\n".join(lines)


def _side_line(label: str, player: Player, queue: list[Card], result: list[int]) -> str:
    name = player.character.name.split("_")[0]
    played = ", ".join(card.name for card in queue) or "—"
    score = "/".join(str(value) for value in result) if result else "—"
    return f"{label} {name}: {played}    →  {score}"
