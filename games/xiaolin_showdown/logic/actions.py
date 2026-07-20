"""Pure temple actions between duels — no I/O: deposit, use-power, and draw.

Draw pulls from the player's *personal* deck, which fills when they shelve surplus cards over the
hand limit. Together, shelving a card and drawing a fresh one is how the player cycles their hand.
"""

from __future__ import annotations


from termcade.core.rng import Rng

from .constants import WEAR_LIMIT
from .mechanics.scoring import initiative
from .mechanics.powers import Mechanic, mechanic_of, trigger_of
from .models import Card
from .settings import XiaolinSettings, deposit_limit, player_actions
from .state import XiaolinState
from .training import add_progress, can_train, doubles_training, payout_ready
from .turn import bank_value, duel_value, max_hand_size, shelve
from .power_effects import FIZZLE_MESSAGE, PowerReport, _Spend, _fire

# Whether Wuya's witchcraft-restored Wu wear out (vault on the third use) or reuse forever, and
# whether it returns them at all. Balance knobs for how hard the witch is — the harness flips them
# (XS_WITCH_NOWEAR / XS_WITCH_OFF) to measure the tireless and the no-return forms.
WITCHCRAFT_WEARS = True
WITCHCRAFT_RETURNS = True

# Not a power: the Early Bird logs its own line, so it stays a plain one-form message.
EARLY_BIRD_MESSAGE = "You outran your opponent to the next Wu: {taken} is yours. You gave up your {given} for it."

SPENT_MESSAGE = "You have already acted this turn."


def has_acted(state: XiaolinState, actions_per_turn: int) -> bool:
    """Is the turn's action already spent? Banking, using a power and drawing all cost the same one.

    The single budget is the whole of the temple economy: a Wu spent is a Wu not replaced, and the
    Wu whose power is worth more than its points is a Wu you must choose to keep.
    """
    return state.actions_taken >= actions_per_turn


def spent_gate(state: XiaolinState, actions: int) -> str | None:
    """``SPENT_MESSAGE`` if the turn's one action is already used, else ``None`` — the shared head of
    the ``*_blocked`` predicates, so the "one action a turn" policy lives in one place."""
    return SPENT_MESSAGE if has_acted(state, actions) else None


def deposit_blocked(state: XiaolinState, actions_per_turn: int) -> str | None:
    """Why a deposit is disallowed right now, or ``None`` when it is allowed.

    The ``can_*`` predicates are defined as "no reason", so a greyed action and the explanation for
    it can never disagree.
    """
    if spent := spent_gate(state, actions_per_turn):
        return spent
    if state.deposits_taken >= deposit_limit(actions_per_turn):
        return "No more deposits this turn."
    if len(state.player.hand) <= 1:
        return "Only one Wu left in hand."
    return None


def can_deposit(state: XiaolinState, actions_per_turn: int) -> bool:
    """A hand card may be cashed for points, unless it would empty the hand or the turn's action is
    already spent."""
    return deposit_blocked(state, actions_per_turn) is None


def deposit(state: XiaolinState, card: Card, *, rng: Rng) -> int:
    """Cash ``card`` from the player's hand; counts against the turn limit. Returns what it paid.

    Usually its printed points. A GAMBLE Wu is rolled instead, and can pay less than nothing — but
    never below zero overall: a bad roll costs you your banked points, not your whole run.

    The derived ``Player.initiative`` updates itself when the hand changes.
    """
    state.player.hand.remove(card)
    paid = bank_value(card, rng)
    state.player.points = max(0, state.player.points + paid)
    state.actions_taken += 1
    state.deposits_taken += 1
    return paid


def draw_blocked(state: XiaolinState, settings: XiaolinSettings) -> str | None:
    """Why a draw is disallowed right now, or ``None`` when it is allowed.

    A full hand no longer blocks it: instead of growing the hand, Draw *swaps* — you shelve a Wu and
    take one back (see :func:`swap_from_hand`), so a stuck hand can still cycle.
    """
    if spent := spent_gate(state, player_actions(state, settings)):
        return spent
    if not state.player.deck:
        return "Your personal deck is empty."
    return None


def can_draw(state: XiaolinState, settings: XiaolinSettings) -> bool:
    """The player may draw — the deck holds a Wu and this turn's action is unspent. A full hand swaps
    rather than grows."""
    return draw_blocked(state, settings) is None


def draw_swaps(state: XiaolinState, settings: XiaolinSettings) -> bool:
    """Whether a Draw would SWAP (hand already full) rather than simply add a Wu."""
    return len(state.player.whole_hand) >= max_hand_size(state.player, settings.max_hand_size)


def draw(state: XiaolinState) -> Card:
    """Pull the top Wu of the player's personal deck into their hand; costs the turn's action."""
    card = state.player.deck.pop(0)
    state.player.hand.append(card)
    state.actions_taken += 1
    return card


