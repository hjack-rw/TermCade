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

from ..mechanics.powers import (
    ANIMATE_STAT,
    MORPH_ASIDE,
    MORPH_CONTESTED,
    NAMED_STAT_VALUE,
    Mechanic,
    is_gamble,
    is_uncontrolled,
    mechanic_of,
    roll_gamble,
)
from ..characters import chase, hannibal, jack
from ..mechanics.cards import hand_over
from ..schema.models import Card, Character, Player
from ..config.settings import XiaolinSettings, deposit_limit, player_actions, plays_keen
from ..schema.state import XiaolinState
from .training import add_progress, can_train, pick_stat, raise_stat, turn_over

# What a booster is worth in a showdown, since it carries no stats of its own.
BOOSTER_PREMIUM = 4

# The bot never banks its hand below this floor. A deposit requires more than DUEL_FLOOR left in
# hand (see `_bank_surplus`), so 2 is the minimum that still allows any deposit at all.
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
    state.undo_stash = None  # a new turn: last turn's actions are past undoing
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
    base_hand = settings.max_hand_size_player if is_player else settings.max_hand_size_bot
    over = len(player.whole_hand) - max_hand_size(player, base_hand)
    if over <= 0:
        if not player.hand:  # nothing fieldable — see `Player.hand` vs `inalienable_hand`
            _emergency_fill(state, player, settings, is_player=is_player)
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
        state.bot_actions_taken = settings.actions_per_turn_bot


def _emergency_fill(
    state: XiaolinState, player: Player, settings: XiaolinSettings, *, is_player: bool
) -> None:
    """Refill a hand with nothing FIELDABLE in it — own shelf first, then the pile (emptying it ends
    the run).

    ``empty_draw_limit`` is how many Wu the mercy PAYS, not the hand size it fills to — an inalienable
    Wu already held must not shrink the payout, so the count is against ``owed``, not against room
    alone. ``max_hand_size`` still caps it: the mercy may not overfill a hand.
    """
    base_hand = settings.max_hand_size_player if is_player else settings.max_hand_size_bot
    room = max_hand_size(player, base_hand) - len(player.whole_hand)
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
    # Prints 0/0/0; its swing is board-dependent and uncapped (see `duel.Duel._conduct_bonus`), so
    # the bot can't know its true value at decision time. Priced level with NULLIFY_CURSE.
    Mechanic.CONDUCT: 4,
    # The bot has no spend policy for this yet (temple_ai) — priced only to keep it from banking as junk.
    Mechanic.TRANSFER: 5,
    # Prints 0/0/0 — no spend policy yet, priced as a modest utility so it isn't banked as junk.
    Mechanic.REFRESH: 3,
    # Prints 0/0/0 but FIELDED it wins the showdown outright (see `bot.choose_card`, which always
    # fields it). No policy to field or wish it deliberately; priced only against banking it as junk.
    # (Deposited it is worth its 10 printed points, counted the ordinary way.)
    Mechanic.WISH: 10,
    # Prints ? ? ? but in the boost slot comes alive as a flat ANIMATE_STAT form — priced off that so
    # retuning the form re-prices the bot.
    Mechanic.ANIMATE: ANIMATE_STAT * 3,
    # Prints ? ? ?; the swap outlives the battle (see `duel.Duel._swap_stat_and_flip`) — no spend
    # policy yet, level with TRANSFER.
    Mechanic.STAT_SWAP: 5,
    # Never dealt (see `constants.in_pool`) — only reached by combining both halves — but still needs
    # a price so a bot holding one never banks it as junk. Same swap as STAT_SWAP, priced a step above.
    Mechanic.CHI_SWAP: 6,
}

# (Witchcraft is a CHARACTER power — no card carries it, so its table price is moot; it sits in
# `_STATS_ARE_THE_WHOLE_VALUE` below purely to satisfy the every-mechanic-is-accounted guard.)

