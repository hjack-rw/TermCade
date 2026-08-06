"""The showdown — a 7-stage machine in a pure, injectable form.

A duel is a *loop of showdowns* over the shared draw pile until it runs dry. One showdown walks
stages 1→6 then a closing stage 0:

    1 Commitment   → draw the prize card; a tied initiative is settled by a coin toss here
    2 Setup        → challenge, wager and arena are decided
    3 Boost        → each duelist may lay a boost Wu ahead of the Wu they are about to field
    4 Card         → both field one Wu, blind to each other; :mod:`.mechanics.resolve` resolves both
    5 Resolvement  → weigh the battles, decide the winner, maybe award the prize card
    0 End          → the loser's staked cards change hands; reset for the next showdown

Boost→Card loops once per Wu owed this showdown (one to three), each Wu optionally preceded by a
boost, and no boost Wu serves twice.

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
from ..schema.constants import BRAWL, ELEMENTS, TOURNAMENT, TOURNAMENT_BATTLES
from .battle import Duelist, Ground, Round, score_battle, score_brawl
from ..mechanics.cards import excluding, is_one_of
from ..mechanics.powers import (
    BEAST_BOOST, CHAMELON_MARGIN, Mechanic, chooses_element, is_boost_slot, is_jong_bane,
    is_uncontrolled, mechanic_of, names_a_stat,
)
from ..mechanics.prize import PrizeRoute, claim_route
from ..mechanics.resolve import as_boost, curse_from_boost, resolve_played_power, stand_in
from ..mechanics.scoring import element_score, initiative
from ..schema.models import Card, Player, Power
from ..config.settings import XiaolinSettings
from .summons import jong_form, summon_name
from ..characters import chase, hannibal, jack, jong
from ..schema.state import XiaolinState
from .training import record_showdown
from . import wear
from .wear import hand_over

END, COMMITMENT, SETUP, BOOST, CARD, RESOLVEMENT = range(6)
LAST_STAGE = RESOLVEMENT  # the showdown cycles stages 0..5, but BOOST..CARD repeats per Wu wagered

# The summon-flavour pools and their resolvers live in :mod:`.summons`; the duel passes the two
# characters and the arena, and shows the name they return in place of the Wu's own.

# Chase Young's Beast Form bonus on the contested stat (see `_award_prize` for the prize side-effect).
# Defined in `mechanics.powers` (`mechanic_config`'s `beast_form.boost`) and re-exported by the
# import above, so the DB is read in one place.

# How far above parity Chamelon-Bot closes the gap when the player leads (see `_chamelon_boost_card`).
# Defined in `mechanics.powers` and re-exported by the import above, so the DB is read in one place.


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
    # How many Wu each duelist must field, all at once, in the one battle (see `_wager_options`).
    wager: int = 1
    # Jack-bots Attack!'s own wager: each side 0-3, decided independently and blind to the other —
    # `wager` above stays unused for it. `None` unless `jack_mode is jack.ATTACK_NAME`.
    player_wager: int | None = None
    bot_wager: int | None = None
    rounds: list[Round] = field(default_factory=list)  # the battles fought, in order
    winner: bool | None = None  # True = player won, False = bot won
    # A WISH card was fielded: that side wins the showdown outright, whatever the battles said.
    # ``None`` is the ordinary game, decided on the ground. Spent with the showdown.
    auto_winner: bool | None = None
    winner_character: str | None = None
    card_won: bool = False
    # The stat the BOT's training raised when this loss filled its bar, for the screen to report.
    # The player's payout is never taken here — the temple offers them the choice instead.
    bot_trained: str | None = None
    # Chase Young's Beast Form (see characters/chase.choose_beast_form): the stat BEAST_BOOST lands on.
    # When set, his fielded Wu score NOTHING (offence_negated) — see `_boost`.
    beast_stat: str | None = None
    # Chase gifted the prize to the loser this showdown (see `_award_prize`). Recorded rather than
    # re-derived: the screen doesn't need to know which of his modes triggers it.
    prize_gifted: bool = False
    # The Wu the wear rule vaulted as this showdown ended — (name, was the player's, points paid) —
    # for the screen to report (see logic/flow/wear.py).
    worn_out: list[tuple[str, bool, int]] = field(default_factory=list)
    # Which of the four routes claimed it (`mechanics.prize`), or None when nobody did and the Wu was
    # lost. Kept so the board can report how it was won.
    prize_route: PrizeRoute | None = None
    # Jack conceded this showdown rather than pay its normal cost (see `jack.choose_to_flee`) — the
    # prize still resolves through the normal ladder in `_award_prize`, unaffected; the only thing
    # this spares him is his own wager, in `_end`. Decided once, in `_resolvement`, the moment he is
    # confirmed the loser.
    jack_fled: bool = False
    # AI Jack's steal, named for the Game Log — set once the theft actually happens (see
    # `_resolve_ai_jack_steal`), never at mode selection. `None` when nothing was stolen: the mode
    # never fired, or the opponent's hand and deck were both already empty.
    jack_stolen: str | None = None
    # Voids the elemental bonus for the rest of the showdown once played by either side — a duel-wide
    # condition, not scoped to the round it was played into.
    elemental_bonus_cancelled: bool = False
    elemental_bonus_reversed: bool = False  # swaps resonance/opposition for the rest of the showdown
    # Jack-Bot's flavour name this cycle (see characters/jack.choose_jack_bot), one of
    # `jack.JACK_BOT_NAMES` — chosen fresh whenever he deploys it, `None` otherwise.
    jack_bot_name: str | None = None
    # Jack Spicer's identity swap (see characters/jack.choose_jack_mode): `jack.AI_JACK_NAME`,
    # `jack.CHAMELON_NAME`, `jack.ATTACK_NAME`, or `None` fighting as himself — decided once, at
    # commitment. IS the shown name for the first two (no flavour on top); Attack!'s own shown name
    # rotates through `jack.ATTACK_BOT_NAMES` instead, held in `attack_bot_name` below.
    jack_mode: str | None = None
    # Attack!'s flavour name for this showdown — one of `jack.ATTACK_BOT_NAMES`, never twice in a
    # row (see `state.last_attack_bot_name`). `None` unless `jack_mode is jack.ATTACK_NAME`.
    attack_bot_name: str | None = None
    # The Yin/Yang Yo-Yo (Mechanic.STAT_SWAP): which Character stats are currently exchanged between
    # the two duelists, this showdown only — read live in `Duel._swapped_bases`, not applied once at
    # play time, the same reason `boost_negated`/`conduct_caster` read live too. Resets every
    # showdown; the affiliation flip it also causes outlives this (see `Player.yoyo_flipped`).
    swapped_stats: set[str] = field(default_factory=set)
    # The PLAYER'S OWN affiliation just flipped this stage — for the toast (see
    # `screens/duel._announce_yoyo_flip`), the same one-shot shape as `jack_stolen`. Never set for
    # the bot's own flip (including Jack becoming Good Jack) — nothing to say text for yet.
    yoyo_flipped_announce: bool = False

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


@dataclass(frozen=True)
class AmendOptions:
    """What a fielded Hodoku Mouse may rewrite in the current round — the terms still open to it."""

    stats: list[str]  # switch the contest to one of these (the stats it does not already contest)
    elements: list[str]  # switch the arena to one of these (the elements it is not already)
    can_take_ground: bool  # take the challenger's ground — offered only when the player lacks it
    wagers: list[int]  # raise the stake to one of these counts (a stat challenge only, never lower)
    swap_out: list[Card]  # a Wu of yours already fielded this battle, that a hand Wu could replace
    swap_in: list[Card]  # a plain Wu in hand that could take a fielded one's place


@dataclass(frozen=True)
class Amend:
    """One rewrite of the current round, chosen by the player who fielded the Mouse.

    ``kind`` names the term; the rest carry its new value — ``value`` for the scalar terms (a stat, an
    element, a wager count), ``swap_out``/``swap_in`` for the fielded-Wu swap.
    """

    kind: str  # "challenge" | "background" | "initiative" | "wager" | "swap"
    value: str = ""
    swap_out: Card | None = None
    swap_in: Card | None = None


# The default when a DuelChoices is built without an amend answerer (every headless caller): decline.
# Only the real duel screen overrides it, so tests and the balance harness need not know the Mouse.
async def _decline_amend(_: AmendOptions) -> Amend | None:
    return None


async def _decline_counter(_: list[Card]) -> Card | None:
    # The default balance answerer (headless callers): field no extra Wu against a boosted Heart of Jong.
    return None


def _is_plain_fighter(card: Card) -> bool:
    """A Wu the Mouse may swap into the field cleanly: real printed stats, none negative (no curse to
    mirror onto the opponent) and not a boost-only Wu. Its stats are the whole of it, so it simply
    takes a fielded Wu's place — no boost or curse in the queue to unwind."""
    values = list(card.stats.values())
    return all(v is not None and v >= 0 for v in values) and any(values) and not is_boost_slot(card.power)


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
    # A fielded Hodoku Mouse: rewrite one term of the round, or ``None`` to decline. Defaulted so only
    # the duel screen — the one caller with a Mouse to play — must supply it.
    amend: Callable[[AmendOptions], Awaitable["Amend | None"]] = _decline_amend
    # A boosted Heart of Jong on the far side: field one extra Wu to answer its summon, or ``None`` to
    # pass. Off-wager — it scores but is never staked. Defaulted, like amend, so only the duel screen cares.
    counter: Callable[[list[Card]], Awaitable[Card | None]] = _decline_counter


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

    def _wager_targets(self) -> tuple[int, int]:
        """How many Wu each side must field this round — (player, bot).

        Symmetric for every showdown but Jack-bots Attack!, the one place the two diverge — each
        side owes its own independently-chosen 0-3, one possibly owing zero while the other owes
        three.
        """
        if self.duel.jack_mode == jack.ATTACK_NAME:
            return self.duel.player_wager or 0, self.duel.bot_wager or 0
        per_side = self._wu_per_battle()
        return per_side, per_side

    def _total_wu(self) -> tuple[int, int]:
        """Everything this showdown will cost each side, across every battle. Three, at most, either way."""
        battles = self._battles()
        player_target, bot_target = self._wager_targets()
        return battles * player_target, battles * bot_target

    def _fielded(self) -> tuple[int, int]:
        """Wu each side has fielded so far this showdown, summed across every battle fought."""
        return (
            sum(battle.player_fielded for battle in self.duel.rounds),
            sum(battle.bot_fielded for battle in self.duel.rounds),
        )

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
        if stage == CARD:
            player_fielded, bot_fielded = self._fielded()
            player_total, bot_total = self._total_wu()
            if player_fielded < player_total or bot_fielded < bot_total:
                return BOOST
        return 0 if stage >= LAST_STAGE else stage + 1

    # --- stages ---------------------------------------------------------------------------
    async def _commitment(self) -> None:
        self.duel.stakes = self.state.card_deck.pop(0)
        if self.duel.player_priority is None:  # tie → a fair coin decides who leads
            self.duel.player_priority = self.rng.choice([True, False])
        self._choose_jack_mode()
        # only when the bot leads does it name the challenge here; a leading player waits for stage 2.
        # Attack! already set BRAWL above — nobody names it, so this must not overwrite that.
        if not self.duel.player_priority and self.duel.jack_mode != jack.ATTACK_NAME:
            # state.locked_challenge, if already set, overrides a freshly-chosen one.
            self.duel.challenge = self.state.locked_challenge or bot.choose_challenge(
                jong.battle_stats(self.state.bot),
                self._challenge_options(),
                self.state.bot.whole_hand,
                jong.battle_stats(self.state.player),
                self.rng,
            )

    async def _setup(self) -> None:
        if self.duel.jack_mode == jack.ATTACK_NAME:
            await self._setup_brawl()
            return
        # The arena is either a random roll neither duelist chose (revealed after the wager) or the
        # non-challenger's pick — settings.random_background decides; the wager is named either way.
        random_bg = bool(self.settings.random_background)
        if self.duel.player_priority:
            self.duel.challenge = await self.choices.challenge(self._challenge_options())
            if not random_bg:
                # Real stats, never `_jack_base()`: the heuristic rewards a background that plays to
                # the bot's OWN comparative stat edge (`bot_stats[stat] - opponent_stats[stat]`) — under
                # Chamelon-Bot's mirror that edge is zero on every stat, and the pick degrades to a
                # near-random fallback. The mirror belongs on the battle score alone (`_bot_base`).
                self.duel.background = bot.choose_background(
                    jong.battle_stats(self.state.bot),
                    self._background_options(),
                    (self.state.bot.whole_hand, self.state.player.whole_hand),
                    jong.battle_stats(self.state.player),
                    self.rng,
                )
            if not self._is_tournament():
                self.duel.wager = bot.choose_wager(
                    self._wager_options(), self.state.bot.whole_hand, self.state.player.whole_hand,
                )
        else:  # the bot led and chose the challenge at stage 1; the player answers the terms
            if not random_bg:
                self.duel.background = await self.choices.background(self._background_options())
            if not self._is_tournament():
                self.duel.wager = await self.choices.wager(self._wager_options())
        if random_bg:  # the arena is a roll neither duelist chose, revealed once the wager is set
            self.duel.background = self.rng.choice(list(ELEMENTS))
        self.duel.background_name = self._draw_place(self.duel.background)
        # Chase decides Beast Form once, here, for the whole showdown — even in a tournament, only
        # one of the three stats gets it. Skipped for a construct: Mala Mala Jong fights as its own
        # body, not through his character power.
        if bot.is_chase(self.state.bot) and self.duel.challenge and not bot.is_jong(self.state.bot):
            contested = self._stat_names() if self._is_tournament() else [self.duel.challenge]
            self.duel.beast_stat = chase.choose_beast_form(
                self.state.bot, self.state.player, contested
            )

    async def _setup_brawl(self) -> None:
        """Jack-bots Attack!'s own setup — shaped differently from a normal showdown.

        No challenge to ask for (`_choose_jack_mode` already set BRAWL). The element is always
        explicitly picked by the non-challenger, never `settings.random_background`'s roll, and gets
        no named place. Each side wagers independently, 0-3, blind to the other — decided one stage
        earlier than usual, since no wager sets the terms for the other's.
        """
        if self.duel.player_priority:
            # The generic heuristic weighs Wu elements in hand — it has no way to know picking metal
            # is worth a guaranteed +1 on all three of HIS OWN stats (see `_jack_base`), a far bigger
            # lever than any hand it could be holding. Take it directly rather than asking.
            options = self._background_options()
            self.duel.background = "metal" if "metal" in options else bot.choose_background(
                self._jack_base(), options,
                (self.state.bot.whole_hand, self.state.player.whole_hand),
                jong.battle_stats(self.state.player), self.rng,
            )
        else:
            self.duel.background = await self.choices.background(self._background_options())
        self.duel.background_name = None
        self.duel.player_wager = await self.choices.wager(self._brawl_wager_options(is_player=True))
        self.duel.bot_wager = bot.choose_wager(
            self._brawl_wager_options(is_player=False), self.state.bot.whole_hand,
            self.state.player.whole_hand,
        )

    def _brawl_wager_options(self, *, is_player: bool) -> list[int]:
        """One side's wager for Attack! — 0 up to that side's own hand, capped by ``max_wager``,
        independent of the other's. Zero is legal (see ``docs/design/BOSSES.md``)."""
        hand_size = len(self.state.player.hand if is_player else self.state.bot.hand)
        return list(range(0, min(hand_size, self.settings.max_wager) + 1))

    def _can_field(self) -> int:
        """The most Wu both duelists could actually put down. Neither may be asked for more."""
        return min(len(self.state.player.hand), len(self.state.bot.hand), self.settings.max_wager)

    def _wager_options(self) -> list[int]:
        """How many Wu options to offer — named by whoever did NOT call the challenge, capped by what
        both duelists can field. A tournament never asks: each of its battles costs one Wu."""
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
        player_target, bot_target = self._wager_targets()
        if not self.duel.rounds or (
            self.duel.round.player_fielded >= player_target and self.duel.round.bot_fielded >= bot_target
        ):
            self.duel.rounds.append(Round(stat=self._stat_of(len(self.duel.rounds))))
            # Beast Form: route through the existing offence-negated path so Chase's played Wu score
            # nothing.
            if self.duel.beast_stat is not None:
                self.duel.round.bot.offence_negated = True
            self.duel.round.player.is_construct = self._is_construct(self.state.player)
            self.duel.round.bot.is_construct = self._is_construct(self.state.bot)

        # Simultaneous choice: neither side sees what the other lays this stage. The opponent reads a
        # frozen copy of the ground so execution order can't leak the player's pick into theirs.
        blind = deepcopy(self.duel.round)

        player_card = await self.choices.boost(self._boost_options(self.state.player, is_player=True))
        if player_card is not None:
            # A Morpher spent as a boost still chooses its element; any other boost ignores the ask.
            self._commit_boost(player_card, is_player=True, element=await self._element_for(player_card))

        # In Beast Form Chase lays no boost. `beast_stat` is set only for Chase, and only when he
        # took the beast.
        if self.duel.beast_stat is None:
            bot_boosts = self._boost_options(self.state.bot, is_player=False)
            # Jack-Bot is his own permanent boost, not one of the three he swaps INTO — while he's
            # sent AI Jack, Chamelon-Bot or the Attack! construct instead, it stays undeployed.
            jack_bot = None
            # Good Jack can't deploy Jack-Bot either — `_is_construct` alone misses this: he sets no
            # `jack_mode` while worn, so he never reads as a construct, correctly (see `_jack_base`).
            if not self._is_construct(self.state.bot) and not self.state.bot.yoyo_flipped:
                jack_bot = next((c for c in bot_boosts if mechanic_of(c.power) is Mechanic.BOT), None)
            # Chamelon-Bot's denial is a boost, not a base override (see `_chamelon_boost_card`) —
            # so it can be weighed by the same reach-comparison as any real boost, not preferred
            # over them by default.
            chamelon_card = self._chamelon_boost_card()
            if chamelon_card is not None:
                bot_boosts = [*bot_boosts, chamelon_card]
            if jack_bot is not None and jack.choose_jack_bot(self.duel.round.player):
                self._pick_jack_bot_name()
                self._commit_boost(jack_bot, is_player=False, element=self.duel.background or "")
            else:
                chosen = bot.choose_boost(
                    blind, self._ground(), bot_boosts, self._playable(self.state.bot, is_player=False)
                )
                if chosen is not None:
                    self._commit_boost(chosen, is_player=False, element=self.duel.background or "")

    async def _card(self) -> None:
        """Both duelists field one Wu at the same moment, blind to each other.

        Execution has to run in some order, so the opponent chooses against a frozen copy of the
        ground taken before anyone committed; both Wu resolve afterward. A duelist with nothing left
        to field plays nothing and stands on base stats.
        """
        current = self.duel.round
        blind = deepcopy(current)
        player_target, bot_target = self._wager_targets()

        # Gated on what's still OWED, not on what's playable: a duelist out of cards still owes the
        # cycle (they "stand on their base stats", per above) and must still be counted as fielded, or
        # the loop above never sees them catch up. Jack-bots Attack! is the only showdown where the two
        # targets can differ at all — everywhere else this is exactly the old shared-counter behaviour.
        player_card: Card | None = None
        player_playable = self._playable(self.state.player, is_player=True)
        if current.player_fielded < player_target:
            if player_playable:
                player_card = await self.choices.card(player_playable)
                self.duel.player.stakes.append(player_card)
            current.player_fielded += 1

        bot_card: Card | None = None
        bot_playable = self._playable(self.state.bot, is_player=False)
        if current.bot_fielded < bot_target:
            if bot_playable:
                bot_card = bot.choose_card(
                    blind,
                    self._ground(),
                    bot_playable,
                    self.rng,
                    prize_bar=self.settings.prize_threshold + 1,
                )
                self.duel.bot.stakes.append(bot_card)
            current.bot_fielded += 1

        if player_card is not None:
            element = await self._element_for(player_card)
            stat = await self._stat_for(player_card)
            self._apply_elemental(
                resolve_played_power(
                    current, player_card, is_player=True, element=element, stat=stat,
                    display_name=self._summon_display(player_card, is_player=True),
                )
            )
        if bot_card is not None:
            if self.duel.beast_stat is None:
                self._resolve_bot(current, bot_card)
            else:
                # In Beast Form his Wu are NULLIFIED, not skipped: a neutral stand-in enters the
                # queue so the board strikes it to -/-/- (offence_negated, set in `_boost`). It is
                # staked (the opponent can still win it), lends nothing, and casts no curse.
                current.bot.queue.append(stand_in(bot_card))

        # WISH: fielded, it wins the showdown outright — the ground is overridden at Resolvement, and
        # it is exiled at the End. Either duelist's win it (the bot never fields it by policy, but the
        # rule is written for whoever does).
        if player_card is not None and mechanic_of(player_card.power) is Mechanic.WISH:
            self.duel.auto_winner = True
        if bot_card is not None and mechanic_of(bot_card.power) is Mechanic.WISH:
            self.duel.auto_winner = False
        # is_uncontrolled: fielded, it turns on its own summoner — that side loses the showdown
        # outright, the inverse of WISH. WISH outranks it: an auto-win already set stands.
        if player_card is not None and is_uncontrolled(player_card.power) and self.duel.auto_winner is None:
            self.duel.auto_winner = False
        if bot_card is not None and is_uncontrolled(bot_card.power) and self.duel.auto_winner is None:
            self.duel.auto_winner = True
        # is_jong_bane vs a constructed Jong: takes this battle only (round.bane_winner, not
        # auto_winner — a tournament leg, not the whole showdown).
        if player_card is not None and is_jong_bane(player_card.power) and bot.is_jong(self.state.bot):
            current.bane_winner = True
        if bot_card is not None and is_jong_bane(bot_card.power) and bot.is_jong(self.state.player):
            current.bane_winner = False
        # AMEND: after the reveal, lets its player rewrite one term of this round before it's
        # weighed. Fights as its own Wu too (resolved above). The bot never amends.
        if player_card is not None and mechanic_of(player_card.power) is Mechanic.AMEND:
            await self._offer_amend()
        # Score only once the battle is full — a wagered field is weighed as a whole, not per Wu.
        if current.player_fielded >= player_target and current.bot_fielded >= bot_target:
            if current.heart_summoner is not None:  # a Heart woke a summon; the far side may answer it
                await self._offer_balance(current)
            self._score_round(current)

    async def _offer_balance(self, current: Round) -> None:
        """The side opposite ``heart_summoner`` may field one off-wager Wu here to answer the summon:
        it scores like any Wu, but it is never staked and doesn't count against the wager. Optional,
        and only if they have one."""
        answerer = not current.heart_summoner
        options = self._playable(self.state.duelist(answerer), is_player=answerer)
        if not options:
            return
        if answerer:  # the player answers a bot's Heart — the screen asks
            card = await self.choices.counter(options)
        else:  # the bot answers the player's Heart
            card = bot.choose_card(
                deepcopy(current),
                self._ground(),
                options,
                self.rng,
                prize_bar=self.settings.prize_threshold + 1,
            )
        if card is None:
            return
        # Resolved into the queue so it scores, but held on off_wager, not stakes: it wears through the
        # same record_showdown path as every Wu (uses += 1, deposited at the limit), yet is never
        # forfeited to the winner — off the wager, only worn out.
        self.duel.duelist(answerer).off_wager.append(card)
        element = await self._element_for(card)
        stat = await self._stat_for(card)
        if answerer:
            self._apply_elemental(
                resolve_played_power(
                    current, card, is_player=True, element=element, stat=stat,
                    display_name=self._summon_display(card, is_player=True),
                )
            )
        else:
            self._resolve_bot(current, card)

    async def _offer_amend(self) -> None:
        """Let the player rewrite one term of the current round. Declining changes nothing."""
        choice = await self.choices.amend(self._amend_options())
        if choice is not None:
            self._apply_amend(choice)

    def _amend_options(self) -> AmendOptions:
        """What the Mouse may rewrite: the contested stat, the arena, the challenger's ground, the
        stake (raise it), or one of your fielded Wu (swap it for a plain one in hand). Swap is a stat
        challenge's alone — a tournament battle is one Wu, and that Wu is the Mouse itself."""
        raises = [] if self._is_tournament() else list(range(self.duel.wager + 1, self._can_field() + 1))
        swap_out = [] if self._is_tournament() else [
            wu for wu in self.duel.player.stakes if mechanic_of(wu.power) is not Mechanic.AMEND
        ]
        # A random arena is nobody's to set, so the Mouse cannot amend it — offer no elements then.
        elements = [] if self.settings.random_background else [e for e in ELEMENTS if e != self.duel.background]
        return AmendOptions(
            stats=[s for s in self._stat_names() if s != self.duel.round.stat],
            elements=elements,
            can_take_ground=self._ground().challenger_is_player is not True,
            wagers=raises,
            swap_out=swap_out,
            swap_in=[wu for wu in self.state.player.hand if _is_plain_fighter(wu)] if swap_out else [],
        )

    def _apply_amend(self, amend: Amend) -> None:
        """Rewrite one term of the current round in place — the next ``_score_round`` reads it. Ground
        is taken through ``conch_tiebreak``, the same field other initiative powers write."""
        if amend.kind == "challenge":
            self.duel.round.stat = amend.value
            if not self._is_tournament():
                self.duel.challenge = amend.value
        elif amend.kind == "background":
            self.duel.background = amend.value
        elif amend.kind == "initiative":
            self.state.conch_tiebreak = True  # the player takes the challenger's ground
        elif amend.kind == "wager":
            # Raise the stake into this battle: the stage machine loops Boost→Card until the new
            # count is fielded (`_wu_per_battle` reads it live). Only ever up — what is down is down.
            self.duel.wager = int(amend.value)
        elif amend.kind == "swap" and amend.swap_out is not None and amend.swap_in is not None:
            self._swap_fielded(amend.swap_out, amend.swap_in)

    def _swap_fielded(self, out_wu: Card, in_wu: Card) -> None:
        """Replace a Wu already fielded this battle with a plain one from hand: the new Wu takes the
        old one's place in the queue (its stand-in becomes the new Wu's stats), the old returns to
        hand un-staked, the new is staked in its stead. The next ``_score_round`` weighs the result."""
        queue = self.duel.round.player.queue
        stand = next(
            (c for c in queue if c.id == out_wu.id and mechanic_of(c.power) is not Mechanic.AMEND),
            None,
        )
        if stand is None or not is_one_of(in_wu, self.state.player.hand):
            return
        stand.id, stand.name = in_wu.id, in_wu.name
        stand.stats = {s: (in_wu.stats[s] or 0) for s in in_wu.stats}
        stand.element, stand.points = in_wu.element, in_wu.points
        # The two Wu change places: the pulled one back to hand, the played one out of it and onto the
        # stakes in the other's slot — so prize and wear at the end count the field as it really stands.
        self.state.player.remove_card(in_wu)
        self.state.player.hand.append(out_wu)
        self.duel.player.stakes[self.duel.player.stakes.index(out_wu)] = in_wu

    def _apply_elemental(self, effect: str | None) -> None:
        """Dispatches a played Wu's showdown-wide effect: void/reverse/recolor the arena, seize the
        ground, hack a construct, steal a Wu, set the conduct caster, or swap a stat (self or
        opponent affiliation flip, depending on which half was played)."""
        if effect and effect.startswith("background:"):
            self.duel.background = effect.split(":", 1)[1]
        elif effect == "cancel":
            self.duel.elemental_bonus_cancelled = True
        elif effect == "reverse":
            self.duel.elemental_bonus_reversed = True
        elif effect and effect.startswith("seize:"):
            self._seize_ground(effect.split(":", 1)[1] == "player")
        elif effect and effect.startswith("hack:"):
            self._hack_construct(effect.split(":", 1)[1] == "player")
        elif effect and effect.startswith("steal:"):
            self._steal_wu(effect.split(":", 1)[1] == "player")
        elif effect and effect.startswith("conduct:"):
            self.duel.round.conduct_caster = effect.split(":", 1)[1] == "player"
        elif effect and effect.startswith("swap:"):
            _, who, stat = effect.split(":", 2)
            self._swap_stat_and_flip(who == "player", stat, flip_self=True)
        elif effect and effect.startswith("chiswap:"):
            _, who, stat = effect.split(":", 2)
            self._swap_stat_and_flip(who == "player", stat, flip_self=False)

    def _swap_stat_and_flip(self, is_player: bool, stat: str, *, flip_self: bool) -> None:
        """Toggles a stat into (or out of) `swapped_stats` — read live at `_swapped_bases`, the same
        reason `conduct_caster` reads live rather than resolving once at play time, so it stays
        correct regardless of effect order.

        Also flips an affiliation for the rest of the RUN, not just this showdown
        (`Player.yoyo_flipped`) — Jack alone reads this as Good Jack (`jack.GOOD_JACK_STAT`) rather
        than a plain flip. ``flip_self`` selects which side: True for the caster's own, False for the
        opponent's (the combined half).
        """
        if stat in self.duel.swapped_stats:
            self.duel.swapped_stats.discard(stat)
        else:
            self.duel.swapped_stats.add(stat)
        caster = self.state.player if is_player else self.state.bot
        opponent = self.state.bot if is_player else self.state.player
        target = caster if flip_self else opponent
        target.yoyo_flipped = not target.yoyo_flipped
        if is_player and flip_self:
            self.duel.yoyo_flipped_announce = True

    def _conduct_bonus(self, is_player: bool) -> int:
        """The contested-stat swing from a played conductor: +1 per metal Wu on the table this
        battle, -1 per non-metal (either side's queue, boosts and curse mirrors alike; an elementless
        card counts as neither) — the decided arena follows the same rule. Zero unless ``is_player``
        is the side that cast it this battle.

        Read live off the queues rather than resolved once at play time, so a Wu fielded *after* the
        cast still counts — the same reason `boost_negated`/`defence_negated` read at scoring time
        instead of when they were set.
        """
        if not self.duel.rounds or self.duel.round.conduct_caster != is_player:
            return 0
        net = sum(
            1 if card.element == "metal" else (-1 if card.element else 0)
            for card in self.duel.round.player.queue + self.duel.round.bot.queue
        )
        if self.duel.background:
            net += 1 if self.duel.background == "metal" else -1
        return net

    def _player_base(self) -> dict[str, int]:
        """The player's current stats: cross-swap already resolved, plus the conduct swing on the
        contested stat if they cast it this battle — mirrors `_bot_base`."""
        base, _ = self._swapped_bases()
        contested = self.duel.round.stat if self.duel.rounds else self.duel.challenge
        bonus = self._conduct_bonus(True)
        if bonus and contested in base:
            base[contested] += bonus
        return base

    def _blind_deck_pick(self, mine: Player, theirs: Player) -> Card | None:
        """A steal's empty-hand fallback: rank whatever ``mine`` actually knows is in ``theirs``'s
        deck (see ``Player.known_of_opponent_deck``), or pick uniformly at random from the rest.
        Lives here, not in `bot.py` — the "AI" surface is only ever handed the pre-filtered known
        subset (`bot.best_known_deck_card`), never the real deck, so it cannot rank by content even
        by accident. ``None`` when the deck itself is empty too."""
        if not theirs.deck:
            return None
        known = [c for c in theirs.deck if c.id in mine.known_of_opponent_deck]
        return bot.best_known_deck_card(known) if known else self.rng.choice(theirs.deck)

    def _steal_wu(self, is_player: bool) -> None:
        """Takes the opponent's strongest hand Wu, or a known/random deck card if their hand is
        empty — the same policy AI Jack's own steal already uses (see `bot.steal_target`), open to
        whoever plays the card."""
        mine = self.state.player if is_player else self.state.bot
        theirs = self.state.bot if is_player else self.state.player
        target = bot.steal_target(theirs.hand)
        if target is None:
            target = self._blind_deck_pick(mine, theirs)
        if target is None:
            return
        theirs.remove_card(target)
        jong.drop_if_broken(theirs)  # a stolen part breaks a constructed Jong
        mine.hand.append(target)

    def _hack_construct(self, is_player: bool) -> None:
        """Vs Jack in a bot identity (never Mala Mala Jong): a stand-in mode (AI Jack, Attack!)
        auto-loses outright since Jack himself isn't the one fighting; a modifier mode (Chamelon-Bot,
        Jack-Bot) instead has its card nullified and the fight proceeds normally.

        Zeroes the specific card, not a blanket `boost_negated`/`defence_negated` flag — those negate
        every boost or every curse on a side, and Jack may have fielded a REAL boost Wu instead of
        Chamelon-Bot's this cycle (it competes for the slot, see `_chamelon_boost_card`), which this
        must leave untouched. `Side.jack_bot` already tracks exactly the one card either mechanism
        lands, so mutating it in place is the whole fix — it is shared by reference with `queue`.
        """
        opponent = self.state.bot if is_player else self.state.player
        if not bot.is_jack(opponent) or bot.is_jong(opponent):
            return
        mine, theirs = self.duel.round.sides(is_player)
        if self.duel.jack_mode in (jack.AI_JACK_NAME, jack.ATTACK_NAME):
            self.duel.auto_winner = is_player
        elif self.duel.jack_mode == jack.CHAMELON_NAME:
            for card in theirs.jack_bot:
                card.stats = {stat: 0 for stat in card.stats}
        elif self.duel.jack_mode is None:
            for card in mine.jack_bot:
                card.stats = {stat: 0 for stat in card.stats}

    def _seize_ground(self, is_player: bool) -> None:
        """Its caster takes the challenger's ground for the rest of the showdown, overriding a
        temple-set ``conch_tiebreak`` (this is fielded later, so it wins). Both sides seizing cancels
        to the priority default — no last-writer-wins between two initiative powers.
        ``ground_seized`` distinguishes that clash from a legitimate override."""
        if self.state.ground_seized is not None and self.state.ground_seized != is_player:
            self.state.conch_tiebreak = None  # both seized — back to who leads
        else:
            self.state.ground_seized = is_player
            self.state.conch_tiebreak = is_player

    def _resolve_bot(self, current: Round, card: Card) -> None:
        stat = bot.choose_stat(current, self._ground(), card) if names_a_stat(card.power) else None
        element = (
            bot.choose_element(current, self._ground(), card)
            if chooses_element(card.power)
            else self.duel.background or ""
        )
        self._apply_elemental(
            resolve_played_power(
                current, card, is_player=False, element=element, stat=stat,
                display_name=self._summon_display(card, is_player=False),
            )
        )

    def _summon_display(self, card: Card, *, is_player: bool) -> str | None:
        """A summon Wu enters the board as the thing it calls up, not as itself — the hand still
        shows the Wu, and only the display name changes; stats are the Wu's own. ``None`` for an
        ordinary Wu. Pools and their keying live in :mod:`.summons`."""
        template = card.power.summon
        if not template:
            return None
        caster, target = self.state.duelist(is_player), self.state.duelist(not is_player)
        return summon_name(
            template,
            caster=caster.character,
            target=target.character,
            arena=self.duel.background or "",
            caster_is_jong=bot.is_jong(caster),
            target_is_jong=bot.is_jong(target),
        )

    def _ground(self) -> Ground:
        """The terms this battle is fought under — what the scorer and the bot both read."""
        return Ground(
            stats=list(self.duel.stakes.stats.keys()) if self.duel.stakes else [],
            background=self.duel.background or "",
            player_stats=self._player_base(),
            bot_stats=self._bot_base(),
            bonus_cancelled=self.duel.elemental_bonus_cancelled,
            bonus_reversed=self.duel.elemental_bonus_reversed,
            # Hannibal: his own Wu ignore arena drag, and the foe's arena lift is turned aside.
            # Empty for any other opponent.
            bot_ward=hannibal.DEFLECTED_ELEMENTS if bot.is_hannibal(self.state.bot) else frozenset(),
            player_deflect=hannibal.DEFLECTED_ELEMENTS if bot.is_hannibal(self.state.bot) else frozenset(),
            # Priority is the last word when nothing else separates the battle — normally whoever
            # called the challenge. An initiative power can split the two: the opponent leads and
            # names the stat, but its caster keeps the ground.
            challenger_is_player=(
                self.state.conch_tiebreak
                if self.state.conch_tiebreak is not None
                else bool(self.duel.player_priority)
            ),
        )

    def _jack_base(self) -> dict[str, int]:
        """Jack's real current stats, before Beast Form's or Chamelon-Bot's per-battle swing (both
        live in `_bot_base` — they only touch the one contested stat, and need to know which battle
        that is, which this method does not).

        Attack! is a flat ATTACK_STAT on every stat, metal, plus the same resonance/suffer swing a
        metal Wu gets for free — `Character` carries no element of its own, so it's added here, same
        shape as `BEAST_BOOST`. The swing needs a decided ground; it reads as neutral (0) while one
        is still being picked (see `_setup_brawl`, which calls this to choose it).

        Good Jack (`Player.yoyo_flipped`) is a flat GOOD_JACK_STAT on force/agility plus whatever
        training delta Evil Jack has already banked on them; intellect is his own separately trained
        value (`Player.good_jack_intellect`), never derived from Evil's. Otherwise his plain printed
        stats.

        The one seam every bot-stats read of him passes through, so all three modes are real, not
        cosmetic.
        """
        if self.duel.jack_mode == jack.ATTACK_NAME:
            swing = element_score("metal", self.duel.background) if self.duel.background else 0
            return {stat: jack.ATTACK_STAT + swing for stat in jong.battle_stats(self.state.bot)}
        if bot.is_jack(self.state.bot) and self.state.bot.yoyo_flipped:
            real = self.state.bot.character.stats
            return {
                "force": jack.GOOD_JACK_STAT + (real["force"] - jack.JACK_PRINTED_PHYSICAL),
                "agility": jack.GOOD_JACK_STAT + (real["agility"] - jack.JACK_PRINTED_PHYSICAL),
                "intellect": self.state.bot.good_jack_intellect,
            }
        return jong.battle_stats(self.state.bot)

    def _swapped_bases(self) -> tuple[dict[str, int], dict[str, int]]:
        """Both sides' own current stats — Good Jack's override already resolved — after the
        Yin/Yang Yo-Yo's cross-swap (`DuelState.swapped_stats`). Computed together: a swap needs the
        OTHER side's own value, and each side's own override must resolve before the exchange, not
        after — else swapping into Good Jack's intellect could read Evil Jack's real one instead."""
        player_base = dict(jong.battle_stats(self.state.player))
        bot_base = dict(self._jack_base())
        for stat in self.duel.swapped_stats:
            if stat in player_base and stat in bot_base:
                player_base[stat], bot_base[stat] = bot_base[stat], player_base[stat]
        return player_base, bot_base

    def _bot_base(self) -> dict[str, int]:
        """The bot's base stats for the CURRENT battle. Beast Form adds BEAST_BOOST to the stat it
        named, in the ONE battle that contests it — a tournament's other two legs see the plain
        printed stats. Chamelon-Bot's own denial is a boost, not a base override (see
        `_chamelon_boost_card`/`_commit_boost`) — it competes for the same one-per-fielded-Wu slot as
        any real boost.

        On the BASE, so it is element-free by nature: it earns no arena bonus and no elemental
        counter can touch it (they act on the elemental bonus, which a base stat never carries).
        """
        _, base = self._swapped_bases()
        contested = self.duel.round.stat if self.duel.rounds else self.duel.challenge
        if self.duel.beast_stat is not None and self.duel.beast_stat == contested:
            base[self.duel.beast_stat] += BEAST_BOOST
        bonus = self._conduct_bonus(False)
        if bonus and contested in base:
            base[contested] += bonus
        return base

    def _chamelon_boost_card(self) -> Card | None:
        """A synthetic boost, built fresh each cycle, never a real catalog row: raises Jack's own
        stat past the opponent's by `CHAMELON_MARGIN` on the ONE stat this battle contests, never
        below his own, never touching the other two. `None` when he isn't sent as Chamelon-Bot, the
        stat needs no help, or he has already spent it this showdown. `_commit_boost` knows its
        reserved id and never stakes it — a computed effect, not a Wu he could lose.

        Rebuilt fresh each cycle rather than sourced from `_boost_options`, so it is never subject
        to that machinery's identity-based "already spent" filter — checked here by id instead, or a
        multi-Wu stat challenge could stack the same denial once per Wu fielded, not once a showdown.
        """
        if self.duel.jack_mode != jack.CHAMELON_NAME:
            return None
        if any(spent.id == jack.CHAMELON_BOOST_ID for spent in self.duel.bot.boosts_spent):
            return None
        contested = self.duel.round.stat if self.duel.rounds else self.duel.challenge
        own = jong.battle_stats(self.state.bot)
        if not contested or contested not in own:
            return None
        opponent_stat = jong.battle_stats(self.state.player).get(contested, 0)
        bump = opponent_stat - own[contested] + CHAMELON_MARGIN
        if bump <= 0:
            return None
        stats: dict[str, int | None] = {stat: 0 for stat in own}
        stats[contested] = bump
        return Card(
            id=jack.CHAMELON_BOOST_ID, name=jack.CHAMELON_NAME, stats=stats,
            power=Power(
                id=jack.CHAMELON_BOOST_ID, name=jack.CHAMELON_NAME, mechanic=Mechanic.INNATE,
                description="",
            ),
            # Elementless, deliberately: precisely the bump and nothing else. An elemental tag would
            # let the arena swing it further off parity or short of it — `element_score` exempts an
            # elementless card entirely.
            element="", type="item", points=0,
        )

    def _score_round(self, current: Round) -> None:
        if self.duel.jack_mode == jack.ATTACK_NAME:
            score_brawl(current, self._ground())
        else:
            score_battle(current, self._ground())
        if current.bane_winner is not None:  # a bane power took this battle from the construct
            current.winner = current.bane_winner

    async def _element_for(self, card: Card) -> str:
        """Wu that choose an element (`chooses_element`) let the player name one; any other card
        takes the background."""
        if chooses_element(card.power):
            return await self.choices.element(self.duel.background or "")
        return self.duel.background or ""

    async def _stat_for(self, card: Card) -> str | None:
        """Wu that name a stat (`names_a_stat`) ask; every other Wu already knows."""
        if names_a_stat(card.power):
            return await self.choices.stat(self._stat_names())
        return None

    def _stat_names(self) -> list[str]:
        """The three stats, in the order a card prints them."""
        return list(self.state.player.character.stats)

    async def _resolvement(self) -> None:
        """Weigh the match; always names a winner. Three steps in order: rounds won decides first; a
        level match falls to aggregate margin; only when nothing separates them does the challenger
        hold the ground.
        """
        player_rounds, bot_rounds = self.duel.rounds_won
        if player_rounds != bot_rounds:
            self.duel.winner = player_rounds > bot_rounds
        else:
            margin = sum(r.score for r in self.duel.rounds)
            self.duel.winner = margin > 0 if margin else bool(self.duel.player_priority)
        if self.duel.auto_winner is not None:
            self.duel.winner = self.duel.auto_winner  # an auto-winner overrides the battle result

        if (
            bot.is_jack(self.state.bot) and self.duel.jack_mode is None and self.duel.winner
            and jack.choose_to_flee(self.state.jack_flees_used)
        ):
            self.duel.jack_fled = True
            self.state.jack_flees_used += 1

        self._award_prize()

    async def _end(self) -> None:
        if bot.is_jack(self.state.bot):
            step = jack.ATTACK_MOMENTUM_STEP if self.duel.winner else -jack.ATTACK_MOMENTUM_STEP
            cap = jack.ATTACK_MOMENTUM_CAP
            self.state.jack_attack_momentum = max(-cap, min(cap, self.state.jack_attack_momentum + step))
        self.state.previous_challenge = [self.duel.challenge] if self.duel.challenge else []
        self.state.previous_background = [self.duel.background] if self.duel.background else []
        # The action counters are NOT reset here. A turn turns over in `turn.refill_hands`, which runs
        # after the opponent has taken theirs — and which may spend the coming turn's action for you,
        # by dealing you back in. Reset here and that charge would be wiped before it ever bit.
        self.state.bot_turn_done = False  # a new temple turn, for both of you
        self.state.forced_priority = None  # the Conch's answer was for this showdown, and is spent
        self.state.locked_challenge = None  # the Prognosis pin was for this showdown too
        self.state.conch_tiebreak = None
        self.state.ground_seized = None  # a Cube's grab was for this showdown, and is spent with it
        self.state.initiative_contested = False  # the contest, if any, was settled by this showdown's coin
        if not self.state.card_deck:
            self.state.has_ended = True

        # the loser's staked cards go to the winner, fresh (wear belongs to whoever used a Wu, see
        # wear.py). A fled Jack keeps his — the point of conceding.
        winner, loser = self._winner_and_loser()
        if not self.duel.jack_fled:
            for card in self.duel.duelist(not self.duel.winner).stakes:
                loser.remove_card(card)
                jong.take_won(winner, hand_over(card))  # into the hand, or banked if the winner is locked

        # A losing Mala Mala Jong drops the form (a loss always breaks the set, since it always
        # wagers parts). The winner already took those parts above; the Heart comes out of exile to
        # them too.
        if bot.is_jong(loser):
            heart = jong.revert(loser)
            if heart is not None:
                jong.take_won(winner, heart)

        # losing teaches: the loser's training bar gains one (see logic/flow/training.py). The bot
        # cashes a full bar on the spot; the raised stat is kept for the screen to report.
        self.duel.bot_trained = record_showdown(
            self.state, self.settings, player_won=bool(self.duel.winner)
        )

        # A WISH card is exiled outright: removed from the winner's hand before wear could vault it
        # for points or any recovery power could reach it.
        if self.duel.auto_winner is not None:
            champion = self.state.duelist(self.duel.auto_winner)
            for card in [c for c in champion.hand if mechanic_of(c.power) is Mechanic.WISH]:
                champion.remove_card(card)

        # wear: every Wu committed this showdown and still held wears by one, and the worn-out are
        # vaulted for their points on the spot (see logic/flow/wear.py). Kept for the screen to report.
        for is_player in (True, False):
            side = self.duel.duelist(is_player)
            # The exiled Heart boosts from out of play — it never wears and is never vaulted, so it is
            # kept out of the wear tally even though it rode the boost slot this showdown.
            heart = self.state.duelist(is_player).jong_heart
            committed = [c for c in side.stakes + side.boosts_spent + side.off_wager if c is not heart]
            vaulted = wear.record_showdown(
                self.state.duelist(is_player), committed, rng=self.rng, wear_limit=self.settings.wear_limit
            )
            self.duel.worn_out += [(card.name, is_player, paid) for card, paid in vaulted]
            # A part worn out and vaulted breaks the set — the form drops here too, the Heart coming
            # home (the lost-showdown drop above already handled the loser; this catches the winner).
            jong.drop_if_broken(self.state.duelist(is_player))

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
        """Boost Wu still available — every fielded Wu may carry one, and each must be a different Wu.

        A boost is spent once a showdown, not once a battle: a three-Wu field can be boosted three
        times, but only by a duelist holding three distinct boost Wu. A Wu is spent whichever slot it
        went into — fielded as an ordinary Wu, it cannot come back to boost the next one.
        """
        duelist = self.duel.duelist(is_player)
        # Mala Mala Jong boosts only with the Heart it exiled — never a part, never a wudai — and only
        # once, so it is gone from the offer the moment it has been spent this showdown.
        if bot.is_jong(player):
            heart = player.jong_heart
            if heart is None or any(c is heart for c in duelist.boosts_spent):
                return []
            return [heart]
        unused = excluding(player.whole_hand, duelist.boosts_spent + duelist.stakes)
        available = [card for card in unused if is_boost_slot(card.power)]

        # You still owe a Wu for every one not yet fielded. Boosting with one out of HAND spends a Wu
        # you would have put down, so it is only offered while you can still cover what you owe. A Wu
        # in the inalienable slot is never fieldable as a card, so it always costs you nothing.
        side = 0 if is_player else 1
        owed = self._total_wu()[side] - self._fielded()[side]
        if len(self._playable(player, is_player=is_player)) > owed:
            return available
        return excluding(available, player.hand)

    def _playable(self, player: Player, *, is_player: bool) -> list[Card]:
        """Wu that may still be fielded as a card. The hand only — the inalienable Wu is boost-only."""
        return excluding(player.hand, self.duel.duelist(is_player).stakes)

    def _choose_jack_mode(self) -> None:
        """Jack's identity swap (Attack!, AI Jack, Chamelon-Bot, or himself) — decided once, right
        after priority: nothing is staked, boosted, or fielded yet this showdown.

        The steal fires here, before either side picks a Wu, so the screen's toast (see
        `screens/duel._announce_jack_steal`) lands before a menu could reveal the theft first.
        """
        if not bot.is_jack(self.state.bot):
            return
        if self.state.bot.yoyo_flipped:  # Good Jack: no bot form this fight, see `_jack_base`
            self.duel.jack_mode = None
            return
        mode = jack.choose_jack_mode(
            bool(self.duel.player_priority), self.state.jack_can_swap,
            self.state.jack_attack_momentum, self.rng,
        )
        self.duel.jack_mode = mode
        if mode == jack.ATTACK_NAME:
            # Never named, never a tournament — see `_challenge_options`/`_commitment`'s guard below.
            # `jack_can_swap` is untouched: Attack! neither reads nor writes it (see `choose_jack_mode`).
            self.duel.challenge = BRAWL
            pool = [n for n in jack.ATTACK_BOT_NAMES if n != self.state.last_attack_bot_name]
            picked = self.rng.spawn("attack_bot_name").choice(pool)  # decoration; see jack_bot_name
            self.duel.attack_bot_name = picked
            self.state.last_attack_bot_name = picked
            return
        if not self.duel.player_priority:
            # Only AI Jack's branch touches the alternation — Chamelon-Bot may fire every time the
            # player leads, whenever CHAMELON_MARGIN says it's worth it; "cannot spam" is his alone.
            self.state.jack_can_swap = mode is None
        self._resolve_ai_jack_steal()

    def _resolve_ai_jack_steal(self) -> None:
        """AI Jack's theft: the strongest Wu in the opponent's hand, or a known/random deck card if
        empty — fires the moment his mode is picked, before either side has chosen a Wu. No-op if
        nothing qualifies or Jack isn't in AI Jack mode.

        A counter Wu (`jack.is_counter`) is taken outright, ahead of a stronger ordinary one."""
        if self.duel.jack_mode != jack.AI_JACK_NAME:
            return
        target = bot.steal_target(self.state.player.hand, prefer=jack.is_counter)
        if target is None:
            target = self._blind_deck_pick(self.state.bot, self.state.player)
        if target is None:
            return
        self.state.player.remove_card(target)
        jong.drop_if_broken(self.state.player)  # a stolen part breaks a constructed Jong
        self.state.bot.hand.append(target)
        self.duel.jack_stolen = target.name

    def _pick_jack_bot_name(self) -> None:
        """Jack-Bot's flavour name for this cycle's curse — one of `jack.JACK_BOT_NAMES`, never
        twice in a row."""
        pool = [name for name in jack.JACK_BOT_NAMES if name != self.state.last_jack_bot_name]
        # A sub-stream: the flavour name is decoration, and decoration that consumed the main
        # stream would shift every roll after it — a cosmetic change that alters the game.
        picked = self.rng.spawn("jack_bot_name").choice(pool)
        self.duel.jack_bot_name = picked
        self.state.last_jack_bot_name = picked

    def _commit_boost(self, card: Card, *, is_player: bool, element: str) -> None:
        duelist = self.duel.duelist(is_player)
        mine, theirs = self.duel.round.sides(is_player)
        player = self.state.player if is_player else self.state.bot
        # What can be staked: everything except the inalienable slot — a wudai weapon found in the
        # pile boosts and stakes like any other Wu; only the character's own inalienable copy is
        # exempt. What cannot be staked: the inalienable slot, the Heart Mala Mala Jong exiled (out
        # of play powering the form), and Chamelon-Bot's denial (a computed effect, not a real Wu
        # Jack holds).
        is_jong_heart = card is player.jong_heart
        is_chamelon_boost = card.id == jack.CHAMELON_BOOST_ID
        if not is_one_of(card, player.inalienable_hand) and not is_jong_heart and not is_chamelon_boost:
            duelist.stakes.append(card)
        duelist.boosts_spent.append(card)  # one showdown, one use — even a dragon
        boosted = as_boost(card, element, self._stat_of(self.duel.round_number - 1))
        if is_jong_heart:
            # As Jong's boost the Heart fights as ITSELF: a flat JONG_BOOST_STAT, metal, no summoned
            # form and no opponent's off-wager answer — the amplified construct, not the ANIMATE beast.
            boosted.stats = {stat: jong.JONG_BOOST_STAT for stat in boosted.stats}
            boosted.element = "metal"
            boosted.name = card.name
        elif mechanic_of(card.power) is Mechanic.ANIMATE:
            # A separate summoned fighter, named by the arena — and it entitles the OTHER side to one
            # off-wager Wu in this battle (see `_offer_balance`), so the extra body is answered.
            boosted.name = jong_form(element, self.state.duelist(is_player).character)
            self.duel.round.heart_summoner = is_player
        elif mechanic_of(card.power) is Mechanic.BOT:
            # Jack-Bot always curses — its printed -1/-1/-1 already rides `boosted` via `as_boost`.
            # The mirror that lands on the opponent carries it (see `curse_from_boost`), and Jack's
            # own copy is spent on their side — zeroed and filed to `spent`, exactly like a played
            # curse (`resolve.resolve_played_power`) — or a naive unconditional append below would
            # ALSO dock his own score.
            boosted.name = self.duel.jack_bot_name or card.name
            curse_from_boost(theirs, deepcopy(boosted))
            boosted.stats = {stat: 0 for stat in boosted.stats}
            mine.spent.append(boosted)
        elif is_chamelon_boost:
            # A gadget that showed up, not stats blended into the Wu it lifts — tracked via the same
            # boost-slot list `Side.jack_bot` already exists for.
            mine.jack_bot.append(boosted)
        mine.queue.append(boosted)

    def _is_construct(self, player: Player) -> bool:
        """Whether this duelist fights this showdown as a construct — Mala Mala Jong, or Jack in any
        of his three identity swaps (each sends a bot, not himself). Read by Denshi Bunny's auto-win
        check; Jong is separately queryable via `bot.is_jong` for its own immunity."""
        return bot.is_jong(player) or (bot.is_jack(player) and self.duel.jack_mode is not None)

    def _winner_and_loser(self) -> tuple[Player, Player]:
        if self.duel.winner:
            return self.state.player, self.state.bot
        return self.state.bot, self.state.player

    def _award_prize(self) -> None:
        """Winning settles who keeps their own Wu; taking the revealed one must be earned via one of
        the routes in :mod:`.mechanics.prize`. Failing all of them, the Wu is lost, not destroyed.
        """
        winner, loser = self._winner_and_loser()
        self.duel.winner_character = winner.character.name
        if not self.duel.stakes:
            self.duel.card_won = False
            return

        # Jack-bots Attack!: no ladder, and no losing it either — winning the Brawl claims it outright.
        if self.duel.jack_mode == jack.ATTACK_NAME:
            self.duel.prize_route = PrizeRoute.BRAWL_WON
        else:
            self.duel.prize_route = claim_route(
                self.duel.rounds,
                winner_is_player=bool(self.duel.winner),
                background=self.duel.background or "",
                threshold=self.settings.prize_threshold,
                bonus_cancelled=self.duel.elemental_bonus_cancelled,
            )
        self.duel.card_won = self.duel.prize_route is not None
        if self.duel.card_won:
            # a WU-PLAY win gifts the prize to Chase's opponent; Beast Form keeps it. `card_won`
            # stays true — only the taker changes.
            gifts = bot.is_chase(winner) and self.duel.beast_stat is None
            self.duel.prize_gifted = gifts
            takes_prize = loser if gifts else winner
            jong.take_won(takes_prize, self.duel.stakes)  # into the hand, or banked if locked
        else:
            # Lost, not destroyed — parked in state.lost for a future recovery power; nothing reads
            # it yet.
            self.state.lost.append(self.duel.stakes)