def swap_from_hand(state: XiaolinState, shelved: Card, *, rng: Rng) -> Card:
    """A full hand's Draw: shelve ``shelved`` and take one back, for the turn's one action.

    Draw FIRST, then shelve — so the Wu you take is whatever the deck already held, never the one you
    are putting down. The shelved Wu is then shuffled into the deck for later. The hand ends the same
    size, and the swap is never a wasted action that hands you back your own card.
    """
    drawn = state.player.deck.pop(0)
    state.player.hand.append(drawn)
    state.player.remove_card(shelved)
    shelve(state.player, shelved, rng=rng)
    state.actions_taken += 1
    return drawn


def train_blocked(state: XiaolinState, actions_per_turn: int) -> str | None:
    """Why training is disallowed right now, or ``None`` when it is allowed.

    A waiting payout is never blocked: the 10 fills already paid for it, so picking the stat is
    free even on a spent turn.
    """
    if payout_ready(state.player):
        return None
    if state.player.just_trained:
        return "Your training is now complete!"
    if not can_train(state.player):
        return "Nothing left to train."
    if spent := spent_gate(state, actions_per_turn):
        return spent
    return None


def train(state: XiaolinState) -> bool:
    """Spend the turn's action on the bar. Returns whether the payout is now waiting.

    A Ring of Nine Xing in hand doubles the point earned, as it doubles a lost showdown's."""
    state.actions_taken += 1
    return add_progress(state.player, 2 if doubles_training(state.player) else 1)


def usable_powers(state: XiaolinState, actions_per_turn: int, *, is_player: bool = True) -> list[Card]:
    """Wu whose power this duelist can actively use now: a hand power-up (``hand``/+1), or a
    ``use``-trigger Wu while the turn's action is unspent — and only if it has something to act on."""
    unspent = state.actions_spent(is_player) < actions_per_turn
    mine = state.duelist(is_player)
    return [
        card
        for card in mine.whole_hand
        if mechanic_of(card.power) is Mechanic.HAND_FIZZLE
        or (trigger_of(card.power) == "use" and unspent and _has_target(state, card, is_player))
    ]


def _has_target(state: XiaolinState, card: Card, is_player: bool = True) -> bool:
    """Is there anything for this Wu's power to act on?

    A Wu that reveals is worth nothing against nothing: an opponent holding no personal deck, or a
    drained draw pile. Offering it anyway would sell a duelist a Wu for an empty list. Only the
    revealing powers ask this — the gag Wu fizzles by design, and Chronokinesis against an empty
    pile ends the run, which is a fizzle a duelist is allowed to walk into.
    """
    me, them = state.duelist(is_player), state.opponent(is_player)
    mechanic = mechanic_of(card.power)
    if mechanic is Mechanic.READ_DECK:
        return bool(them.deck)
    if mechanic is Mechanic.SCRY:
        return bool(state.card_deck)
    if mechanic is Mechanic.FETCH:
        return bool(me.deck)
    if mechanic is Mechanic.BOUNCE:
        # The opponent is held to the rule that binds you: a deposit may never empty a hand.
        return len(them.hand) > 1
    if mechanic is Mechanic.LUCK:
        return bool(state.lost)  # nothing has been lost yet — there is nobody to call back
    if mechanic is Mechanic.REFRESH:
        return bool(state.used)  # nobody has used anything yet — there is nothing to call back
    if mechanic is Mechanic.TRANSFER:
        return bool(them.hand)  # a one-way gift is not a swap
    return True


def early_bird_options(state: XiaolinState, *, is_player: bool = True) -> list[Card]:
    """The Wu you may surrender to the Early Bird: your *highest* initiative, by magnitude.

    Magnitude, not sign: a ``-2`` is as much a Wu of speed as a ``+2``. One drags them, one lifts you,
    and both open the gap by two — so both are the price, and neither is a cheaper one.

    A choice, not a pick: several Wu can tie at the top, and which one you let go of is yours to say.
    That it must be a *highest* one is what keeps the rule honest — outrunning them costs you the very
    thing you outran them with, so the Early Bird cannot be flown twice on the same wings.
    """
    me = state.duelist(is_player)
    # Wuya's witchcraft cheats the toll: she gives up her WEAKEST Wu, not her fastest — the bird
    # costs her a scrap, so she snatches the pile almost for free. Anyone else pays in speed.
    if mechanic_of(me.character.power) is Mechanic.WITCHCRAFT and me.hand:
        cheapest = min(duel_value(card) for card in me.hand)
        return [card for card in me.hand if duel_value(card) == cheapest]
    speed = [card for card in me.hand if card.power.initiative_bonus]
    if not speed:
        return []
    highest = max(abs(card.power.initiative_bonus) for card in speed)
    return [card for card in speed if abs(card.power.initiative_bonus) == highest]


def early_bird_blocked(state: XiaolinState, settings: XiaolinSettings) -> str | None:
    """Why the Early Bird cannot be flown right now, or ``None`` when it can."""
    if spent := spent_gate(state, player_actions(state, settings)):
        return spent
    if not state.card_deck:
        return "No Wu left on the pile."
    lead = initiative_lead(state, is_player=True)
    if lead < settings.early_bird_gap:
        return (
            f"Your initiative lead is {lead}. You need {settings.early_bird_gap} "
            f"to take the next Wu without a duel."
        )
    if not early_bird_options(state):
        return "You hold no initiative Wu to give up."
    return None


