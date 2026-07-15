"""The vault turn — what both duelists do between showdowns.

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
from .models import Card, Player
from .settings import XiaolinSettings, is_hard
from .state import XiaolinState

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

    Runs each time control returns to the vault (between showdowns). Re-balances until both hands
    are stable — loops :func:`oversee_hand_size` over both until neither reports more work. The
    player's interactive over-limit discard is handled by the screen *before* this runs, so any
    shedding here (the bot's) is random.

    This is where a turn turns over, so this is where the action counters are cleared — and then
    immediately spent again for anyone the mercy rule has to deal back in (:func:`_charge_the_turn`).
    """
    if state.player.points >= settings.point_limit or state.bot.points >= settings.point_limit:
        state.has_ended = True

    state.actions_taken = 0
    state.bot_actions_taken = 0

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
    player = state.player if is_player else state.bot
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
        player.deck.append(card)
    return False


def _charge_the_turn(state: XiaolinState, settings: XiaolinSettings, *, is_player: bool) -> None:
    """Being dealt back in *is* the turn's action, not a gift on top of it.

    The mercy rule hands a duelist with nothing fieldable a hand off the pile. That is the same
    income a Draw buys, so it costs the same thing: the turn it lands on opens already spent.
    """
    if is_player:
        state.actions_taken = settings.actions_per_turn
    else:
        state.bot_actions_taken = settings.actions_per_turn


def _emergency_fill(state: XiaolinState, player: Player, settings: XiaolinSettings) -> None:
    """Refill a hand with nothing playable in it — from its own shelf first, then the pile.

    Your own deck answers before the pile does: those Wu are already yours, shelved by your own hand,
    and handing you fresh cards off the pile while your shelf sits full would be paying you for
    forgetting about it. The pile is the *last* resort, and emptying it ends the run.

    "Nothing playable" is not the same as "nothing at all". A dragon (``boost``/0) can only ever be
    laid as a boost — it is never staked, lost or fielded as a Wu — so a hand holding only one has no
    answer to a showdown and is empty for every purpose that decides a duel. An amplifier
    (``boost``/+1) is a different matter: it sits in the hand and *can* be fielded, badly.

    ``empty_draw_limit`` is the hand you are brought back up to, not a count of cards handed over.
    A Wu that cannot be fielded still fills one of those slots, so a duelist holding one is dealt one
    fewer: it is a mercy rule, and what is already on the shelf counts toward the mercy.
    """
    target = min(settings.empty_draw_limit, max_hand_size(player, settings.max_hand_size))
    while player.deck and len(player.whole_hand) < target:
        player.hand.append(player.deck.pop(0))
    while state.card_deck and len(player.whole_hand) < target:
        _draw_from_main(state, player)


# What a Wu is worth in a showdown when its printed stats say nothing about it. A card that resolves
# at play prints `? ? ?` or 0/0/0, and reading the stats off it gives *zero* — which is how the whole
# in-duel half of the card pool came to look like junk to the opponent, get banked first, and be
# counted as an empty slot when a wager was priced.
#
# Each number is what the Wu is *worth on the table*, in the same currency as a printed stat:
#   pours  — it puts NAMED_STAT_VALUE into a stat of your choosing; that is what it is worth.
#   negations — it takes a whole line off the opponent for the battle, which is worth more than any
#     one Wu contributes, and the three of them are the strongest cards in the game.
_MECHANIC_VALUE: dict[Mechanic, int] = {
    # The Morpher prints `? ? ?` and takes a known shape at play, so it is priced off that shape
    # rather than a flat premium — retune the rule and the bot re-prices itself.
    Mechanic.MORPH: MORPH_ASIDE * 2 + MORPH_CONTESTED,
    Mechanic.HYDROKINESIS: NAMED_STAT_VALUE,
    Mechanic.MISFORTUNE: NAMED_STAT_VALUE,
    Mechanic.CONTAINMENT: 5,
    Mechanic.SUBJUGATION: 5,
    Mechanic.REVERSAL: 4,
}