# Mechanics whose printed stats are the whole value, declared rather than assumed. The two sets must
# cover every `Mechanic` — `test_every_mechanic_is_priced` enforces it. An unpriced `? ? ?` Wu reads as
# zero: the bot banks the strongest card in the game for 2 points.
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
        # Jack-Bot is an inalienable boss fixture, never pooled or bought — its -1/-1/-1 lands on the
        # opponent (`resolve.curse_from_boost`), not scored as its own printed stats, so there is
        # nothing here for a points-vs-stats check to weigh in the first place.
        Mechanic.BOT,
        # Worth more than its printed stats (it vetoes the elemental bonus and the prize's elemental
        # route both), but priced by stats alone deliberately — do not raise it.
        Mechanic.NULLIFY_ELEMENT,
        # Worth more than its printed stats (it reverses the elemental bonus), but priced by them —
        # the reversal is contextual, read by the bot's play-it-out eval, not here.
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
        # Prints real stats; its seize only decides level battles, and the bot has no policy to field
        # it for the seize — excused until it does.
        Mechanic.SEIZE_GROUND,
        # Prints real stats; its win-vs-construct is entirely contextual — worth nothing outside a
        # Jack fight, and even then only in two of his four states. Read by the bot's play-it-out
        # eval, not priced here.
        Mechanic.HACK,
        # Prints real stats; the steal it buys is read by the bot's play-it-out eval (it already has
        # `bot.steal_target` to weigh the hand it would take), not priced flat here — a steal against
        # an empty hand and deck is worth nothing, and no fixed number captures that.
        Mechanic.STEAL,
        # Prints real stats; its undo is a temple ``use`` the bot never spends (no policy), so on the
        # table it is only ever the 1/1/1 it wagers. Excused, not priced.
        Mechanic.AMEND,
        # A summon: on the table it is just its printed stats (the fielded horde/clone). Its extra worth
        # is the temple +training, a use the bot has no policy for — so table value is the stats alone.
        Mechanic.TRAIN_BOOST,
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
    # The Sapphire Dragon prints no stats and LOSES the showdown if fielded — its whole worth is the
    # temple level it grants. Priced so the bot holds it over junk rather than banking it away; like the
    # WISH above, temple_ai has no policy to actually spend it. (Deposited, it is its printed points.)
    if is_uncontrolled(card.power):
        return 8
    stats = sum(abs(v) for v in card.stats.values() if v is not None)
    mechanic = mechanic_of(card.power)
    premium = BOOSTER_PREMIUM if mechanic is Mechanic.BOOST else 0
    return stats + _MECHANIC_VALUE.get(mechanic, 0) + premium


def pick_deposit(hand: list[Card], difficulty: Difficulty, wear_limit: int) -> Card | None:
    """Which Wu the bot deposits, by difficulty. ``None`` when nothing in hand is worth points.

    Hard takes the highest points, full stop — points are the win condition. Easy sheds its least
    useful Wu and hoards weapons, so it duels well but never closes.
    """
    # A Treasurebox is worth far more fielded (it wins the showdown) than its 10 banked points, so the
    # bot keeps it for the duel rather than cashing it — see bot.choose_card, which always fields it.
    candidates = [
        card for card in hand if card.points > 0 and mechanic_of(card.power) is not Mechanic.WISH
    ]
    if not candidates:
        return None
    # A Wu one showdown from wearing out banks ITSELF, free (see wear.py) — spending the turn's
    # action on it wastes the action. Prefer any other candidate; near-worn only when that is all
    # there is.
    fresh = [card for card in candidates if card.uses < wear_limit - 1]
    candidates = fresh or candidates
    if plays_keen(difficulty):
        return max(candidates, key=lambda c: c.points)
    return min(candidates, key=lambda c: (duel_value(c), -c.points))


def counters_against(character: Character) -> frozenset[Mechanic]:
    """The keyed counter mechanics that specifically answer ``character`` — empty for a boss with
    none built yet (Wuya). Every one of them is an ordinary pool Wu any duelist can hold and
    play against anyone; a boss is simply the one meant to be wary of its own answers."""
    if mechanic_of(character.power) is Mechanic.BOT:
        return jack.counter
    if character.name == "Hannibal_Roy_Bean":
        return hannibal.counter
    if character.name == "Chase_Young":
        return chase.counter
    return frozenset()


def _priority_deposit(bot: Player, wear_limit: int) -> Card | None:
    """Any boss with a keyed counter set (`counters_against`) banks one the instant they hold it —
    stolen, or simply drawn, since these are ordinary pool Wu picked up like anyone else's — ahead
    of `pick_deposit`'s own points-first rule. Getting it out of the player's reach matters more
    than its bank value; the same wear-free exception `pick_deposit` grants everything else applies
    here too. ``None`` when there is none held (or none to be wary of), so the caller falls through
    to the normal policy."""
    wary_of = counters_against(bot.character)
    if not wary_of:
        return None
    counters = [card for card in bot.hand if mechanic_of(card.power) in wary_of]
    if not counters:
        return None
    fresh = [card for card in counters if card.uses < wear_limit - 1]
    return max(fresh or counters, key=lambda c: c.points)