def can_early_bird(state: XiaolinState, settings: XiaolinSettings) -> bool:
    """Outrun them by enough and the next Wu is yours without a showdown."""
    return early_bird_blocked(state, settings) is None


def initiative_lead(state: XiaolinState, *, is_player: bool) -> int:
    """How far ahead of the other duelist this one is on initiative — never below zero.

    Read off :func:`~.mechanics.scoring.initiative`, which is what decides who moves first in a
    showdown: your own positive bonuses, plus the negatives they are carrying, summed over the
    *distinct* values. So a second ``+1`` adds nothing and a ``+1`` beside a ``+2`` adds three.
    """
    player_side, bot_side = initiative(state.player, state.bot)
    mine, theirs = (player_side, bot_side) if is_player else (bot_side, player_side)
    return max(0, mine - theirs)


def early_bird(state: XiaolinState, surrendered: Card, *, is_player: bool = True) -> str:
    """Take the next Wu off the pile with no showdown, and give up a Wu of speed for it.

    You were simply faster: you reached the Wu first, so there was nothing to duel over. The Wu you
    surrender is *discarded* — no points, like any power spent — and it is the fastest thing you hold,
    so the lead that bought this shrinks by at least as much as it cost. Emptying the pile ends the
    run, exactly as it does when the last prize is drawn.

    ``is_player`` is which duelist flew it. The bot is held to the same rule, down to the surrender.
    """
    me = state.duelist(is_player)
    me.remove_card(surrendered)
    taken = state.card_deck.pop(0)
    me.hand.append(taken)
    state.spend_action(is_player)
    if not state.card_deck:
        state.has_ended = True
    return EARLY_BIRD_MESSAGE.format(taken=taken.name, given=surrendered.name)


def use_power_blocked(state: XiaolinState, actions_per_turn: int) -> str | None:
    """Why no power can be used right now, or ``None`` when one can."""
    if usable_powers(state, actions_per_turn):
        return None
    # A `use`-trigger Wu only counts while the turn's action is unspent, so a spent turn is the more
    # useful thing to say than "no Wu with a power".
    if has_acted(state, actions_per_turn) and any(
        trigger_of(card.power) == "use" for card in state.player.whole_hand
    ):
        return SPENT_MESSAGE
    return "No Wu with a usable power."


def coming_wu(state: XiaolinState, depth: int = 1) -> list[Card]:
    """The next ``depth`` Wu of the draw pile, in the order they will come.

    What the revealing Wu are *for*, and the screens need it before the Wu is spent: the Conch shows
    you the next card and then asks its question, so the answer is an informed one.
    """
    return state.card_deck[:depth]


def use_power(
    state: XiaolinState,
    card: Card,
    *,
    is_player: bool = True,
    priority: bool | None = None,
    target: Card | None = None,
    to_deck: bool = False,
    rng: Rng | None = None,
) -> PowerReport:
    """Fire ``card``'s power, then discard it for **no points**; return its :class:`PowerReport`
    (a toast line and a shorter log line).

    Distinct from :func:`deposit`, which banks the Wu for its points. Seven powers do something —
    Chronokinesis draws, Diaskopia and Teleskopia reveal, Oxyderkia buys the next showdown's
    initiative, Attraction pulls a Wu to you, Repulsion shoves one out of your opponent's hand, and
    Euthymia calls one back from the lost; the gag Wu fizzles.

    ``is_player`` is which duelist fired it — the bot spends a Wu by exactly these rules. The rest
    are the answers a power needs and the logic layer cannot ask for: ``priority`` is Oxyderkia's
    (take the next showdown's initiative, or refuse it), ``target`` is the Wu Attraction pulls or the
    one Repulsion shoves, ``to_deck`` is Repulsion's destination (shelve it into their deck for no
    points, instead of banking it for points), and ``rng`` is Repulsion's, because a Wu shoved into the
    temple might be the one whose worth is rolled — and a Wu shoved into a deck is shuffled in.
    """
    if trigger_of(card.power) != "use":  # a hand power-up is passive — nothing to trigger, kept
        return FIZZLE_MESSAGE

    spend = _Spend(state, card, is_player, priority, target, to_deck, rng)
    message = _fire(spend)
    state.spend_action(is_player)
    # Witchcraft (Wuya): the spent Wu returns to her hand instead of the discard — worn one further
    # by the sorcery. The wear rule is her leash: the return that brings it to the limit vaults it.
    if WITCHCRAFT_RETURNS and mechanic_of(spend.me.character.power) is Mechanic.WITCHCRAFT:
        card.uses += 1
        if not WITCHCRAFT_WEARS or card.uses < WEAR_LIMIT:
            return message  # restored: it never leaves her hand
        spend.me.remove_card(card)
        # A wear-vault, not a deposit: the sorcery used the Wu up, she did not choose to cash it.
        paid = bank_value(card, rng) if rng is not None else card.points
        spend.me.points = max(0, spend.me.points + paid)
        return message
    spend.me.remove_card(card)  # spent, no points
    state.used.append(card)  # into the shared used pile for a Refresh Wu to call back
    return message
