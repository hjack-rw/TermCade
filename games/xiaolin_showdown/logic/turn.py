"""The temple turn — what both duelists do between showdowns.

Keeps a hand within its size limit (the surplus goes to the personal deck) and flags the run finished
when a point limit is reached or the draw pile runs dry. A short hand is *not* topped up: the player
refills it themselves with Draw. Only a hand with **nothing that can be fielded** is drawn for
automatically — a Wu that can only ever be laid as a boost is no answer to a showdown, so a hand of
those is empty for every purpose that decides a duel, and the loop would otherwise strand on it.
"""

from __future__ import annotations

from dataclasses import dataclass

from termcade.core.rng import Rng
from termcade.core.settings import Difficulty

from .mechanics.powers import (
    MORPH_ASIDE,
    MORPH_CONTESTED,
    NAMED_STAT_VALUE,
    Mechanic,
    is_gamble,
    mechanic_of,
    roll_gamble,
)
from .constants import WEAR_LIMIT
from .mechanics.cards import hand_over
from .models import Card, Player
from .settings import XiaolinSettings, deposit_limit, player_actions, plays_keen
from .state import XiaolinState
from .training import TRAIN_LENGTH, add_progress, can_train, pick_stat, raise_stat, turn_over

# What a booster is worth in a showdown. It carries no stats of its own, so without this premium a
# skilled bot would happily bank one for points.
BOOSTER_PREMIUM = 4

# The bot never banks its hand below this. It may deposit one Wu a turn and its only income is
# winning showdowns, so with no floor it cashes its own bench and ends the run holding a single Wu
# against a full hand — measured at 5 -> 1.3 Wu over a run. Two is what a duelist needs to still be
# an opponent; three starves it, because a hand that sits at three can never bank at all.
DUEL_FLOOR = 2


def refill_hands(state: XiaolinState, settings: XiaolinSettings, *, rng: Rng) -> None:
    """Bring both hands within their size limit and update ``has_ended``.

    Runs each time control returns to the temple (between showdowns). Re-balances until both hands
    are stable — loops :func:`oversee_hand_size` over both until neither reports more work. The
    player's interactive over-limit discard is handled by the screen *before* this runs, so any
    shedding here (the bot's) is random.

    This is where a turn turns over, so this is where the action counters are cleared — and then
    immediately spent again for anyone the mercy rule has to deal back in (:func:`_charge_the_turn`).
    """
    target = state.win_target(settings)
    if state.player.points >= target or state.bot.points >= target:
        state.has_ended = True

    state.actions_taken = 0
    state.bot_actions_taken = 0
    state.deposits_taken = 0
    state.bot_deposits_taken = 0
    turn_over(state.player)  # a taken payout's bar showed full through the turn; reset it now
    turn_over(state.bot)

    while not (
        oversee_hand_size(state, is_player=True, settings=settings, rng=rng)
        and oversee_hand_size(state, is_player=False, settings=settings, rng=rng)
    ):
        pass


def oversee_hand_size(
    state: XiaolinState, *, is_player: bool, settings: XiaolinSettings, rng: Rng
) -> bool:
    """Nudge one duelist's hand toward its size limit by one pass; return whether it is settled.

    Over the limit → shed the surplus at random to the personal deck. Under → leave it (the player
    tops up manually with Draw), unless there is nothing in it that can be *fielded*, which is drawn
    for from the main pile. Returns ``False`` after shedding (the caller re-checks), ``True`` else.
    """
    player = state.duelist(is_player)
    over = len(player.whole_hand) - max_hand_size(player, settings.max_hand_size)
    if over <= 0:
        if not player.hand:  # nothing fieldable — see `Player.hand` vs `inalienable_hand`
            _emergency_fill(state, player, settings)
            _charge_the_turn(state, settings, is_player=is_player)
        return True
    if state.has_ended:
        return True  # game over — leftover cards stay, they still count toward the final score

    for _ in range(over):
        card = rng.choice(player.hand)
        player.remove_card(card)
        shelve(player, card, rng=rng)
    return False


