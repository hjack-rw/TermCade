"""The showdown — a 7-stage machine in a pure, injectable form.

A duel is a *loop of showdowns* over the shared draw pile until it runs dry. One showdown walks
stages 1→6 then a closing stage 0:

    1 Commitment   → draw the prize card; a tied initiative is settled by a coin toss here
    2 Setup        → the challenger names the stat (or a tournament); the other the element and wager
    3 Boost        → each duelist may lay a boost Wu ahead of the Wu they are about to field
    4 Card         → both field one Wu, blind to each other; :mod:`.mechanics.resolve` resolves both
    5 Resolvement  → weigh the battles, decide the winner, maybe award the prize card
    0 End          → the loser's staked cards change hands; reset for the next showdown

**Three Wu, spent one of two ways.** The challenger names a *stat* or a *tournament*. On a stat, the
other duelist names the wager — one to three Wu, all fielded together in a single battle. A
tournament asks nobody: it is three battles of one Wu, contesting force, then agility, then intellect,
and may only be called when both duelists can field three. Either way Boost→Card loops once per Wu,
each Wu optionally preceded by a boost, and no boost Wu serves twice.

**Initiative is not a stage.** It is a property of the two hands, so a showdown opens with it already
resolved and on the board: the first "Continue" either commits you to the priority you can see, or
draws the coin toss that breaks a tie. Nothing is staked until then, so that press is the point of no
return.

**Transient — never saved.** The machine mutates deep-copied scratch cards in place; a save's
``snapshot()`` is valid only at the temple (no active duel). Every human decision is an injected
:class:`DuelChoices` callback, so this layer blocks on nothing and tests headlessly; the bot's
decisions come from :mod:`.bot`. Advancing one stage per call mirrors one "Continue" press.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from copy import deepcopy
from dataclasses import dataclass, field

from termcade.core.rng import Rng

from . import bot
from .constants import ELEMENTS, TOURNAMENT, TOURNAMENT_BATTLES
from .battle import Duelist, Ground, Round, score_battle
from .mechanics.cards import excluding, is_one_of
from .mechanics.powers import Mechanic, is_boost_slot, mechanic_of, names_a_stat
from .mechanics.prize import PrizeRoute, claim_route
from .mechanics.resolve import as_boost, resolve_played_power, stand_in
from .mechanics.scoring import initiative
from .models import Card, Player
from .settings import XiaolinSettings
from .state import XiaolinState
from .training import record_showdown
from . import wear
from .wear import hand_over

END, COMMITMENT, SETUP, BOOST, CARD, RESOLVEMENT = range(6)
LAST_STAGE = RESOLVEMENT  # the showdown cycles stages 0..5, but BOOST..CARD repeats per Wu wagered

# The Wu that ask their caster for an element: the Morpher (its shape), the Eye (its own colour), the
# Monsoon (the whole arena's).
_CHOOSES_ELEMENT = frozenset({Mechanic.MORPH, Mechanic.SET_ELEMENT, Mechanic.SET_ARENA})

# Chase Young's Beast Form: +1 on the contested stat, in exchange for his Wu. One, not two: the beast
# KEEPS its prize now (see `_award_prize`), and at +2 that was worth so much it crushed the whole
# `bot.BEAST_MARGIN` curve flat (margin 5 read 2.0% player win). At +1 the margin spans 5.5-10.9% and
# is a real dial again — the boost had to come down for when-to-beast to mean anything.
BEAST_BOOST = 1


@dataclass
class DuelState:
    stage: int = 0
    stakes: Card | None = None  # the prize card for this showdown
    challenge: str | None = None  # the contested stat: force / agility / intellect
    background: str | None = None  # the contested element
    # The place the showdown is fought in — flavour only. Drawn from the pool of the element the
    # duelist named, off the seeded RNG, so a seed replays the same board. Never touches scoring.
    background_name: str | None = None
    player_priority: bool | None = None  # who names the challenge (None = tie → coin toss)
    player: Duelist = field(default_factory=Duelist)
    bot: Duelist = field(default_factory=Duelist)
    # How many Wu each duelist must field, all at once, in the one battle. Named by the duelist who
    # did NOT call the challenge — you set the terms, I set the price — and capped by what both can
    # actually play. A tournament does not ask: it is always one Wu in each of its three battles.
    wager: int = 1
    rounds: list[Round] = field(default_factory=list)  # the battles fought, in order
    winner: bool | None = None  # True = player won, False = bot won
    winner_character: str | None = None
    card_won: bool = False
    # The stat the BOT's training raised when this loss filled its bar, for the screen to report.
    # The player's payout is never taken here — the temple offers them the choice instead.
    bot_trained: str | None = None
    # Chase Young's Beast Form (see logic/bot.choose_beast_form): the stat he boosts +3 this showdown.
    # When set, his fielded Wu score NOTHING (offence_negated) — he wagers them, never wields them.
    beast_stat: str | None = None
    # Chase won the Wu and handed it to the duelist he beat ("The Good Guys Finish Last", see
    # `_award_prize`). Recorded rather than re-derived: the screen must not have to know which of his
    # two modes gives the prize back, and the player cannot see it happen — the Wu simply arrives.
    prize_gifted: bool = False
    # The Wu the wear rule vaulted as this showdown ended — (name, was the player's, points paid) —
    # for the screen to report (see logic/wear.py).
    worn_out: list[tuple[str, bool, int]] = field(default_factory=list)
    # Which of the four routes claimed it (`mechanics.prize`), or None when nobody did and the Wu was
    # lost. Kept so the board can say *how* it was won: a card that simply appears teaches nothing.
    prize_route: PrizeRoute | None = None
    # A "Serpent's Tail" (play/−1) played by *either* duelist voids the elemental bonus for the whole
    # showdown — a condition of the duel, not of the queue it was played into. It carries across
    # every round: the ground stays intangible once someone makes it so.
    elemental_bonus_cancelled: bool = False
    elemental_bonus_reversed: bool = False  # a Celestial Dial: resonance and opposition swap all match

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
    stat: Callable[[list[str]], Awaitable[str]]  # an Orb/Curse Wu's stat (given the three)


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

        Priority is ``None`` only on a tie, which :meth:`_commitment` settles with a coin — unless a
        Mind Reader Conch was spent, in which case the player already answered and neither the sums
        nor the coin get a say. The answer is spent by :meth:`_end`, not here: a showdown opened and
        retreated from has not delivered it yet.
        """
        duel = DuelState()
        duel.player.initiative, duel.bot.initiative = initiative(self.state.player, self.state.bot)
        if self.state.initiative_contested:
            pass  # both reached for it — player_priority stays None, so `_commitment` throws the coin
        elif self.state.forced_priority is not None:
            duel.player_priority = self.state.forced_priority
        elif duel.player.initiative != duel.bot.initiative:
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

    # --- the shape of the challenge ---------------------------------------------------------
    def _is_tournament(self) -> bool:
        return self.duel.challenge == TOURNAMENT

    def _battles(self) -> int:
        """One battle for a stat challenge; three for a tournament, a stat apiece."""
        return TOURNAMENT_BATTLES if self._is_tournament() else 1

    def _wu_per_battle(self) -> int:
        """A tournament fields one Wu a battle. A stat challenge fields the whole wager, at once."""
        return 1 if self._is_tournament() else self.duel.wager

    def _total_wu(self) -> int:
        """Everything this showdown will cost you. Three, at the very most, either way."""
        return self._battles() * self._wu_per_battle()

    def _fielded(self) -> int:
        return sum(battle.fielded for battle in self.duel.rounds)

    def _stat_of(self, battle_index: int) -> str:
        """What the battle at ``battle_index`` contests.

        A tournament walks the stats left to right, in the order the card prints them: force, then
        agility, then intellect. A stat challenge contests its one stat, once.
        """
        if not self._is_tournament():
            return self.duel.challenge or ""
        stats = list(self.duel.stakes.stats.keys()) if self.duel.stakes else []
        return stats[battle_index] if battle_index < len(stats) else ""

    def _next_stage(self) -> int:
        """The showdown walks 1..5, except that Boost and Card loop once per Wu that must be fielded.

        Every Wu goes down as a boost-then-Wu pair, so Card falls back to Boost until the showdown's
        whole cost has been paid — three Wu into one battle, or one Wu into each of three. Only when
        nothing is left to field does Resolvement weigh it.
        """
        stage = self.duel.stage
        if stage == CARD and self._fielded() < self._total_wu():
            return BOOST
        return 0 if stage >= LAST_STAGE else stage + 1

    # --- stages ---------------------------------------------------------------------------
    async def _commitment(self) -> None:
        self.duel.stakes = self.state.card_deck.pop(0)
        if self.duel.player_priority is None:  # tie → a fair coin decides who leads
            self.duel.player_priority = self.rng.choice([True, False])
        # only when the bot leads does it name the challenge here; a leading player waits for stage 2
        if not self.duel.player_priority:
            # A Prognosis Conch already pinned the bot's challenge when it was spent — read, and set
            # in stone. Otherwise the bot names it fresh from its hand now.
            self.duel.challenge = self.state.locked_challenge or bot.choose_challenge(
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
            if not self._is_tournament():
                self.duel.wager = bot.choose_wager(
                    self._wager_options(), self.state.bot.whole_hand, self.state.player.whole_hand,
                )
        else:  # the bot led and chose the challenge at stage 1; the player answers the background
            self.duel.background = await self.choices.background(self._background_options())
            if not self._is_tournament():
                self.duel.wager = await self.choices.wager(self._wager_options())
        self.duel.background_name = self._draw_place(self.duel.background)
        # Chase Young decides now, the challenge known: go Beast Form (+2 on one stat, his Wu all
        # dead) or field his Wu as an ordinary duelist and keep the prizes he wins. Chase ALONE.
        # Beast Form is once a fight — in a tournament he still boosts only one of the three stats.
        if self._is_chase(self.state.bot) and self.duel.challenge:
            contested = self._stat_names() if self._is_tournament() else [self.duel.challenge]
            self.duel.beast_stat = bot.choose_beast_form(
                self.state.bot, self.state.player, contested
            )

    def _can_field(self) -> int:
        """The most Wu both duelists could actually put down. Neither may be asked for more."""
        return min(len(self.state.player.hand), len(self.state.bot.hand), self.settings.max_wager)

    def _wager_options(self) -> list[int]:
        """How many Wu go into the battle — named by whoever did NOT call the challenge.

        You set the terms, I set the price. They all land at once, so this is the width of the field,
        not a number of exchanges. Capped by what *both* can field: a wager one duelist cannot answer
        is not a wager, it is a forfeit.

        A tournament never asks. Its three battles cost one Wu each, and that is the whole of it.
        """
        return list(range(1, max(1, self._can_field()) + 1))

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
        # A battle opens only when there is no room left in the last one: a wagered stat challenge
        # lays all its Wu into a single battle, a tournament opens a fresh one for each.
        if not self.duel.rounds or self.duel.round.fielded >= self._wu_per_battle():
            self.duel.rounds.append(Round(stat=self._stat_of(len(self.duel.rounds))))
            # Beast Form: Chase's fielded Wu score nothing — he wagers them, never wields them. The
            # existing offence-negated path zeroes his played Wu and strikes them on the board.
            if self.duel.beast_stat is not None:
                self.duel.round.bot.offence_negated = True

        # Gong Yi Tanpai: both duelists choose against the ground as it stands *now*, and neither
        # sees what the other laid this stage. The opponent reads the frozen copy, so the order the
        # code happens to run in cannot leak the player's choice into theirs.
        blind = deepcopy(self.duel.round)

        player_card = await self.choices.boost(self._boost_options(self.state.player, is_player=True))
        if player_card is not None:
            # A Morpher spent as a boost still chooses its element; any other boost ignores the ask.
            self._commit_boost(player_card, is_player=True, element=await self._element_for(player_card))

        # In Beast Form Chase lays no boost — his Wu never lift, never curse, never score. Outside it
        # he boosts like anyone. `beast_stat` is set only for Chase, and only when he took the beast.
        if self.duel.beast_stat is None:
            bot_boosts = self._boost_options(self.state.bot, is_player=False)
            chosen = bot.choose_boost(
                blind, self._ground(), bot_boosts, self._playable(self.state.bot, is_player=False)
            )
            if chosen is not None:
                self._commit_boost(chosen, is_player=False, element=self.duel.background or "")

    async def _card(self) -> None:
        """Both duelists field one Wu, at the same moment and blind to each other.

        Gong Yi Tanpai is a simultaneous reveal: neither duelist may answer a Wu they have seen land.
        The code has to run in some order, so the opponent chooses against a frozen copy of the ground
        taken before anyone committed, and both Wu are resolved afterwards. A duelist with nothing
        left to field plays nothing and stands on their base stats.
        """
        current = self.duel.round
        blind = deepcopy(current)

        player_card: Card | None = None
        player_playable = self._playable(self.state.player, is_player=True)
        if player_playable:
            player_card = await self.choices.card(player_playable)
            self.duel.player.stakes.append(player_card)

        bot_card: Card | None = None
        bot_playable = self._playable(self.state.bot, is_player=False)
        if bot_playable:
            bot_card = bot.choose_card(blind, self._ground(), bot_playable, self.rng)
            self.duel.bot.stakes.append(bot_card)

        if player_card is not None:
            element = await self._element_for(player_card)
            stat = await self._stat_for(player_card)
            self._apply_elemental(
                resolve_played_power(current, player_card, is_player=True, element=element, stat=stat)
            )
        if bot_card is not None:
            if self.duel.beast_stat is None:
                self._resolve_bot(current, bot_card)
            else:
                # In Beast Form his Wu are NULLIFIED, not skipped: a neutral stand-in enters the
                # queue so the board strikes it to -/-/- (offence_negated, set in `_boost`) — like an
                # Emperor Scorpion's victim. It is staked (the opponent can still win it), lends
                # nothing, and casts no curse: he meets the wager but wields none of it.
                current.bot.queue.append(stand_in(bot_card))

        current.fielded += 1
        # Score only once the battle is full — a wagered field is weighed as a whole, not per Wu.
        if current.fielded >= self._wu_per_battle():
            self._score_round(current)

    def _apply_elemental(self, effect: str | None) -> None:
        """A played Wu's showdown-wide elemental effect: void, reverse, or re-colour the arena."""
        if effect and effect.startswith("background:"):
            self.duel.background = effect.split(":", 1)[1]
        elif effect == "cancel":
            self.duel.elemental_bonus_cancelled = True
        elif effect == "reverse":
            self.duel.elemental_bonus_reversed = True

    def _resolve_bot(self, current: Round, card: Card) -> None:
        stat = bot.choose_stat(current, self._ground(), card) if names_a_stat(card.power) else None
        self._apply_elemental(
            resolve_played_power(current, card, is_player=False, element=self.duel.background or "", stat=stat)
        )

    def _ground(self) -> Ground:
        """The terms this battle is fought under — what the scorer and the bot both read."""
        return Ground(
            stats=list(self.duel.stakes.stats.keys()) if self.duel.stakes else [],
            background=self.duel.background or "",
            player_stats=self.state.player.character.stats,
            bot_stats=self._bot_base(),
            bonus_cancelled=self.duel.elemental_bonus_cancelled,
            bonus_reversed=self.duel.elemental_bonus_reversed,
            # Priority is the last word on a battle nothing else can separate — held by whoever called
            # the challenge (settled by initiative, or the coin on a tie). A Prognosis Conch splits
            # the two: the opponent leads and names the stat, but its caster keeps the ground.
            challenger_is_player=(
                self.state.conch_tiebreak
                if self.state.conch_tiebreak is not None
                else bool(self.duel.player_priority)
            ),
        )

    def _bot_base(self) -> dict[str, int]:
        """The bot's base stats — Chase's Beast Form adds +2 to the stat it named, in the ONE battle
        that contests it. Like a boost: once a showdown, one stat, one battle (a tournament's other
        two legs see the plain 7/7/7).

        On the BASE, so it is element-free by nature: it earns no arena bonus and no elemental counter
        can touch it (they act on the elemental bonus, which a base stat never carries).
        """
        base = dict(self.state.bot.character.stats)
        contested = self.duel.round.stat if self.duel.rounds else self.duel.challenge
        if self.duel.beast_stat is not None and self.duel.beast_stat == contested:
            base[self.duel.beast_stat] += BEAST_BOOST
        return base

    def _score_round(self, current: Round) -> None:
        score_battle(current, self._ground())

    async def _element_for(self, card: Card) -> str:
        """Some Wu let the player name an element: the Morpher its shape, the Eye its own colour, the
        Monsoon the whole arena's. Any other card ignores the ask and takes the background."""
        if mechanic_of(card.power) in _CHOOSES_ELEMENT:
            return await self.choices.element(self.duel.background or "")
        return self.duel.background or ""

    async def _stat_for(self, card: Card) -> str | None:
        """The Orb and the Curse are told which stat to pour into; every other Wu already knows."""
        if names_a_stat(card.power):
            return await self.choices.stat(self._stat_names())
        return None

    def _stat_names(self) -> list[str]:
        """The three stats, in the order a card prints them."""
        return list(self.state.player.character.stats)

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

        self._award_prize()

    async def _end(self) -> None:
        self.state.previous_challenge = [self.duel.challenge] if self.duel.challenge else []
        self.state.previous_background = [self.duel.background] if self.duel.background else []
        # The action counters are NOT reset here. A turn turns over in `turn.refill_hands`, which runs
        # after the opponent has taken theirs — and which may spend the coming turn's action for you,
        # by dealing you back in. Reset here and that charge would be wiped before it ever bit.
        self.state.bot_turn_done = False  # a new temple turn, for both of you
        self.state.forced_priority = None  # the Conch's answer was for this showdown, and is spent
        self.state.locked_challenge = None  # the Prognosis pin was for this showdown too
        self.state.conch_tiebreak = None
        self.state.initiative_contested = False  # the contest, if any, was settled by this showdown's coin
        if not self.state.card_deck:
            self.state.has_ended = True

        # the loser gives up every card they staked this showdown; the winner takes them — fresh,
        # since a Wu's wear belongs to the duelist who used it (see logic/wear.py)
        winner, loser = self._winner_and_loser()
        for card in self.duel.duelist(not self.duel.winner).stakes:
            loser.remove_card(card)
            winner.hand.append(hand_over(card))

        # losing teaches: the loser's training bar gains one (see logic/training.py). The bot
        # cashes a full bar on the spot; the raised stat is kept for the screen to report.
        self.duel.bot_trained = record_showdown(self.state, player_won=bool(self.duel.winner))

        # wear: every Wu committed this showdown and still held wears by one, and the worn-out are
        # vaulted for their points on the spot (see logic/wear.py). Kept for the screen to report.
        for is_player in (True, False):
            side = self.duel.duelist(is_player)
            vaulted = wear.record_showdown(
                self.state.duelist(is_player), side.stakes + side.boosts_spent, rng=self.rng
            )
            self.duel.worn_out += [(card.name, is_player, paid) for card, paid in vaulted]

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
        """What the challenger may call: a stat, or the tournament that calls all three.

        A tournament costs three Wu, one per battle, so it is only on the table when *both* duelists
        can field three — like any wager, a challenge the other cannot answer is not a challenge.
        """
        stats = self.duel.stakes.stats.keys() if self.duel.stakes else ()
        options = [s for s in stats if s not in self.state.previous_challenge]
        if (
            TOURNAMENT not in self.state.previous_challenge
            and min(len(self.state.player.hand), len(self.state.bot.hand)) >= TOURNAMENT_BATTLES
        ):
            options.append(TOURNAMENT)
        return options

    def _background_options(self) -> list[str]:
        return [e for e in ELEMENTS if e not in self.state.previous_background]

    def _boost_options(self, player: Player, *, is_player: bool) -> list[Card]:
        """Boost Wu still available — every Wu fielded may carry one, and each must be a different Wu.

        A boost is spent once a showdown, not once a battle. So a three-Wu field can be boosted three
        times, but only by a duelist holding three distinct boost Wu — you cannot lift the whole field
        with one dragon. And a Wu is spent whichever slot it went into: fielded as an ordinary Wu, it
        is gone, and cannot come back to boost the next one.
        """
        duelist = self.duel.duelist(is_player)
        unused = excluding(player.whole_hand, duelist.boosts_spent + duelist.stakes)
        available = [card for card in unused if is_boost_slot(card.power)]

        # You still owe a Wu for every one not yet fielded. Boosting with one out of HAND spends a Wu
        # you would have put down, so it is only offered while you can still cover what you owe. A Wu
        # in the inalienable slot is never fieldable as a card, so it always costs you nothing.
        owed = self._total_wu() - self._fielded()
        if len(self._playable(player, is_player=is_player)) > owed:
            return available
        return excluding(available, player.hand)

    def _playable(self, player: Player, *, is_player: bool) -> list[Card]:
        """Wu that may still be fielded as a card. The hand only — the inalienable Wu is boost-only."""
        return excluding(player.hand, self.duel.duelist(is_player).stakes)

    def _commit_boost(self, card: Card, *, is_player: bool, element: str) -> None:
        duelist = self.duel.duelist(is_player)
        mine, _theirs = self.duel.round.sides(is_player)
        player = self.state.player if is_player else self.state.bot
        # What cannot be lost is what sits in the inalienable slot — *not* every Wu that boosts. A
        # wudai weapon found in the pile boosts exactly like the one a character was born holding,
        # and is staked like anything else you carry: win it, lose it, bank it.
        if not is_one_of(card, player.inalienable_hand):
            duelist.stakes.append(card)
        duelist.boosts_spent.append(card)  # one showdown, one use — even a dragon
        # A dragon/amplifier keeps its unresolved slot — what it lends is not known until it sees the
        # Wu it lifts. A Morpher resolves here instead: 0 on the contested stat, MORPH_BOOST on the
        # rest, so in tune it NETS 1/1/1 (see `as_boost`).
        mine.queue.append(as_boost(card, element, self._stat_of(self.duel.round_number - 1)))

    @staticmethod
    def _is_chase(player: Player) -> bool:
        """Whether this duelist gifts a won prize — Chase Young, the boss who refuses the Wu."""
        return mechanic_of(player.character.power) is Mechanic.BEAST_FORM

    def _winner_and_loser(self) -> tuple[Player, Player]:
        if self.duel.winner:
            return self.state.player, self.state.bot
        return self.state.bot, self.state.player

    def _award_prize(self) -> None:
        """Winning settles who keeps their own Wu. Taking the revealed one has to be *earned*.

        Four routes, in :mod:`.mechanics.prize` — a decisive blow, a broad win, total command, or
        having fought in tune with the arena. Fail all four and the Wu is **lost**, not destroyed.
        """
        winner, loser = self._winner_and_loser()
        self.duel.winner_character = winner.character.name
        if not self.duel.stakes:
            self.duel.card_won = False
            return

        self.duel.prize_route = claim_route(
            self.duel.rounds,
            winner_is_player=bool(self.duel.winner),
            background=self.duel.background or "",
            threshold=self.settings.prize_threshold,
            bonus_cancelled=self.duel.elemental_bonus_cancelled,
        )
        self.duel.card_won = self.duel.prize_route is not None
        if self.duel.card_won:
            # "The Good Guys Finish Last": a WU-PLAY win gives the prize to the duelist Chase beat —
            # he fought them as a duelist and hands the trophy back. A Beast-Form win keeps it: in
            # the beast his Wu are dead weight, so a Wu he takes is one he cannot wield, banked and
            # denied rather than wielded. He could spend them at the temple; he simply never wants to.
            # `card_won` stays true — a route was earned — so the log still reads a win; only the
            # taker changes.
            #
            # This way round because the beast was paying twice: it deadens his Wu AND forfeited the
            # prize, so it was never the right call and beasting more only made him weaker (margin 0
            # 1.5% player win, always-beast 8.5%). A mode that is always wrong is not a choice.
            gifts = self._is_chase(winner) and self.duel.beast_stat is None
            self.duel.prize_gifted = gifts
            takes_prize = loser if gifts else winner
            takes_prize.hand.append(self.duel.stakes)
        else:
            # Lost, not destroyed. It leaves play, and one day it can surface again — which is what
            # the Rooster Booster reaches for. Until that card exists, nothing reads this pile.
            self.state.lost.append(self.duel.stakes)
