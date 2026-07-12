"""The vault turn — what happens on each return to the vault, between showdowns.

Keeps a hand from exceeding its size limit (surplus goes to the personal deck) and flags the run
finished when a point limit is reached or the draw pile runs dry. A short hand is *not* topped up
automatically — the player refills it themselves with Draw; only a fully empty hand is emergency-
drawn from the main pile, so the duel loop can still terminate rather than strand on an empty hand.
"""

from __future__ import annotations

from termcade.core.rng import Rng
from termcade.core.settings import Difficulty

from .mechanics.powers import is_gamble, roll_gamble
from .models import Card, Player
from .settings import XiaolinSettings, is_hard
from .state import XiaolinState

# What a booster (``boost``/+1) or the Morpher (``play``/+1) is worth in a showdown. They carry no
# stats of their own, so without this premium a skilled bot would happily bank them for points.
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
    """
    if state.player.points >= settings.point_limit or state.bot.points >= settings.point_limit:
        state.has_ended = True

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
    tops up manually with Draw), unless the hand is *empty*, which is emergency-drawn from the main
    pile. Returns ``False`` after shedding (the caller re-checks), ``True`` otherwise.
    """
    player = state.player if is_player else state.bot
    over = len(player.whole_hand) - max_hand_size(player, settings.max_hand_size)
    if over <= 0:
        if not player.hand:  # nothing fieldable — see `Player.hand` vs `inalienable_hand`
            _emergency_fill(state, player, settings)
        return True
    if state.has_ended:
        return True  # game over — leftover cards stay, they still count toward the final score

    for _ in range(over):
        card = rng.choice(player.hand)
        player.remove_card(card)
        player.deck.append(card)
    return False


def _emergency_fill(state: XiaolinState, player: Player, settings: XiaolinSettings) -> None:
    """Refill a hand with nothing playable in it, from the main pile. Emptying the pile ends the run.

    "Nothing playable" is not the same as "nothing at all". A dragon (``boost``/0) can only ever be
    laid as a boost — it is never staked, lost or fielded as a Wu — so a hand holding only one has no
    answer to a showdown and is empty for every purpose that decides a duel. An amplifier
    (``boost``/+1) is a different matter: it sits in the hand and *can* be fielded, badly.

    ``empty_draw_limit`` is the hand you are brought back up to, not a count of cards handed over.
    A Wu that cannot be fielded still fills one of those slots, so a duelist holding one is dealt one
    fewer: it is a mercy rule, and what is already on the shelf counts toward the mercy.
    """
    target = min(settings.empty_draw_limit, max_hand_size(player, settings.max_hand_size))
    while state.card_deck and len(player.whole_hand) < target:
        _draw_from_main(state, player)


def duel_value(card: Card) -> int:
    """Roughly what ``card`` is worth held in a showdown.

    Stat magnitude, not signed value: a negative stat is a *weapon* (``powers`` mirrors it onto the
    opponent's queue), so it is as worth keeping as a positive one. Boosters and the Morpher carry no
    stats but decide duels, hence the premium.
    """
    stats = sum(abs(v) for v in card.stats.values() if v is not None)
    special = card.power.effect == 1 and card.power.trigger in ("boost", "play")
    return stats + (BOOSTER_PREMIUM if special else 0)


def pick_deposit(hand: list[Card], difficulty: Difficulty) -> Card | None:
    """Which Wu the bot banks this turn — its deposit skill, dialled by difficulty.

    Both bots always race for points (a bot that hoards can never reach ``point_limit``); they
    differ in *what* they give up. An easy bot chases the biggest number and cheerfully cashes the
    Wu it needed, which is what makes it lean so hard on whatever it keeps. The hard bot sheds its
    least useful Wu instead — the gag card, deck filler, a 1-point trinket — and holds its weapons.

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


def bot_turn(
    state: XiaolinState,
    settings: XiaolinSettings,
    *,
    rng: Rng,
    difficulty: Difficulty = Difficulty.NORMAL,
) -> list[str]:
    """The bot's between-showdown vault turn; returns a short log of what it did, for the player.

    It deposits (see :func:`_bot_deposits` — how it banks points toward the win) then refills one
    card toward the hand limit from its own deck, since it has no manual Draw as the player does.
    """
    log = _bot_deposits(state, settings, rng, difficulty)
    _bot_refill(state, settings)
    return log or [f"{state.bot.character.name.split('_')[0]} passed"]


def _bot_deposits(
    state: XiaolinState, settings: XiaolinSettings, rng: Rng, difficulty: Difficulty
) -> list[str]:
    """Up to ``deposit_limit`` deposits: swap each ``use``/+1 Wu for a fresh draw, then bank the
    card :func:`pick_deposit` chooses.

    Banks *any* card, matching the rule the player's Deposit screen offers (:func:`~.actions.deposit`).
    Restricting the bot to ``use``-trigger Wu left it with exactly one bankable card in the whole
    pile, so it could never race the player to ``point_limit``.
    """
    name = state.bot.character.name.split("_")[0]
    log: list[str] = []
    deposits = 0

    for card in list(state.bot.whole_hand):  # snapshot: the hand mutates as cards leave
        if deposits >= settings.deposit_limit:
            break
        if card.power.trigger == "use" and card.power.effect == 1 and state.card_deck:
            _draw_from_main(state, state.bot)  # trade the power card for a fresh one
            state.bot.remove_card(card)
            deposits += 1
            log.append(f"{name} played {card.name} and drew a Wu")

    # Mirrors `can_deposit`: never cash the last card out of the hand.
    while deposits < settings.deposit_limit and len(state.bot.hand) > DUEL_FLOOR:
        banked = pick_deposit(state.bot.hand, difficulty)
        if banked is None:  # nothing in hand is worth points
            break
        points = bank_value(banked, rng)
        state.bot.points = max(0, state.bot.points + points)  # a bad gamble cannot go below zero
        state.bot.remove_card(banked)
        deposits += 1
        log.append(f"{name} deposited {banked.name} for {points} pt{'s' if points != 1 else ''}")
    return log


def _bot_refill(state: XiaolinState, settings: XiaolinSettings) -> None:
    """Fill the bot's hand from its personal deck — it has no manual Draw of its own.

    To the limit, not one card at a time: a duelist sitting on a deck while its hand has room is
    simply not playing. (In practice the deck is usually empty — it is only fed by shedding surplus
    over the hand limit — so this is the ceiling, not the bot's income.)
    """
    limit = max_hand_size(state.bot, settings.max_hand_size)
    while state.bot.deck and len(state.bot.whole_hand) < limit:
        state.bot.hand.append(state.bot.deck.pop(0))


def max_hand_size(player: Player, base: int) -> int:
    """The size limit, plus one while a "Third-Arm Sash" (a hand power with effect −1) is held."""
    sash = any(c.power.trigger == "hand" and c.power.effect == -1 for c in player.whole_hand)
    return base + int(sash)


def _draw_from_main(state: XiaolinState, player: Player) -> None:
    """Emergency draw from the shared pile; emptying it ends the run."""
    player.hand.append(state.card_deck.pop(0))
    if not state.card_deck:
        state.has_ended = True
