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
from textual.widgets import Footer, Header, Static

from termcade.ui.screens.base import EngineScreen
from termcade.ui.widgets import BoxedPanel

from ..logic.duel import Duel, DuelChoices, DuelState
from ..logic.constants import ELEMENTS
from ..logic.models import Card, Player
from ..logic.settings import XiaolinSettings
from ..logic.state import XiaolinState
from ..logic.turn import bot_turn, max_hand_size, refill_hands
from .format import char_stats, display_name, stats_line


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
        self._committed = False  # once the showdown begins there is no walking away

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
        """Back out before the showdown begins — return to the vault.

        Only the opening board offers this: from the first "Continue" the priority is locked (or the
        coin is thrown) and the prize is drawn, so there is nothing left to walk away from.
        """
        if self._committed:
            self.app.notify("Gong Yi Tanpai! There is no retreat from a showdown.")
            return
        self._retreating = True
        self._continue.set()

    async def _await_continue(self, prompt: str) -> None:
        self.query_one("#duel-prompt", Static).update(f"▶  {prompt}")
        self._continue.clear()
        await self._continue.wait()
        self.query_one("#duel-prompt", Static).update("")

    async def _reveal_coin_toss(self, player_won: bool) -> None:
        """Tied initiative — the player calls the coin, then learns whether they hold priority."""
        call = await self.choose(
            "Tied initiative —  call the coin.",  # the em-dash eats the space to its right
            [("Heads", "heads"), ("Tails", "tails")],
            title="COIN TOSS",
        )
        # Priority was already decided; reveal a face consistent with it — a matching call wins.
        face = call if player_won else ("tails" if call == "heads" else "heads")
        outcome = "You win priority!" if player_won else "You lose priority."
        await self.show_message(f"The coin lands {face.upper()}.  {outcome}", title="COIN TOSS")

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
        self._committed = True

        while True:
            stage = await duel.advance()  # one phase; a choice phase raises its modal inline
            self._show_board(duel)
            if stage == 1 and duel.duel.player_initiative == duel.duel.bot_initiative:
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
            difficulty = self.ctx.settings.current.difficulty  # the bot's deposit skill follows it
            self.app.notify(
                "\n".join(bot_turn(state, settings, difficulty=difficulty)), title="Opponent's turn"
            )
            refill_hands(state, settings, rng=rng)
        self._leave()

    async def _discard_surplus(self, state: XiaolinState, settings: XiaolinSettings) -> None:
        """Over the hand limit (you just won cards) → choose which Wu to shelve to your deck."""
        while not state.has_ended:
            if len(state.player.whole_hand) <= max_hand_size(state.player, settings.max_hand_size):
                return
            card = await self.choose(
                "Too many Wu — shelve one to your deck",
                _card_options(state.player.hand),
                title="DISPOSE",
            )
            state.player.remove_card(card)
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
        return await self.choose("Choose the challenge stat", _stat_options(options), title="CHALLENGE")

    async def _pick_background(self, options: list[str]) -> str:
        return await self.choose("Choose the background element", _stat_options(options), title="BACKGROUND")

    async def _pick_element(self, _background: str) -> str:
        return await self.choose("Choose an element", _stat_options(list(ELEMENTS)), title="ELEMENT")

    async def _pick_boost(self, cards: list[Card]) -> Card | None:
        options: list[tuple[str, Card | None]] = [*_card_options(cards), ("Don't play", None)]
        return await self.choose("Play a boost Wu?", options, title="BOOST")

    async def _pick_card(self, cards: list[Card]) -> Card:
        return await self.choose("Play a card", _card_options(cards), title="CARD")


def _stat_options(values: list[str]) -> list[tuple[str, str]]:
    return [(value.upper(), value) for value in values]


def _card_options(cards: list[Card]) -> list[tuple[str, Card]]:
    return [(f"{card.name}  ({stats_line(card.stats)})", card) for card in cards]


def _card_options(cards: list[Card]) -> list[tuple[str, Card]]:
    return [(f"{card.name}  ({stats_line(card.stats)})", card) for card in cards]


_SETUP_STAGE = 2  # named for what *you* do there: pick the challenge, or answer with the background

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
    if duel.stage == _SETUP_STAGE:
        # Setup is one stage but two moves: the priority holder names the contested stat, the other
        # answers with the element. Title it with the move *this* duelist made.
        return "Challenge" if duel.player_priority else "Background"
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
        Text(f"—  {_phase_name(duel)} —", style="bold", justify="center"),  # the em-dash eats the space to its right
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