def shelve(player: Player, card: Card, *, rng: Rng) -> None:
    """Put a Wu on a personal deck — and shuffle it in. The deck is an OBSTACLE, not an ordered stack:
    a shelved Wu must not come back in a known order or on a countable turn, or it could be memorised
    and played around. Load-bearing randomness (it decides a draw), so it draws the main stream."""
    player.deck.append(card)
    rng.shuffle(player.deck)


def _charge_the_turn(state: XiaolinState, settings: XiaolinSettings, *, is_player: bool) -> None:
    """Being dealt back in *is* the turn's action, not a gift on top of it.

    The mercy rule hands a duelist with nothing fieldable a hand off the pile. That is the same
    income a Draw buys, so it costs the same thing: the turn it lands on opens already spent.
    """
    if is_player:
        state.actions_taken = player_actions(state, settings)  # the whole budget, boss run or not
    else:
        state.bot_actions_taken = settings.actions_per_turn


def _emergency_fill(state: XiaolinState, player: Player, settings: XiaolinSettings) -> None:
    """Refill a hand with nothing FIELDABLE in it — own shelf first, then the pile (emptying it ends
    the run).

    "Nothing playable" is not "nothing at all": a dragon (``boost``/0) can only ever be laid as a
    boost, so a hand of them has no answer to a showdown. An amplifier (``boost``/+1) *can* be fielded,
    badly.

    ``empty_draw_limit`` is how many Wu the mercy PAYS, not the hand size it fills to. Filling to a
    size paid a duelist holding a wudai one Wu LESS than one holding none — the wudai already occupied
    a slot — so the rule shorted the very hands it exists to rescue. A count is blind to what is held.
    ``max_hand_size`` still caps it: the mercy may not overfill a hand.
    """
    room = max_hand_size(player, settings.max_hand_size) - len(player.whole_hand)
    owed = min(settings.empty_draw_limit, room)
    while player.deck and owed > 0:
        player.hand.append(player.deck.pop(0))
        owed -= 1
    while state.card_deck and owed > 0:
        _draw_from_main(state, player)
        owed -= 1


# What a Wu is worth on the table when its printed stats say nothing (a `? ? ?` card reads as ZERO).
# Same currency as a printed stat.
_MECHANIC_VALUE: dict[Mechanic, int] = {
    # Priced off the Morph rule itself, so retuning the rule re-prices the bot.
    Mechanic.MORPH: MORPH_ASIDE * 2 + MORPH_CONTESTED,
    Mechanic.BUFF: NAMED_STAT_VALUE,
    Mechanic.MISFORTUNE: NAMED_STAT_VALUE,
    Mechanic.NULLIFY_STATS: 5,
    Mechanic.NULLIFY_WU: 5,
    Mechanic.NULLIFY_CURSE: 4,
    # A whole-hand swap swings at least as hard as a negation. The bot does not SPEND it yet
    # (temple_ai has no policy for it) — this price only keeps it from banking the strongest
    # tempo card in the pool as junk.
    Mechanic.TRANSFER: 5,
    # Refresh prints 0/0/0 — its worth is the second use it buys back, not stats. Priced as a modest
    # utility so the bot holds it rather than banking it as junk; the bot has no policy to spend it yet.
    Mechanic.REFRESH: 3,
}

# (Witchcraft is a CHARACTER power — no card carries it, so its table price is moot; it sits in
# `_STATS_ARE_THE_WHOLE_VALUE` below purely to satisfy the every-mechanic-is-accounted guard.)

# Mechanics whose printed stats are the whole value, declared rather than assumed. The two sets must
# cover every `Mechanic` — `test_every_mechanic_is_priced` enforces it. An unpriced `? ? ?` Wu reads as
# zero: the bot banks the strongest card in the game for 2 points. That cost 16 points of win rate once.
#
# Two of them are excused for a *different* reason: they are worth nothing on the table at all, and
# that is deliberate. Kept apart from the rest because "its stats say what it is worth" and "it is
# worth nothing" are different claims, and only the second one may price at zero.
_WORTH_NOTHING_ON_THE_TABLE: frozenset[Mechanic] = frozenset(
    {
        Mechanic.FILLER,  # deck padding: no stats, no power, no business being fielded
        # The joke Wu prints `? ? ?` and does nothing in a battle. Everything it is worth is at the
        # temple, where it is rolled for points — so zero on the table is honest, not an oversight.
        Mechanic.GAMBLE,
    }
)

