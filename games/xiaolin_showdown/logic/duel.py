"""The showdown — a 7-stage machine in a pure, injectable form.

A duel is a *loop of showdowns* over the shared draw pile until it runs dry. One showdown walks
stages 1→6 then a closing stage 0:

    1 Commitment   → draw the prize card; a tied initiative is settled by a coin toss here
    2 Setup        → the priority holder names the challenge stat, the other the background element
    3 Boost        → each duelist may play a boost Wu, in addition to their card
    4 Card         → each plays one card; :func:`~.mechanics.resolve.resolve_played_power` resolves it
    5 Resolvement  → score every staked stat, decide the winner, maybe award the prize card
    0 End          → the loser's staked cards change hands; reset for the next showdown

**Initiative is not a stage.** It is a property of the two hands, so a showdown opens with it already
resolved and on the board: the first "Continue" either commits you to the priority you can see, or
draws the coin toss that breaks a tie. Nothing is staked until then, so that press is the point of no
return.

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
from .mechanics.cards import excluding
from .mechanics.powers import is_boost_slot
from .mechanics.resolve import resolve_played_power
from .mechanics.scoring import contributing, count_end_stats, initiative
from .models import Card, Player
from .settings import XiaolinSettings
from .state import XiaolinState

END, COMMITMENT, SETUP, BOOST, CARD, RESOLVEMENT = range(6)
LAST_STAGE = RESOLVEMENT  # the showdown cycles stages 0..5, but BOOST..CARD repeats per Wu wagered


@dataclass
class Side:
    """One duelist's half of a round: what they put on the table, and what landed on them.

    Every duelist holds one of these, and nothing here knows *which* duelist it belongs to. That is
    the point: a rule written against a ``Side`` is written once and holds for both of them.
    """

    queue: list[Card] = field(default_factory=list)  # what scores on this side
    suffered: list[Card] = field(default_factory=list)  # curse mirrors the opponent landed here
    amplifiers: list[Card] = field(default_factory=list)  # which of those mirrors a booster doubled
    result: list[int] = field(default_factory=list)  # per-stat end values

    def contributors(self) -> list[Card]:
        """The Wu *this* duelist played that still contribute — all the background rewards.

        A curse mirror in the queue is the opponent's Wu. It reads the background too, but against
        this side — see ``suffers_bonus`` in :func:`~.mechanics.scoring.count_end_stats`.
        """
        return contributing(excluding(self.queue, self.suffered))


@dataclass
class Round:
    """One Wu each, fought out. A showdown is a best-of-N over these."""

    player: Side = field(default_factory=Side)
    bot: Side = field(default_factory=Side)
    score: int = 0  # from the player's side: +2 the challenge, +1 each other stat
    winner: bool | None = None  # True player, False bot, None a dead heat

    def sides(self, is_player: bool) -> tuple[Side, Side]:
        """``(mine, theirs)`` — the only place a duel turns "which duelist" into "which half"."""
        return (self.player, self.bot) if is_player else (self.bot, self.player)


@dataclass
class Duelist:
    """One duelist's stake in the showdown: what they brought, and what they can no longer take back."""

    initiative: int = 0
    stakes: list[Card] = field(default_factory=list)  # Wu fielded — the loser forfeits every one
    # A boost Wu is spent once a showdown, not once a round: you choose which Wu to lift.
    boosts_spent: list[Card] = field(default_factory=list)


@dataclass
class DuelState:
    stage: int = 0
    stakes: Card | None = None  # the prize card for this showdown
    challenge: str | None = None  # the contested stat: force / agility / intellect
    background: str | None = None  # the contested element
    # The place the showdown is fought in — flavour only. Drawn from the pool of the element the
    # duelist named, off the seeded RNG, so a seed replays the same board. Never touches scoring.
    background_name: str | None = None
    player_priority: bool | None = None  # who commits first (None = tie → coin toss)
    player: Duelist = field(default_factory=Duelist)
    bot: Duelist = field(default_factory=Duelist)
    # How many Wu each duelist must field. Named by the duelist who did NOT call the challenge —
    # you set the terms, I set the price — and capped by what both can actually play.
    wager: int = 1
    rounds: list[Round] = field(default_factory=list)  # one per Wu wagered, in the order fought
    winner: bool | None = None  # True = player won, False = bot won
    winner_character: str | None = None
    card_won: bool = False
    # A "Serpent's Tail" (play/−1) played by *either* duelist voids the elemental bonus for the whole
    # showdown — a condition of the duel, not of the queue it was played into. It carries across
    # every round: the ground stays intangible once someone makes it so.
    elemental_bonus_cancelled: bool = False

    def duelist(self, is_player: bool) -> Duelist:
        return self.player if is_player else self.bot

    @property
    def round(self) -> Round:
        """The round being fought. There is always one once the showdown has begun."""
        return self.rounds[-1]

    @property
    def round_number(self) -> int:
        return len(self.rounds)

    @property
    def rounds_won(self) -> tuple[int, int]:
        return (
            sum(1 for r in self.rounds if r.winner is True),
            sum(1 for r in self.rounds if r.winner is False),
        )