# Mechanics whose printed stats are the whole of what they are worth, declared rather than assumed.
#
# The two sets together must cover every `Mechanic` — `test_every_mechanic_is_priced` fails otherwise,
# and that test is the whole point. A new Wu that resolves at play prints `? ? ?`, so `duel_value`
# reads *zero* off it and nothing complains: the opponent banks the strongest card in the game for two
# points and prices a wager as though the slot were empty. That is not hypothetical — it is what
# happened to the pours and the negations, and it cost the opponent 16 points of win rate before the
# simulation caught it. So a mechanic must be *priced or excused*, never merely forgotten.
#
# Two of them are excused for a *different* reason: they are worth nothing on the table at all, and
# that is deliberate. Kept apart from the rest because "its stats say what it is worth" and "it is
# worth nothing" are different claims, and only the second one may price at zero.
_WORTH_NOTHING_ON_THE_TABLE: frozenset[Mechanic] = frozenset(
    {
        Mechanic.FILLER,  # deck padding: no stats, no power, no business being fielded
        # The joke Wu prints `? ? ?` and does nothing in a battle. Everything it is worth is at the
        # vault, where it is rolled for points — so zero on the table is honest, not an oversight.
        Mechanic.GAMBLE,
    }
)

_STATS_ARE_THE_WHOLE_VALUE: frozenset[Mechanic] = _WORTH_NOTHING_ON_THE_TABLE | frozenset(
    {
        Mechanic.PRINTED_STATS,  # the stats *are* the Wu
        Mechanic.INITIATIVE,  # its bonus is a hand power; in a battle it is only its stats
        Mechanic.HAND_SIZE,  # likewise — it buys a hand slot, not a blow
        Mechanic.HAND_FIZZLE,  # unprinted (see `powers.UNPRINTED`)
        Mechanic.CHRONOKINESIS,  # a vault power; on the table it is just its printed stats
        Mechanic.DIASKOPIA,  # likewise
        Mechanic.TELESKOPIA,  # likewise
        Mechanic.TELEPATHEIA,  # likewise
        Mechanic.ATTRACTION,  # likewise
        Mechanic.REPULSION,  # likewise
        Mechanic.ANABIOSIS,  # likewise — it acts on the lost pile, never in a battle
        # The dragon and the booster carry no stats but decide duels — they are priced by
        # BOOSTER_PREMIUM in `duel_value` rather than here, which is the older seam.
        Mechanic.DRAGON,
        Mechanic.BOOST,
        # The Serpent's Tail voids the elemental bonus for both duelists all showdown, and vetoes the
        # prize's elemental route with it. That is plainly worth more than the stats it prints — and it
        # is *meant* to be: the veto is the card, and the author has priced it as such (4 points, the
        # top of the pool). It is not underpriced here by oversight. Do not "fix" it.
        Mechanic.INTANGIBLE,
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
    """Which Wu the bot banks this turn — its deposit skill, dialled by difficulty.

    **The hard bot takes the points, and it is right to.** A run is won by banking to
    ``point_limit``, so the strong line is to cash the biggest number in hand and fight on with what
    is left. Protecting good Wu is the clever-sounding play and it loses: over 250 runs, weighting
    the choice by ``duel_value`` costs the bot ground at every weight tried, and refusing to bank a
    booster costs it five points of win rate. Points are not merely the currency — they are the win
    condition, and a duelist who hoards its weapons never reaches it.

    The easy bot does the reverse: it sheds its least useful Wu and holds its weapons. It duels
    exactly as well as the hard bot — it simply never banks enough to close a run out.

    Returns ``None`` when nothing in hand is worth points.
    """
    candidates = [card for card in hand if card.points > 0]
    if not candidates:
        return None
    if is_hard(difficulty):
        return max(candidates, key=lambda c: c.points)
    return min(candidates, key=lambda c: (duel_value(c), -c.points))


def bank_value(card: Card, rng: Rng) -> int:
    """What depositing this Wu pays. Its printed points — unless it is the gamble, which is rolled.

    The bot banks on the same terms as the player. Neither is told what the gamble is worth, and
    neither finds out until it is spent: the bot picks it by the expected value in the card DB (see
    ``GAMBLE_SPREAD``), the same way a player eyeing a ``?`` has only the odds to go on.
    """
    return roll_gamble(rng) if is_gamble(card.power) else card.points


# The names of the actions a vault turn can spend, for whoever spends them. One list, so a move of
# theirs and the same move of yours are filed under the same word in the Game Log — "Deposit" is
# "Deposit" whichever side of the table it happened on. (A power is filed under its own name, and the
# Early Bird under this one, because the Bird is a power that belongs to no Wu.)
# The PLACE, not the verb. You go to the Vault; what you do there is bank a Wu, and the line under
# the title says so ("You deposited Golden Tiger Claws for 2 pts"). A title names where a move was made;
# the prose names what it was.
VAULT = "Vault"
DRAW = "Draw"
EARLY_BIRD = "Early Bird"
PASSED = "Pass"
# Every Wu power is one action, and the game already has a word for it: the vault offers "Use a Power",
# the rulebook says power, the code says `use_power`. A second word for the same thing is the thing
# that reads wrong, whichever word it is.
#
# The *power's own name* goes in the line, not in the title: a title is a label, and a label that
# changes with every card cannot be scanned for.
POWER = "Power"


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
    """The bot's between-showdown vault turn; returns a short log of what it did, for the player.

    One turn, one action — the rule that binds the player binds the bot. It used to bank *and* top
    its hand back up for free, which is not a game either duelist is playing: a hand that refills
    itself is not a resource, and a Wu spent out of one costs nothing.
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


def _bot_acts(
    state: XiaolinState, settings: XiaolinSettings, rng: Rng, difficulty: Difficulty, name: str
) -> BotMove | None:
    """The bot's one action, or ``None`` when it has nothing worth doing.

    Draw first when the hand is too thin to field a full showdown: a duelist who banks its way down
    to one Wu can only ever be wagered one Wu, and wins nothing that way. Otherwise bank — points
    are the win condition, and the bot that hoards its weapons never reaches it (see
    :func:`pick_deposit`).
    """
    # A Wu's power, when one of them is worth more than the points it would bank. The opponent reads
    # only what a player could — see `vault_ai`, which is also where two of the Wu are explained as
    # worthless *to it* and banked instead.
    from .actions import early_bird, use_power  # local: actions imports this module
    from .vault_ai import choose_early_bird, choose_vault_power

    play = choose_vault_power(state, settings)
    if play is not None:
        use_power(
            state,
            play.card,
            is_player=False,
            priority=play.priority,
            target=play.target,
            rng=rng,
        )
        return BotMove(
            POWER, f"{name} played {play.card.power.name} from the {play.card.name}."
        )

    # The Early Bird, before drawing or banking: a Wu off the pile with no showdown beats either, and
    # it is the only action here that takes from the *shared* pile rather than the bot's own shelf.
    bird = choose_early_bird(state, settings)
    if bird is not None:
        early_bird(state, bird, is_player=False)
        return BotMove(
            EARLY_BIRD,
            f"{name} used Early Bird and sacrificed {bird.name} — the next Wu was taken from "
            "under your nose.",
        )

    if len(state.bot.hand) < settings.max_wager and state.bot.deck:
        drawn = state.bot.deck.pop(0)
        state.bot.hand.append(drawn)
        state.bot_actions_taken += 1
        return BotMove(DRAW, f"{name} drew a Wu from their deck.")

    # Mirrors `can_deposit`: never cash the last card out of the hand.
    if len(state.bot.hand) > DUEL_FLOOR:
        banked = pick_deposit(state.bot.hand, difficulty)
        if banked is not None:
            points = bank_value(banked, rng)
            state.bot.points = max(0, state.bot.points + points)  # a bad gamble cannot go below zero
            state.bot.remove_card(banked)
            state.bot_actions_taken += 1
            return BotMove(
                VAULT,
                f"{name} deposited {banked.name} for {points} pt{'s' if points != 1 else ''}.",
            )
    return None


def max_hand_size(player: Player, base: int) -> int:
    """The size limit, plus one while a "Third-Arm Sash" (a HAND_SIZE Wu) is held."""
    sash = any(mechanic_of(c.power) is Mechanic.HAND_SIZE for c in player.whole_hand)
    return base + int(sash)


def _draw_from_main(state: XiaolinState, player: Player) -> None:
    """Emergency draw from the shared pile; emptying it ends the run."""
    player.hand.append(state.card_deck.pop(0))
    if not state.card_deck:
        state.has_ended = True