_STATS_ARE_THE_WHOLE_VALUE: frozenset[Mechanic] = _WORTH_NOTHING_ON_THE_TABLE | frozenset(
    {
        Mechanic.INNATE,  # the stats *are* the Wu
        Mechanic.INITIATIVE,  # its bonus is a hand power; in a battle it is only its stats
        Mechanic.HAND_SIZE,  # likewise — it buys a hand slot, not a blow
        Mechanic.DOUBLE_TRAINING,  # a hand power (doubles training); in a battle it is only its stats
        Mechanic.HAND_FIZZLE,  # unprinted (see `powers.UNPRINTED`)
        Mechanic.DRAW,  # a temple power; on the table it is just its printed stats
        Mechanic.READ_DECK,  # likewise
        Mechanic.SCRY,  # likewise
        Mechanic.ENHANCED_VISION,  # likewise
        Mechanic.FETCH,  # likewise
        Mechanic.BOUNCE,  # likewise
        Mechanic.LUCK,  # likewise — it acts on the lost pile, never in a battle
        Mechanic.PROGNOSIS,  # likewise — a temple power, on the table just its printed stats
        Mechanic.WITCHCRAFT,  # a character power (Wuya's) — no card ever prints it
        Mechanic.BEAST_FORM,  # a character power (Chase's) — likewise
        # The dragon and the booster carry no stats but decide duels — they are priced by
        # BOOSTER_PREMIUM in `duel_value` rather than here, which is the older seam.
        Mechanic.DRAGON,
        Mechanic.BOOST,
        # The Serpent's Tail voids the elemental bonus for both duelists all showdown, and vetoes the
        # prize's elemental route with it. That is plainly worth more than the stats it prints — and it
        # is *meant* to be: the veto is the card, and the author has priced it as such (4 points, the
        # top of the pool). It is not underpriced here by oversight. Do not "fix" it.
        Mechanic.NULLIFY_ELEMENT,
        # The Celestial Dial reverses the elemental bonus all showdown — worth more than its printed
        # 1/1/1, but priced by them here: the reversal is contextual (great against an in-tune opponent,
        # nothing against a metal one) and the bot reads that from its play-it-out eval, not from here.
        Mechanic.REVERSE_ELEMENT,
        # The four boss counters print real stats; their showdown effect (negate a boost, recolour a
        # side or the arena) is contextual and read by the bot's play-it-out eval, not priced here.
        Mechanic.NULLIFY_BOOST,
        Mechanic.CLEANSE,
        Mechanic.SET_ELEMENT,
        Mechanic.WARD,
        Mechanic.SET_ARENA,
        # Prints real stats; its shield (no curse on the stat it boosts) is contextual, read by the
        # bot's play-it-out eval, not priced here.
        Mechanic.STAT_SHIELD,
        # Prints real stats; its doubled elemental bonus is contextual (great in tune, awful against),
        # read by the bot's play-it-out eval, not priced here.
        Mechanic.DOUBLE_ELEMENT,
        # Its printed stats are its whole table value — the fat deposit is the points column, which the
        # bot reads straight off when it decides what to bank.
        Mechanic.TREASURE,
    }
)


def duel_value(card: Card) -> int:
    """Roughly what ``card`` is worth held in a showdown.

    Stat magnitude, not signed value: a negative stat is a *weapon* (``powers`` mirrors it onto the
    opponent's queue), so it is as worth keeping as a positive one. A booster carries no stats but
    decides duels, hence the premium.

    A Wu whose stats resolve at play prints none, so the stats cannot answer for it either — its
    mechanic does, through :data:`_MECHANIC_VALUE`. Without that, every card that reads `? ? ?` is
    worth nothing to the opponent, and it will cheerfully bank an Emperor Scorpion for two points.
    """
    stats = sum(abs(v) for v in card.stats.values() if v is not None)
    mechanic = mechanic_of(card.power)
    premium = BOOSTER_PREMIUM if mechanic is Mechanic.BOOST else 0
    return stats + _MECHANIC_VALUE.get(mechanic, 0) + premium