@dataclass
class DuelChoices:
    """The human duelist's decisions, injected by the screen (the bot's come from :mod:`.bot`).

    Each is awaited only when it is the player's turn to decide — the stage machine is async so a
    terminal screen can ``await`` a modal for the answer while the game logic stays pure.
    """

    challenge: Callable[[list[str]], Awaitable[str]]  # pick the contested stat (player has priority)
    background: Callable[[list[str]], Awaitable[str]]  # pick the element (player lacks priority)
    wager: Callable[[list[int]], Awaitable[int]]  # how many Wu to stake (player lacks priority)
    boost: Callable[[list[Card]], Awaitable[Card | None]]  # play a boost Wu, or decline
    card: Callable[[list[Card]], Awaitable[Card]]  # play a card from hand
    element: Callable[[str], Awaitable[str]]  # a Morpher's element (given the background)


class Duel:
    """Drives one showdown loop over ``state.card_deck``. Call :meth:`advance` per "Continue"."""

    def __init__(
        self,
        state: XiaolinState,
        rng: Rng,
        choices: DuelChoices,
        settings: XiaolinSettings | None = None,
    ) -> None:
        self.state = state
        self.rng = rng
        self.choices = choices
        # The tunables a showdown reads: the prize threshold, and the most Wu that may be staked.
        self.settings = settings or XiaolinSettings()
        self.duel = self._new_round()

    def _new_round(self) -> DuelState:
        """A fresh showdown with initiative already read off the two hands.

        Priority is ``None`` only on a tie, which :meth:`_commitment` settles with a coin.
        """
        duel = DuelState()
        duel.player.initiative, duel.bot.initiative = initiative(self.state.player, self.state.bot)
        if duel.player.initiative != duel.bot.initiative:
            duel.player_priority = duel.player.initiative > duel.bot.initiative
        return duel

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
            self.duel = self._new_round()  # hands have changed; initiative is read afresh
        self.duel.stage = self._next_stage()
        await self._STAGES[self.duel.stage](self)
        return self.duel.stage

    def _next_stage(self) -> int:
        """The showdown walks 1..5, except that Boost and Card loop once per Wu wagered.

        A best-of-3 is three exchanges, not one: Card falls back to Boost until every staked Wu has
        been fought, and only then does Resolvement weigh the match.
        """
        stage = self.duel.stage
        if stage == CARD and self.duel.round_number < self.duel.wager:
            return BOOST
        return 0 if stage >= LAST_STAGE else stage + 1

    # --- stages ---------------------------------------------------------------------------
    async def _commitment(self) -> None:
        self.duel.stakes = self.state.card_deck.pop(0)
        if self.duel.player_priority is None:  # tie → a fair coin decides who leads
            self.duel.player_priority = self.rng.choice([True, False])
        # only when the bot leads does it name the challenge here; a leading player waits for stage 2
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
            self.duel.wager = bot.choose_wager(
                self._wager_options(), self.state.bot.whole_hand, self.state.player.whole_hand,
            )
        else:  # the bot led and chose the challenge at stage 1; the player answers the background
            self.duel.background = await self.choices.background(self._background_options())
            self.duel.wager = await self.choices.wager(self._wager_options())
        self.duel.background_name = self._draw_place(self.duel.background)

    def _wager_options(self) -> list[int]:
        """How many Wu the stakes may be — named by whoever did NOT call the challenge.

        You set the terms, I set the price. Capped by what *both* can field: a wager one duelist
        cannot answer is not a wager, it is a forfeit.
        """
        both_can_field = min(
            len(self.state.player.hand), len(self.state.bot.hand), self.settings.max_wager
        )
        return list(range(1, max(1, both_can_field) + 1))

    def _draw_place(self, element: str | None) -> str | None:
        """A named place from ``element``'s pool. Flavour: the *element* is what scores, always."""
        if element is None:
            return None
        pool = self.state.catalog.backgrounds_for(element)
        if not pool:
            return None
        # A sub-stream, never the duel's own: the place is decoration, and decoration that consumed
        # the main stream would shift every roll after it — a cosmetic change that alters the game.
        return self.rng.spawn("background").choice(pool).name

    async def _boost(self) -> None:
        self.duel.rounds.append(Round())  # a new Wu, a new exchange

        player_card = await self.choices.boost(self._boost_options(self.state.player, is_player=True))
        if player_card is not None:
            self._commit_boost(player_card, is_player=True)

        bot_boosts = self._boost_options(self.state.bot, is_player=False)
        if bot_boosts:  # the bot always plays a boost when it holds one
            self._commit_boost(self.rng.choice(bot_boosts), is_player=False)

    async def _card(self) -> None:
        # A duelist with no card left (decks and hand exhausted near the end) simply plays nothing
        # and scores on their base stats (playing nothing avoids crashing on an empty choice).
        current = self.duel.round
        player_playable = self._playable(self.state.player, is_player=True)
        if player_playable:
            player_card = await self.choices.card(player_playable)
            self.duel.player.stakes.append(player_card)
            element = await self._element_for(player_card)
            if resolve_played_power(current, player_card, is_player=True, element=element):
                self.duel.elemental_bonus_cancelled = True

        challenge, background = self._contested()
        bot_playable = self._playable(self.state.bot, is_player=False)
        if bot_playable:
            bot_card = bot.choose_card(
                self.state.bot.character.stats,
                challenge,
                background,
                bot_playable,
                self.state.player.character.stats,
                self.rng,
            )
            self.duel.bot.stakes.append(bot_card)
            if resolve_played_power(current, bot_card, is_player=False, element=background):
                self.duel.elemental_bonus_cancelled = True

        self._score_round(current)

    def _score_round(self, current: Round) -> None:
        """Weigh one exchange: the challenge stat counts double, the other two count once."""
        challenge, background = self._contested()
        stats = list(self.duel.stakes.stats.keys()) if self.duel.stakes else []
        score = 0
        for stat in stats:
            elemental_bonus, point = (1, 2) if stat == challenge else (0, 1)
            if self.duel.elemental_bonus_cancelled:  # a Serpent's Tail is on the table
                elemental_bonus = 0
            player_end = self._end_stat(
                stat, elemental_bonus, current.player, self.state.player, background
            )
            bot_end = self._end_stat(
                stat, elemental_bonus, current.bot, self.state.bot, background
            )
            current.player.result.append(player_end)
            current.bot.result.append(bot_end)
            score += 0 if player_end == bot_end else point if player_end > bot_end else -point

        current.score = score
        current.winner = None if score == 0 else score > 0

    @staticmethod
    def _end_stat(
        stat: str, elemental_bonus: int, side: Side, player: Player, background: str
    ) -> int:
        """One duelist's final value for one stat: their own, their Wu, and what was done to them."""
        return count_end_stats(
            stat,
            elemental_bonus,
            side.queue,
            player.character.stats,
            background,
            earns_bonus=side.contributors(),
            suffers_bonus=contributing(side.suffered),
        )

    async def _element_for(self, card: Card) -> str:
        """A Morpher (play/+1) lets the player choose its element; any other card ignores it."""
        if card.power.trigger == "play" and card.power.effect == 1:
            return await self.choices.element(self.duel.background or "")
        return self.duel.background or ""

    async def _resolvement(self) -> None:
        """Weigh the match. A Wu must belong to someone, so this always names a winner.

        Three steps, in order. Rounds won is the honest headline. Aggregate margin breaks a level
        match by *how* the rounds were won — a rout counts for more than a whisker, which is what
        makes committing your best Wu worth doing. Only when nothing at all separates them does the
        duelist who called the challenge hold the ground: rare, and dramatic when it lands.
        """
        player_rounds, bot_rounds = self.duel.rounds_won
        if player_rounds != bot_rounds:
            self.duel.winner = player_rounds > bot_rounds
        else:
            margin = sum(r.score for r in self.duel.rounds)
            self.duel.winner = margin > 0 if margin else bool(self.duel.player_priority)

        challenge, _ = self._contested()
        stats = list(self.duel.stakes.stats.keys()) if self.duel.stakes else []
        self._award_prize(challenge, stats)

    async def _end(self) -> None:
        self.state.previous_challenge = [self.duel.challenge] if self.duel.challenge else []
        self.state.previous_background = [self.duel.background] if self.duel.background else []
        self.state.deposit_counter = 0
        self.state.draw_counter = 0
        if not self.state.card_deck:
            self.state.has_ended = True

        # the loser gives up every card they staked this showdown; the winner takes them
        winner, loser = self._winner_and_loser()
        for card in self.duel.duelist(not self.duel.winner).stakes:
            loser.remove_card(card)
            winner.hand.append(card)

    _STAGES: dict[int, Callable[["Duel"], Awaitable[None]]] = {
        END: _end,
        COMMITMENT: _commitment,
        SETUP: _setup,
        BOOST: _boost,
        CARD: _card,
        RESOLVEMENT: _resolvement,
    }

    # --- helpers --------------------------------------------------------------------------
    def _challenge_options(self) -> list[str]:
        stats = self.duel.stakes.stats.keys() if self.duel.stakes else ()
        return [s for s in stats if s not in self.state.previous_challenge]

    def _background_options(self) -> list[str]:
        return [e for e in ELEMENTS if e not in self.state.previous_background]

    def _boost_options(self, player: Player, *, is_player: bool) -> list[Card]:
        """Boost Wu still available this showdown — a boost is spent once, not once a round.

        A Wu is spent when it is used, whichever slot it went into. A best-of-3 can force you to
        field a booster as an ordinary Wu; once you do, it is gone — you cannot stake the same Wu as
        a card and then lift another card with it. And a dragon cannot be replayed round after round.
        """
        duelist = self.duel.duelist(is_player)
        unused = excluding(player.whole_hand, duelist.boosts_spent + duelist.stakes)
        available = [card for card in unused if is_boost_slot(card.power)]

        # You owe a Wu for every round still to fight. Boosting with one out of HAND spends a Wu you
        # would have fielded, so it is only offered while you can still cover what you owe. A Wu that
        # lives in the inalienable slot is never fieldable as a card, so it always costs you nothing.
        owed = self.duel.wager - self.duel.round_number + 1
        if len(self._playable(player, is_player=is_player)) > owed:
            return available
        return excluding(available, player.hand)

    def _playable(self, player: Player, *, is_player: bool) -> list[Card]:
        """Wu that may still be fielded as a card. The hand only — the inalienable Wu is boost-only."""
        return excluding(player.hand, self.duel.duelist(is_player).stakes)

    def _commit_boost(self, card: Card, *, is_player: bool) -> None:
        duelist = self.duel.duelist(is_player)
        mine, _theirs = self.duel.round.sides(is_player)
        if card.power.effect > 0:  # a positive boost can be lost, so it joins the stakes
            duelist.stakes.append(card)
        duelist.boosts_spent.append(card)  # one showdown, one use — even a dragon
        mine.queue.append(deepcopy(card))  # a private scratch copy the resolver may amplify

    def _contested(self) -> tuple[str, str]:
        assert self.duel.challenge is not None and self.duel.background is not None
        return self.duel.challenge, self.duel.background

    def _winner_and_loser(self) -> tuple[Player, Player]:
        if self.duel.winner:
            return self.state.player, self.state.bot
        return self.state.bot, self.state.player

    def _award_prize(self, challenge: str, stats: list[str]) -> None:
        """The prize is claimed on the winner's BEST round — one decisive blow is enough."""
        winner, _loser = self._winner_and_loser()
        self.duel.winner_character = winner.character.name
        if not self.duel.stakes or challenge not in stats:
            self.duel.card_won = False
            return

        column = stats.index(challenge)
        best = max(
            r.sides(bool(self.duel.winner))[0].result[column]
            for r in self.duel.rounds
            if r.player.result and r.bot.result
        )
        self.duel.card_won = best > self.settings.prize_threshold  # win small, and the Wu is lost
        if self.duel.card_won:
            winner.hand.append(self.duel.stakes)
