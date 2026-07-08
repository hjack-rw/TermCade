"""Duel screen — one showdown, driven by the async :class:`~..logic.duel.Duel` stage machine.

The stage machine awaits the player's decisions; here each ``await`` raises a :class:`ChoiceModal`
via ``push_screen_wait`` and resolves with the chosen value. The whole showdown runs in an async
worker so the UI stays responsive and the pure game logic never touches Textual.

One press of "Gong Yi Tanpai" plays exactly one showdown (stages 1→6→0). The vault turn runs here
too, at the end — you shelve any surplus Wu, the bot takes its turn, and the hands settle — so
control returns to the vault, or, when the draw pile is spent, to the :class:`~.outcome.OutcomeScreen`.
"""

from __future__ import annotations

import asyncio
from typing import cast

from rich.console import Group, RenderableType
from rich.table import Table
from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Static

from termcade.ui.screens.base import EngineScreen
from termcade.ui.widgets import BoxedPanel

from ..logic.duel import Duel, DuelChoices, DuelState
from ..logic.elements import ELEMENTS
from ..logic.models import Card, Player, remove_card_from_hand
from ..logic.settings import XiaolinSettings
from ..logic.state import XiaolinState
from ..logic.turn import bot_turn, max_hand_size, refill_hands
from .format import char_stats, display_name, stats_line

Option = tuple[str, object]


