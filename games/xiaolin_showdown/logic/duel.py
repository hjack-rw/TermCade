"""The showdown — a 7-stage machine in a pure, injectable form.

A duel is a *loop of showdowns* over the shared draw pile until it runs dry. One showdown walks
stages 1→6 then a closing stage 0:

    1 Initiative   → who commits first (priority; a tie is a coin toss at stage 2)
    2 Commitment   → draw the prize card; the priority holder's side names the challenge stat
    3 Challenge/BG → the other side names the background element
    4 Power        → each duelist may play a boost Wu
    5 Card         → each plays one card; :func:`~.powers.resolve_played_power` resolves it
    6 Resolvement  → score every staked stat, decide the winner, maybe award the prize card
    0 End          → the loser's staked cards change hands; reset for the next showdown

**Transient — never saved.** The machine mutates deep-copied scratch cards in place; a save's
``snapshot()`` is valid only at the vault (no active duel). Every human decision is an injected
:class:`DuelChoices` callback, so this layer blocks on nothing and tests headlessly; the bot's
decisions come from :mod:`.bot`. Advancing one stage per call mirrors one "Continue" press.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from copy import deepcopy
from dataclasses import dataclass, field

from termcade.core.rng import Rng

from . import bot
from .constants import ELEMENTS
from .mechanics.powers import is_boost_slot
from .mechanics.resolve import resolve_played_power
from .mechanics.scoring import contributing, count_end_stats, initiative
from .models import Card, Player
from .state import XiaolinState

LAST_STAGE = 6  # the showdown cycles stages 0..6


@dataclass
class DuelState:
    stage: int = 0
    stakes: Card | None = None  # the prize card for this showdown
    challenge: str | None = None  # the contested stat: force / agility / intellect
    background: str | None = None  # the contested element
    player_priority: bool | None = None  # who commits first (None = tie → coin toss)
    player_initiative: int = 0
    bot_initiative: int = 0
    player_stakes: list[Card] = field(default_factory=list)
    bot_stakes: list[Card] = field(default_factory=list)
    player_queue: list[Card] = field(default_factory=list)  # resolved cards feeding scoring
    bot_queue: list[Card] = field(default_factory=list)
    # The curse mirrors a *negative* Wu landed on this side: the very objects sitting in the queue
    # above, so the board can tell "I played this" from "this was done to me". Display only.
    player_suffered: list[Card] = field(default_factory=list)
    bot_suffered: list[Card] = field(default_factory=list)
    # Which of the mirrors above are a booster's share of a curse. A mirror is inert — its power is
    # stripped — so nothing else can tell, and the board must join it to what it boosts. Display only.
    player_amplifiers: list[Card] = field(default_factory=list)
    bot_amplifiers: list[Card] = field(default_factory=list)
    player_result: list[int] = field(default_factory=list)  # per-stat end values (for display)
    bot_result: list[int] = field(default_factory=list)
    winner: bool | None = None  # True = player won, False = bot won
    winner_character: str | None = None
    card_won: bool = False
    # A "Serpent's Tail" (play/−1) played by *either* duelist voids the elemental bonus for the whole
    # showdown — a condition of the duel, not of the queue it was played into.
    elemental_bonus_cancelled: bool = False


@dataclass
class DuelChoices:
    """The human duelist's decisions, injected by the screen (the bot's come from :mod:`.bot`).

    Each is awaited only when it is the player's turn to decide — the stage machine is async so a
    terminal screen can ``await`` a modal for the answer while the game logic stays pure.
    """

    challenge: Callable[[list[str]], Awaitable[str]]  # pick the contested stat (player has priority)
    background: Callable[[list[str]], Awaitable[str]]  # pick the element (player lacks priority)
    boost: Callable[[list[Card]], Awaitable[Card | None]]  # play a boost Wu, or decline
    card: Callable[[list[Card]], Awaitable[Card]]  # play a card from hand
    element: Callable[[str], Awaitable[str]]  # a Morpher's element (given the background)


class Duel:
    """Drives one showdown loop over ``state.card_deck``. Call :meth:`advance` per "Continue"."""

    def __init__(self, state: XiaolinState, rng: Rng, choices: DuelChoices) -> None:
        self.state = state
        self.rng = rng
        self.choices = choices
        self.duel = DuelState()

    @property
    def is_over(self) -> bool:
        """The draw pile is spent — the run is finished (go to the outcome screen)."""
        return self.state.has_ended

    async def advance(self) -> int:
        """Run the next stage and return it.

        Re-entering at stage 0 resets the per-showdown scratch, so the closing end phase (also
        stage 0) always runs on the *finished* showdown before the reset wipes it.
        """
        if self.duel.stage == 0:
            self.duel = DuelState()
        self.duel.stage = 0 if self.duel.stage >= LAST_STAGE else self.duel.stage + 1
        await self._STAGES[self.duel.stage](self)
        return self.duel.stage

    # --- stages ---------------------------------------------------------------------------
    async def _initiative(self) -> None:
        player_init, bot_init = initiative(self.state.player, self.state.bot)
        self.duel.player_initiative = player_init
        self.duel.bot_initiative = bot_init
        self.duel.player_priority = None if player_init == bot_init else player_init > bot_init

    async def _commitment(self) -> None:
        self.duel.stakes = self.state.card_deck.pop(0)
        if self.duel.player_priority is None:  # tie → a fair coin decides who leads
            self.duel.player_priority = self.rng.choice([True, False])
        # only when the bot leads does it name the challenge here; a leading player waits for stage 3
        if not self.duel.player_priority:
            self.duel.challenge = bot.choose_challenge(
                self.state.bot.character.stats,
                self._challenge_options(),
                self.state.bot.whole_hand,
                self.state.player.character.stats,
                self.rng,
            )

    async def _setup(self) -> None:
        if self.duel.player_priority:
            self.duel.challenge = await self.choices.challenge(self._challenge_options())
            self.duel.background = bot.choose_background(
                self.state.bot.character.stats,
                self._background_options(),
                (self.state.bot.whole_hand, self.state.player.whole_hand),
                self.state.player.character.stats,
                self.rng,
            )
        else:  # the bot led and chose the challenge at stage 2; the player answers the background
            self.duel.background = await self.choices.background(self._background_options())

    async def _power(self) -> None:
        player_card = await self.choices.boost(self._boost_options(self.state.player))
        if player_card is not None:
            self._commit_boost(player_card, self.duel.player_stakes, self.duel.player_queue)

        bot_boosts = self._boost_options(self.state.bot)
        if bot_boosts:  # the bot always plays a boost when it holds one
            self._commit_boost(self.rng.choice(bot_boosts), self.duel.bot_stakes, self.duel.bot_queue)

    async def _card(self) -> None:
        # A duelist with no card left (decks and hand exhausted near the end) simply plays nothing
        # and scores on their base stats (playing nothing avoids crashing on an empty choice).
        player_playable = self._playable(self.state.player, self.duel.player_stakes)
        if player_playable:
            player_card = await self.choices.card(player_playable)
            self.duel.player_stakes.append(player_card)
            element = await self._element_for(player_card)
            resolve_played_power(self.duel, player_card, is_player=True, element=element)

        challenge, background = self._contested()
        bot_playable = self._playable(self.state.bot, self.duel.bot_stakes)
        if bot_playable:
            bot_card = bot.choose_card(
                self.state.bot.character.stats,
                challenge,
                background,
                bot_playable,
                self.state.player.character.stats,
                self.rng,
            )
            self.duel.bot_stakes.append(bot_card)
            resolve_played_power(self.duel, bot_card, is_player=False, element=background)

    async def _element_for(self, card: Card) -> str:
        """A Morpher (play/+1) lets the player choose its element; any other card ignores it."""
        if card.power.trigger == "play" and card.power.effect == 1:
            return await self.choices.element(self.duel.background or "")
        return self.duel.background or ""

    async def _resolvement(self) -> None:
        challenge, background = self._contested()
        stats = list(self.duel.stakes.stats.keys()) if self.duel.stakes else []
        player_result: list[int] = []
        bot_result: list[int] = []
        score = 0
        for stat in stats:
            elemental_bonus, point = (1, 2) if stat == challenge else (0, 1)
            if self.duel.elemental_bonus_cancelled:  # a Serpent's Tail is on the table
                elemental_bonus = 0
            player_end = count_end_stats(
                stat, elemental_bonus, self.duel.player_queue, self.state.player.character.stats,
                background,
                earns_bonus=self._earns_bonus(self.duel.player_queue, self.duel.player_suffered),
                suffers_bonus=contributing(self.duel.player_suffered),
            )
            bot_end = count_end_stats(
                stat, elemental_bonus, self.duel.bot_queue, self.state.bot.character.stats,
                background,
                earns_bonus=self._earns_bonus(self.duel.bot_queue, self.duel.bot_suffered),
                suffers_bonus=contributing(self.duel.bot_suffered),
            )
            player_result.append(player_end)
            bot_result.append(bot_end)
            score += 0 if player_end == bot_end else point if player_end > bot_end else -point

        self.duel.player_result = player_result
        self.duel.bot_result = bot_result
        # a clear score wins; a dead heat falls to whoever had priority
        self.duel.winner = score > 0 if score else bool(self.duel.player_priority)
        self._award_prize(challenge, stats, player_result, bot_result)

    async def _end(self) -> None:
        self.state.previous_challenge = [self.duel.challenge] if self.duel.challenge else []
        self.state.previous_background = [self.duel.background] if self.duel.background else []
        self.state.deposit_counter = 0
        self.state.draw_counter = 0
        if not self.state.card_deck:
            self.state.has_ended = True

        # the loser gives up every card they staked this showdown; the winner takes them
        winner, loser = self._winner_and_loser()
        forfeit = self.duel.bot_stakes if self.duel.winner else self.duel.player_stakes
        for card in forfeit:
            loser.remove_card(card)
            winner.hand.append(card)

    _STAGES: dict[int, Callable[["Duel"], Awaitable[None]]] = {
        0: _end,
        1: _initiative,
        2: _commitment,
        3: _setup,
        4: _power,
        5: _card,
        6: _resolvement,
    }

    # --- helpers --------------------------------------------------------------------------
    def _challenge_options(self) -> list[str]:
        stats = self.duel.stakes.stats.keys() if self.duel.stakes else ()
        return [s for s in stats if s not in self.state.previous_challenge]

    def _background_options(self) -> list[str]:
        return [e for e in ELEMENTS if e not in self.state.previous_background]

    def _boost_options(self, player: Player) -> list[Card]:
        return [c for c in player.whole_hand if is_boost_slot(c.power)]

    def _playable(self, player: Player, staked: list[Card]) -> list[Card]:
        # regular play draws from the hand only (the inalienable Wu is boost-only)
        return [c for c in player.hand if c not in staked]

    def _commit_boost(self, card: Card, stakes: list[Card], queue: list[Card]) -> None:
        if card.power.effect > 0:  # a positive boost can be lost, so it joins the stakes
            stakes.append(card)
        queue.append(deepcopy(card))  # a private scratch copy the resolver may amplify

    @staticmethod
    def _earns_bonus(queue: list[Card], suffered: list[Card]) -> list[Card]:
        """The Wu this duelist played that still contribute — the only cards the background rewards.

        A curse mirror in the queue is the *opponent's* Wu. It reads the background too, but against
        this duelist — see ``suffers_bonus`` in :func:`~.mechanics.scoring.count_end_stats`.
        """
        mine = [card for card in queue if not any(card is mirror for mirror in suffered)]
        return contributing(mine)

    def _contested(self) -> tuple[str, str]:
        assert self.duel.challenge is not None and self.duel.background is not None
        return self.duel.challenge, self.duel.background

    def _winner_and_loser(self) -> tuple[Player, Player]:
        if self.duel.winner:
            return self.state.player, self.state.bot
        return self.state.bot, self.state.player

    def _award_prize(
        self, challenge: str, stats: list[str], player_result: list[int], bot_result: list[int]
    ) -> None:
        winner, _loser = self._winner_and_loser()
        self.duel.winner_character = winner.character.name
        winner_result = player_result if self.duel.winner else bot_result
        # the prize card is only kept if the winner cleared the challenge stat decisively (>7)
        self.duel.card_won = bool(self.duel.stakes) and winner_result[stats.index(challenge)] > 7
        if self.duel.card_won and self.duel.stakes is not None:
            winner.hand.append(self.duel.stakes)