def pick_deposit(hand: list[Card], difficulty: Difficulty) -> Card | None:
    """Which Wu the bot deposits, by difficulty. ``None`` when nothing in hand is worth points.

    Hard takes the highest points, full stop: over 250 runs, weighting by ``duel_value`` lost ground at
    every weight, and refusing to deposit a booster cost 5 points of win rate. Points are the win
    condition. Easy sheds its least useful Wu and hoards weapons — it duels as well, and never closes.
    """
    candidates = [card for card in hand if card.points > 0]
    if not candidates:
        return None
    # A Wu one showdown from wearing out banks ITSELF, free (see wear.py) — spending the turn's
    # action on it wastes the action. Prefer any other candidate; near-worn only when that is all
    # there is.
    fresh = [card for card in candidates if card.uses < WEAR_LIMIT - 1]
    candidates = fresh or candidates
    if plays_keen(difficulty):
        return max(candidates, key=lambda c: c.points)
    return min(candidates, key=lambda c: (duel_value(c), -c.points))


def bank_value(card: Card, rng: Rng) -> int:
    """What depositing this Wu pays. Its printed points — unless it is the gamble, which is rolled.

    The bot banks on the same terms as the player. Neither is told what the gamble is worth, and
    neither finds out until it is spent: the bot picks it by the expected value in the card DB (see
    ``GAMBLE_SPREAD``), the same way a player eyeing a ``?`` has only the odds to go on.

    No duelist banks at a different rate. A "Shen Gong Wu hunger" that halved Wuya's deposits was
    built and reverted the same day: it did not make her score less so much as stop her CLOSING, and
    her runs went 7.7 showdowns to 13.8. Long runs feed the player's training bar — the one legal
    asymmetry in a boss run — so the player took 2.04 stat raises to 1.03 and out-trained her. It
    took her from 8.8% to 20.8% player win, the easiest boss in the tier. Run LENGTH predicts a
    boss's difficulty better than its scoring; shortening her runs is what makes her hard.
    """
    return roll_gamble(rng) if is_gamble(card.power) else card.points


# Game Log action names, for whoever spends the turn — one list, so a move of theirs files under the
# same word as the same move of yours. VAULT is the PLACE (the verb "deposited" goes in the line
# beneath it), and a power's own name goes in the line too: a title that changes per card cannot be
# scanned for. See docs/design/VOICE.md.
VAULT = "Vault"
DRAW = "Draw"
EARLY_BIRD = "Early Bird"
PASSED = "Pass"
POWER = "Power"
TRAIN = "Train"
RECALL = "Witchcraft"

# How close to a full bar the bot must be before training beats drawing or banking. Losses carry a
# bar most of the way for free; only the last stretch is worth whole temple turns.
_TRAIN_WITHIN = 4


@dataclass(frozen=True)
class BotMove:
    """One thing the opponent did: what KIND of action it was, and the line the player is shown.

    Two fields, because they answer different questions. The ``line`` is prose — it names the Wu and
    what it cost. The ``action`` is the action itself ("Deposit", "Draw", a power's name), which is
    what the Game Log files the move under, so their moves read the same shape as yours: an action,
    then what it did. Deriving one from the other would mean parsing the game's own sentences back.
    """

    action: str
    line: str


def bot_turn(
    state: XiaolinState,
    settings: XiaolinSettings,
    *,
    rng: Rng,
    difficulty: Difficulty = Difficulty.NORMAL,
) -> list[BotMove]:
    """The bot's between-showdown temple turn; returns a short log of what it did, for the player.

    One turn, one action — the rule that binds the player binds the bot: a hand that refilled itself
    for free would not be a resource, and a Wu spent out of one would cost nothing.
    """
    name = state.bot.character.name.split("_")[0]
    log: list[BotMove] = []

    # Every action charges its own budget — `use_power` does it for the powers, and the draw and the
    # deposit below do it for themselves. Charging it here as well would bill the turn twice.
    while state.bot_actions_taken < settings.actions_per_turn:
        acted = _bot_acts(state, settings, rng, difficulty, name)
        if acted is None:
            break
        log.append(acted)
    return log or [BotMove(PASSED, f"{name} did nothing this turn.")]