class ChoiceModal(ModalScreen[object]):
    """A list of buttons; dismisses with the value behind the chosen one. With ``title`` set, that is
    the border label and ``prompt`` shows inside; otherwise ``prompt`` is the border label itself."""

    # No pre-selected option on open — same rule as EngineScreen, but ModalScreen doesn't inherit it.
    # Must be "" (not None): None makes Textual fall back to the app's "*" and auto-focus the first
    # button; the empty string is what actually leaves the modal un-highlighted until the player tabs.
    AUTO_FOCUS = ""

    def __init__(self, prompt: str, options: list[Option], *, title: str | None = None) -> None:
        super().__init__()
        self._prompt = prompt
        self._options = options
        self._title = title

    def compose(self) -> ComposeResult:
        with BoxedPanel(title=self._title or self._prompt):
            if self._title is not None:
                yield Static(self._prompt, classes="modal-prompt")
            for index, (label, _value) in enumerate(self._options):
                yield Button(label, id=f"opt-{index}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        assert event.button.id is not None
        self.dismiss(self._options[int(event.button.id.removeprefix("opt-"))][1])


class DuelScreen(EngineScreen):
    """One showdown, stepped through a phase at a time — the player presses Continue to advance,
    seeing each phase resolve, and the choice phases raise their modal inline."""

    BINDINGS = [
        ("enter,space", "continue", "Continue"),
        ("escape", "retreat", "Retreat"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._continue = asyncio.Event()
        self._duel: Duel | None = None
        self._retreating = False

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

    def action_retreat(self) -> None:
        """Back out before committing (before the prize card is drawn) — return to the vault."""
        if self._duel is not None and self._duel.duel.stakes is None:
            self._retreating = True
            self._continue.set()

    async def _await_continue(self, prompt: str) -> None:
        self.query_one("#duel-prompt", Static).update(f"▶  {prompt}")
        self._continue.clear()
        await self._continue.wait()
        self.query_one("#duel-prompt", Static).update("")

    async def _reveal_coin_toss(self, player_won: bool) -> None:
        """Tied initiative — the player calls the coin, then learns whether they hold priority."""
        call = cast(
            str,
            await self._ask(
                ChoiceModal(
                    "Tied initiative — call the coin.",
                    [("Heads", "heads"), ("Tails", "tails")],
                    title="COIN TOSS",
                )
            ),
        )
        # Priority was already decided; reveal a face consistent with it — a matching call wins.
        face = call if player_won else ("tails" if call == "heads" else "heads")
        outcome = "You win priority!" if player_won else "You lose priority."
        await self.app.push_screen_wait(
            ChoiceModal(
                f"The coin lands {face.upper()}.  {outcome}",
                [("Continue", None)],
                title="COIN TOSS",
            )
        )

    @work
    async def _run_showdown(self) -> None:
        state = cast(XiaolinState, self.ctx.state)
        settings = XiaolinSettings.from_settings(self.ctx.settings.current)
        rng = self.ctx.rng
        duel = Duel(state, rng, self._choices())
        self._duel = duel

        self._show_board(duel)
        await self._await_continue("Continue to begin the showdown        (Esc retreats)")
        if self._retreating:
            self._retreat_to_vault()
            return
        while True:
            stage = await duel.advance()  # one phase; a choice phase raises its modal inline
            self._show_board(duel)
            if stage == 2 and duel.duel.player_initiative == duel.duel.bot_initiative:
                await self._reveal_coin_toss(duel.duel.player_priority is True)
            if stage == 0:  # the end phase (the loser's stakes change hands) has run
                break
            can_retreat = duel.duel.stakes is None  # nothing is committed until the prize is drawn
            await self._await_continue("Continue" + ("        (Esc retreats)" if can_retreat else ""))
            if self._retreating and can_retreat:
                self._retreat_to_vault()
                return

        # The result is already on screen, so head straight into the vault turn (no extra Continue):
        # you shelve any surplus Wu (your choice), the bot banks points, then the
        # hands settle (which may flag the run over on the point limit). Skip once the pile is spent.
        if not state.has_ended:
            await self._discard_surplus(state, settings)
            self.app.notify("\n".join(bot_turn(state, settings)), title="Opponent's turn")
            refill_hands(state, settings, rng=rng)
        self._leave()

    async def _discard_surplus(self, state: XiaolinState, settings: XiaolinSettings) -> None:
        """Over the hand limit (you just won cards) → choose which Wu to shelve to your deck."""
        while not state.has_ended:
            if len(state.player.whole_hand) <= max_hand_size(state.player, settings.max_hand_size):
                return
            card = cast(
                Card,
                await self._ask(
                    ChoiceModal(
                        "Too many Wu — shelve one to your deck",
                        _card_options(state.player.hand),
                        title="DISPOSE",
                    )
                ),
            )
            remove_card_from_hand(state.player, card)
            state.player.deck.append(card)

    def _leave(self) -> None:
        # Lazy imports: the vault imports this screen, so importing it at module load would cycle.
        if cast(XiaolinState, self.ctx.state).has_ended:
            from .outcome import OutcomeScreen

            self.app.switch_screen(OutcomeScreen())
        else:
            from .vault import VaultScreen

            self.app.switch_screen(VaultScreen())

    def _retreat_to_vault(self) -> None:
        """Abandon an uncommitted showdown — no prize drawn, no cards staked, nothing to undo."""
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
        modal = ChoiceModal("Choose the challenge stat", _stat_options(options), title="CHALLENGE")
        return cast(str, await self._ask(modal))

    async def _pick_background(self, options: list[str]) -> str:
        modal = ChoiceModal("Choose the background element", _stat_options(options), title="BACKGROUND")
        return cast(str, await self._ask(modal))

    async def _pick_element(self, _background: str) -> str:
        modal = ChoiceModal("Choose an element", _stat_options(list(ELEMENTS)), title="ELEMENT")
        return cast(str, await self._ask(modal))

    async def _pick_boost(self, cards: list[Card]) -> Card | None:
        options = _card_options(cards) + [("Don't play", None)]
        modal = ChoiceModal("Play a boost Wu?", options, title="BOOST")
        return cast("Card | None", await self._ask(modal))

    async def _pick_card(self, cards: list[Card]) -> Card:
        modal = ChoiceModal("Play a card", _card_options(cards), title="CARD")
        return cast(Card, await self._ask(modal))

    async def _ask(self, modal: ChoiceModal) -> object:
        return await self.app.push_screen_wait(modal)


def _stat_options(values: list[str]) -> list[Option]:
    return [(value.upper(), value) for value in values]


def _card_options(cards: list[Card]) -> list[Option]:
    return [(f"{card.name}  ({stats_line(card.stats)})", card) for card in cards]


_PHASE_NAMES = {
    0: "End",
    1: "Initiative",
    2: "Commitment",
    3: "Challenge & Background",
    4: "Power",
    5: "Card",
    6: "Resolvement",
}


def _phase_name(duel: DuelState) -> str:
    # stage 0 is reused: the fresh pre-showdown board (no winner yet) vs the closing end phase.
    if duel.stage == 0 and duel.winner_character is None:
        return "Gong Yi Tanpai!"
    return _PHASE_NAMES.get(duel.stage, "")


def _won(duel: DuelState) -> str:
    return display_name(duel.winner_character or "").upper()


def _labelled(label: str, value: str, *, strong: bool = False) -> Text:
    """A dim label followed by its value — the muted-label / bright-value pairing used on the board."""
    text = Text()
    text.append(f"{label}: ", style="dim")
    text.append(value, style="bold" if strong else "")
    return text


def _board_text(duel: DuelState, state: XiaolinState) -> RenderableType:
    prize = f"{duel.stakes.name} ({stats_line(duel.stakes.stats)})" if duel.stakes else "—"

    prize_line = Text(justify="center")  # the prize sits on its own centred line
    prize_line.append("Prize: ", style="dim")
    prize_line.append(prize, style="bold" if duel.stakes else "")

    meta = Table.grid(expand=True)  # initiative / challenge / background spread across the board
    meta.add_column(justify="left", ratio=1)
    meta.add_column(justify="center", ratio=1)
    meta.add_column(justify="right", ratio=1)
    meta.add_row(
        _labelled("Initiative", f"P1 {duel.player_initiative}  P2 {duel.bot_initiative}"),
        _labelled("Challenge", (duel.challenge or "—").upper(), strong=bool(duel.challenge)),
        _labelled("Background", (duel.background or "—").upper(), strong=bool(duel.background)),
    )

    parts: list[RenderableType] = [
        Text(f"— {_phase_name(duel)} —", style="bold", justify="center"),
        "",
        prize_line,
        "",
        meta,
        "",
        _side_line("P1", state.player, duel.player_queue, duel.player_result, leads=duel.player_priority is True),
        _side_line("P2", state.bot, duel.bot_queue, duel.bot_result, leads=duel.player_priority is False),
    ]
    if duel.winner_character:
        parts += ["", Text(f"{_won(duel)} WINS!", style="bold")]
    return Group(*parts)


def _side_line(label: str, player: Player, queue: list[Card], result: list[int], *, leads: bool) -> Group:
    name = display_name(player.character.name)
    marker = "✫ " if leads else ""  # holds priority: names the challenge, breaks a tied duel

    header = Text()
    header.append(f"{label} ", style="dim")
    header.append(f"{marker}{name}", style="bold")
    header.append(f" (base {char_stats(player.character)})", style="dim")

    # The Wu committed this showdown (with their stats), on their own line below the header.
    used = ", ".join(f"{display_name(c.name)} ({stats_line(c.stats)})" for c in queue) or "—"
    played = Text()
    played.append("    Cards played: ", style="dim")
    played.append(used)
    if result:  # score appears once scoring has run; joined to its arrow so they wrap as one unit
        played.append("   ")
        played.append("→  ", style="dim")
        played.append("/".join(str(value) for value in result), style="bold")

    return Group(header, played)