def bank_value(card: Card, rng: Rng) -> int:
    """What depositing this Wu pays: its printed points, unless it is the gamble, which is rolled.

    Both duelists bank on the same terms and neither is told the gamble's worth — the bot picks it by
    the DB expected value (``GAMBLE_SPREAD``), blind like a player eyeing a ``?``.
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
    while state.bot_actions_taken < settings.actions_per_turn_bot:
        acted = _bot_acts(state, settings, rng, difficulty, name)
        if acted is None:
            break
        log.append(acted)
    return log or [BotMove(PASSED, f"{name} did nothing this turn.")]


# The bot's temple actions, each a self-contained attempt that either DOES the thing and returns its
# log line, or returns ``None`` to say "not now, try the next". A policy is just an ORDER over these,
# so a change to how the bot banks changes it for every duelist that banks — one place banks.


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
    """Wuya's temple action: call the most valuable lost Wu back, paying no Wu for it. A known weapon
    from the lost beats a blind draw, and her bond finds the best one, not merely the oldest."""
    from ..characters.wuya import recall_index, worth_recalling

    if mechanic_of(state.bot.character.power) is Mechanic.WITCHCRAFT and worth_recalling(state):
        revived = state.lost.pop(recall_index(state))
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
        can_train(state.bot, settings)
        and not state.bot.just_trained
        and settings.train_length_bot - state.bot.training <= _TRAIN_WITHIN
    ):
        state.bot_actions_taken += 1
        if add_progress(state.bot, settings, is_player=False):
            stat = pick_stat(state.bot, settings)
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
        settings.actions_per_turn_bot
    ):
        banked = _priority_deposit(bot, settings.wear_limit) or pick_deposit(
            bot.hand, difficulty, settings.wear_limit
        )
        if banked is not None:
            points = bank_value(banked, rng)
            bot.points = max(0, bot.points + points)  # a bad gamble cannot go below zero
            bot.remove_card(banked)
            if mechanic_of(banked.power) is not Mechanic.WISH:
                bot.vault.append(banked)  # into the Vault, where the player's Treasurebox can steal it
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
            settings,
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


def _construct_jong(
    state: XiaolinState, settings: XiaolinSettings, rng: Rng, difficulty: Difficulty, name: str
) -> BotMove | None:
    """Assemble Mala Mala Jong the moment the full set is in hand. The construct races the game to its
    close for an outright win, so it outranks every other temple move — take it and lock the hand."""
    from .actions import can_construct, construct_jong

    if not can_construct(state, settings.actions_per_turn_bot, is_player=False):
        return None
    construct_jong(state, is_player=False)
    return BotMove(POWER, f"{name} assembled Mala Mala Jong — race it to the end.")


def _self_correct_good_jack(
    state: XiaolinState, settings: XiaolinSettings, rng: Rng, difficulty: Difficulty, name: str
) -> BotMove | None:
    """Jack alone: the moment the combined Ying-Yang Yo-Yo is in hand and he's worn as Good Jack,
    flip back to himself. Good Jack forfeits every one of his bot forms while worn (`Duel._boost`'s
    gate on `Player.yoyo_flipped`), so there is no reason to stay a moment longer than the Yo-Yo
    makes him."""
    from .actions import can_self_correct_yoyo, self_correct_yoyo

    bot = state.bot
    if mechanic_of(bot.character.power) is not Mechanic.BOT or not bot.yoyo_flipped:
        return None
    if not can_self_correct_yoyo(state, settings.actions_per_turn_bot, is_player=False):
        return None
    self_correct_yoyo(state, is_player=False)
    return BotMove(POWER, f"{name} corrected {jack.GOOD_JACK_NAME} back to himself.")


# The boss temple order: bank the surplus AHEAD of any power. A power is not taken here; it falls
# through to the generic path below, which fires one only once the surplus is gone.
_BOSS_ORDER = (
    _construct_jong,
    _self_correct_good_jack,
    _draw_thin_hand,
    _fly_early_bird,
    _recall_witchcraft,
    _bank_surplus,
)

# The generic order: a power first (when one beats banking), then the pile raid, the recall, the
# training cash-in, a thin-hand draw, and banking last.
_GENERIC_ORDER = (
    _construct_jong,
    _play_power,
    _fly_early_bird,
    _recall_witchcraft,
    _cash_training,
    _draw_thin_hand,
    _bank_surplus,
)

# Chase Young's order: only trains, draws, or banks — never spends a Wu's power, never flies the
# Early Bird.
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
    from . import bot as bot_module  # deferred: bot.py imports duel_value from this module

    # A construct's hand is locked: it draws nothing, banks nothing, recalls nothing (Wuya's witchcraft
    # would otherwise pull a Wu into the sealed hand, and banking could deposit a part and silently
    # break the set). It only races — so once in form the bot passes every temple turn. Construct itself
    # still fires below, because a duelist is not yet in form when it decides to assemble.
    if bot_module.is_jong(state.bot):
        return None

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