# The bot's temple actions, each a self-contained attempt that either DOES the thing and returns its
# log line, or returns ``None`` to say "not now, try the next". They used to be inlined twice —
# once in the boss policy and once in the generic one — verbatim, down to the pluralised "pt". A
# policy is now just an ORDER over these: change how the bot banks, and it changes for every duelist
# that banks, because there is one place that banks.


def _draw_thin_hand(
    state: XiaolinState, settings: XiaolinSettings, rng: Rng, difficulty: Difficulty, name: str
) -> BotMove | None:
    """Draw from the personal deck when the hand is too thin to field a full wager. A duelist that
    banks its way down to one Wu can only ever be wagered one, and wins nothing that way."""
    bot = state.bot
    if len(bot.hand) < settings.max_wager and bot.deck:
        drawn = bot.deck.pop(0)
        bot.hand.append(drawn)
        state.bot_actions_taken += 1
        return BotMove(DRAW, f"{name} drew {drawn.name} from their deck.")
    return None


def _fly_early_bird(
    state: XiaolinState, settings: XiaolinSettings, rng: Rng, difficulty: Difficulty, name: str
) -> BotMove | None:
    """Take a Wu off the shared pile with no showdown — the one action that raids the pile rather
    than the bot's own shelf. ``early_bird`` charges the turn itself."""
    from .actions import early_bird  # local: actions imports this module
    from .temple_ai import choose_early_bird

    bird = choose_early_bird(state, settings)
    if bird is not None:
        taken = state.card_deck[0]
        early_bird(state, bird, is_player=False)
        return BotMove(
            EARLY_BIRD,
            f"{name} used Early Bird to take {taken.name} from under your nose, "
            f"giving up {bird.name}.",
        )
    return None


def _recall_witchcraft(
    state: XiaolinState, settings: XiaolinSettings, rng: Rng, difficulty: Difficulty, name: str
) -> BotMove | None:
    """Wuya's temple action: call the OLDEST lost Wu back, paying no Wu for it. A known weapon from
    the lost beats a blind draw."""
    from .temple_ai import worth_recalling

    if mechanic_of(state.bot.character.power) is Mechanic.WITCHCRAFT and worth_recalling(state):
        revived = state.lost.pop(0)
        state.bot.hand.append(hand_over(revived))
        state.bot_actions_taken += 1
        state.witch_recalls += 1
        return BotMove(RECALL, f"{name} called {revived.name} back from the lost.")
    return None


def _cash_training(
    state: XiaolinState, settings: XiaolinSettings, rng: Rng, difficulty: Difficulty, name: str
) -> BotMove | None:
    """Spend the turn on a nearly-full training bar: a permanent +1 base stat pays in every showdown
    left in the run. A just-taken payout waits for the turnover — the bar cannot climb until it
    resets."""
    if (
        can_train(state.bot)
        and not state.bot.just_trained
        and TRAIN_LENGTH - state.bot.training <= _TRAIN_WITHIN
    ):
        state.bot_actions_taken += 1
        if add_progress(state.bot):
            stat = pick_stat(state.bot)
            raise_stat(state.bot, stat)
            return BotMove(TRAIN, f"{name} completed their training: their {stat} rose.")
        return BotMove(TRAIN, f"{name} spent the turn training.")
    return None


def _bank_surplus(
    state: XiaolinState, settings: XiaolinSettings, rng: Rng, difficulty: Difficulty, name: str
) -> BotMove | None:
    """Convert a surplus Wu to points — the win condition. Mirrors ``can_deposit``: never cash the
    last card out of the hand, and never spend more than half the turn's budget doing it."""
    bot = state.bot
    if len(bot.hand) > DUEL_FLOOR and state.bot_deposits_taken < deposit_limit(
        settings.actions_per_turn
    ):
        banked = pick_deposit(bot.hand, difficulty)
        if banked is not None:
            points = bank_value(banked, rng)
            bot.points = max(0, bot.points + points)  # a bad gamble cannot go below zero
            bot.remove_card(banked)
            state.bot_actions_taken += 1
            state.bot_deposits_taken += 1
            return BotMove(
                VAULT, f"{name} deposited {banked.name} for {points} pt{'s' if points != 1 else ''}."
            )
    return None


def _play_power(
    state: XiaolinState, settings: XiaolinSettings, rng: Rng, difficulty: Difficulty, name: str
) -> BotMove | None:
    """Spend a Wu's power when one is worth more than the points it would bank. The opponent reads
    only what a player could — see ``temple_ai.choose_temple_power``."""
    from .actions import use_power  # local: actions imports this module
    from .temple_ai import choose_temple_power

    play = choose_temple_power(state, settings)
    if play is not None:
        report = use_power(
            state,
            play.card,
            is_player=False,
            priority=play.priority,
            target=play.target,
            to_deck=play.to_deck,
            rng=rng,
        )
        return BotMove(
            POWER,
            f"{name} played {play.card.power.name} from the {play.card.name}.\n{report.log}",
        )
    return None


# The boss temple order: bank the surplus AHEAD of any power. A boss wins showdowns on its stats, so
# the temple is a race to the point target — keep a hand big enough to field a full wager, snatch
# cheap Wu off the pile, and BANK. A power is not taken here; it falls through to the generic path,
# which fires one only once the surplus is gone. That is the whole fix: banking outranks a power for
# a boss, so a reusable witchcraft power stops being an every-turn substitute for reaching the target.
_BOSS_ORDER = (_draw_thin_hand, _fly_early_bird, _recall_witchcraft, _bank_surplus)

# The generic order: a power first (when one beats banking), then the pile raid, the recall, the
# training cash-in, a thin-hand draw, and banking last.
_GENERIC_ORDER = (
    _play_power,
    _fly_early_bird,
    _recall_witchcraft,
    _cash_training,
    _draw_thin_hand,
    _bank_surplus,
)

# Chase Young meddles in no mere mortal affairs: at the temple he only trains, draws, or banks —
# never spends a Wu's power, never flies the Early Bird. His Wu are points and wagers, nothing more.
_CHASE_ORDER = (_cash_training, _draw_thin_hand, _bank_surplus)


def _first_move(
    order, state: XiaolinState, settings: XiaolinSettings, rng: Rng, difficulty: Difficulty, name: str
) -> BotMove | None:
    """The first action in ``order`` that does something, or ``None`` if none will."""
    for action in order:
        move = action(state, settings, rng, difficulty, name)
        if move is not None:
            return move
    return None


def _boss_acts(
    state: XiaolinState, settings: XiaolinSettings, rng: Rng, difficulty: Difficulty, name: str
) -> BotMove | None:
    """A boss's one temple action, or ``None`` to let the generic policy (a power) handle it."""
    return _first_move(_BOSS_ORDER, state, settings, rng, difficulty, name)


def _bot_acts(
    state: XiaolinState, settings: XiaolinSettings, rng: Rng, difficulty: Difficulty, name: str
) -> BotMove | None:
    """The bot's one action, or ``None`` when it has nothing worth doing.

    A boss runs its own order first (bank before power); if that finds nothing, it falls through to
    the generic order, which is where its power finally fires. Chase runs a stripped order that spends
    no powers at all.
    """
    chase = mechanic_of(state.bot.character.power) is Mechanic.BEAST_FORM

    if state.bot.character.tier == "boss" and not chase:
        boss = _boss_acts(state, settings, rng, difficulty, name)
        if boss is not None:
            return boss

    order = _CHASE_ORDER if chase else _GENERIC_ORDER
    return _first_move(order, state, settings, rng, difficulty, name)


def max_hand_size(player: Player, base: int) -> int:
    """The size limit, plus one while a "Third-Arm Sash" (a HAND_SIZE Wu) is held."""
    sash = any(mechanic_of(c.power) is Mechanic.HAND_SIZE for c in player.whole_hand)
    return base + int(sash)


def _draw_from_main(state: XiaolinState, player: Player) -> None:
    """Emergency draw from the shared pile; emptying it ends the run."""
    player.hand.append(state.card_deck.pop(0))
    if not state.card_deck:
        state.has_ended = True
