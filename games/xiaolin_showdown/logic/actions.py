"""Pure vault actions between duels — no I/O: deposit, use-power, and draw.

Draw pulls from the player's *personal* deck, which fills when they shelve surplus cards over the
hand limit. Together, shelving a card and drawing a fresh one is how the player cycles their hand.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from termcade.core.rng import Rng

from .mechanics.cards import index_of
from .mechanics.scoring import initiative
from .mechanics.powers import SCOPE_DEPTH, Mechanic, mechanic_of, trigger_of
from .models import Card, Player
from .settings import XiaolinSettings
from .state import XiaolinState
from .turn import bank_value, max_hand_size

# The gag Wu Ohwah Tegu Saim (use/0) has a "? ? ?" power that does nothing when used.
FIZZLE_MESSAGE = "You feel like something should have happened..."
DRAW_MESSAGE = "Chronokinesis warps time — you draw a Wu!"
DECK_MESSAGE = "Diaskopia sees through the vault — their deck holds: {cards}"
PILE_MESSAGE = "Teleskopia reaches down the pile — next come: {cards}"
CONCH_MESSAGE = "Telepatheia listens — you {answer} Initiative in the next Showdown."
TAKEN, REFUSED = "take", "refuse"
GLOVE_MESSAGE = "Attraction pulls {name} out of your deck and into your hand."
RUBY_MESSAGE = "Repulsion shoves {name} out of their hand — they bank it for {paid} points."
ROOSTER_MESSAGE = "Anabiosis calls {name} back from the lost — it is yours."
EARLY_BIRD_MESSAGE = "You outrun your opponent to the next Wu: {taken} is yours. You gave up your {given} for it."


SPENT_MESSAGE = "You have already acted this turn."


def has_acted(state: XiaolinState, actions_per_turn: int) -> bool:
    """Is the turn's action already spent? Banking, using a power and drawing all cost the same one.

    The single budget is the whole of the vault economy: a Wu spent is a Wu not replaced, and the
    Wu whose power is worth more than its points is a Wu you must choose to keep.
    """
    return state.actions_taken >= actions_per_turn


def deposit_blocked(state: XiaolinState, actions_per_turn: int) -> str | None:
    """Why a deposit is disallowed right now, or ``None`` when it is allowed.

    The ``can_*`` predicates are defined as "no reason", so a greyed action and the explanation for
    it can never disagree.
    """
    if has_acted(state, actions_per_turn):
        return SPENT_MESSAGE
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
    return paid


def draw_blocked(state: XiaolinState, settings: XiaolinSettings) -> str | None:
    """Why a draw is disallowed right now, or ``None`` when it is allowed."""
    if has_acted(state, settings.actions_per_turn):
        return SPENT_MESSAGE
    if not state.player.deck:
        return "Your personal deck is empty."
    if len(state.player.whole_hand) >= max_hand_size(state.player, settings.max_hand_size):
        return "Your hand is full."
    return None


def can_draw(state: XiaolinState, settings: XiaolinSettings) -> bool:
    """The player may pull one Wu from their personal deck — if the deck holds one, this turn's
    action is unspent, and the hand has room under the size limit."""
    return draw_blocked(state, settings) is None


def draw(state: XiaolinState) -> Card:
    """Pull the top Wu of the player's personal deck into their hand; costs the turn's action."""
    card = state.player.deck.pop(0)
    state.player.hand.append(card)
    state.actions_taken += 1
    return card


def usable_powers(state: XiaolinState, actions_per_turn: int, *, is_player: bool = True) -> list[Card]:
    """Wu whose power this duelist can actively use now: a hand power-up (``hand``/+1), or a
    ``use``-trigger Wu while the turn's action is unspent — and only if it has something to act on."""
    spent = state.actions_taken if is_player else state.bot_actions_taken
    unspent = spent < actions_per_turn
    mine = state.player if is_player else state.bot
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
    me = state.player if is_player else state.bot
    them = state.bot if is_player else state.player
    mechanic = mechanic_of(card.power)
    if mechanic is Mechanic.DIASKOPIA:
        return bool(them.deck)
    if mechanic is Mechanic.TELESKOPIA:
        return bool(state.card_deck)
    if mechanic is Mechanic.ATTRACTION:
        return bool(me.deck)
    if mechanic is Mechanic.REPULSION:
        # The opponent is held to the rule that binds you: a deposit may never empty a hand.
        return len(them.hand) > 1
    if mechanic is Mechanic.ANABIOSIS:
        return bool(state.lost)  # nothing has been lost yet — there is nobody to call back
    return True


def early_bird_options(state: XiaolinState, *, is_player: bool = True) -> list[Card]:
    """The Wu you may surrender to the Early Bird: your *highest* initiative, by magnitude.

    Magnitude, not sign: a ``-2`` is as much a Wu of speed as a ``+2``. One drags them, one lifts you,
    and both open the gap by two — so both are the price, and neither is a cheaper one.

    A choice, not a pick: several Wu can tie at the top, and which one you let go of is yours to say.
    That it must be a *highest* one is what keeps the rule honest — outrunning them costs you the very
    thing you outran them with, so the Early Bird cannot be flown twice on the same wings.
    """
    me = state.player if is_player else state.bot
    speed = [card for card in me.hand if card.power.initiative_bonus]
    if not speed:
        return []
    highest = max(abs(card.power.initiative_bonus) for card in speed)
    return [card for card in speed if abs(card.power.initiative_bonus) == highest]


def early_bird_blocked(state: XiaolinState, settings: XiaolinSettings) -> str | None:
    """Why the Early Bird cannot be flown right now, or ``None`` when it can."""
    if has_acted(state, settings.actions_per_turn):
        return SPENT_MESSAGE
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
    me = state.player if is_player else state.bot
    me.remove_card(surrendered)
    taken = state.card_deck.pop(0)
    me.hand.append(taken)
    if is_player:
        state.actions_taken += 1
    else:
        state.bot_actions_taken += 1
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
    rng: Rng | None = None,
) -> str:
    """Fire ``card``'s power, then discard it for **no points**; return a line describing what
    happened.

    Distinct from :func:`deposit`, which banks the Wu for its points. Seven powers do something —
    Chronokinesis draws, Diaskopia and Teleskopia reveal, Telepatheia buys the next showdown's
    initiative, Attraction pulls a Wu to you, Repulsion shoves one out of your opponent's hand, and
    Anabiosis calls one back from the lost; the gag Wu fizzles.

    ``is_player`` is which duelist fired it — the bot spends a Wu by exactly these rules. The rest
    are the answers a power needs and the logic layer cannot ask for: ``priority`` is Telepatheia's
    (take the next showdown's initiative, or refuse it), ``target`` is the Wu Attraction pulls or the
    one Repulsion shoves, and ``rng`` is Repulsion's, because a Wu shoved into the vault might be the
    one whose worth is rolled.
    """
    if trigger_of(card.power) != "use":  # a hand power-up is passive — nothing to trigger, kept
        return FIZZLE_MESSAGE

    spend = _Spend(state, card, is_player, priority, target, rng)
    message = _fire(spend)
    if is_player:
        state.actions_taken += 1
    else:
        state.bot_actions_taken += 1
    spend.me.remove_card(card)  # discarded, no points
    return message


@dataclass(frozen=True)
class _Spend:
    """One firing of a ``use`` power: the board, the Wu, and the answers its power asked for.

    ``is_player`` is which side of the table fired it. Every rule below is written from the caster's
    seat — *my* deck, *their* hand — so the bot spends a Wu by exactly the rules the player does.
    """

    state: XiaolinState
    card: Card
    is_player: bool = True
    priority: bool | None = None
    target: Card | None = None
    rng: Rng | None = None

    @property
    def me(self) -> Player:
        return self.state.player if self.is_player else self.state.bot

    @property
    def them(self) -> Player:
        return self.state.bot if self.is_player else self.state.player

    def wu(self) -> Card:
        """The Wu this power was aimed at. Fired at nothing, it would silently do nothing."""
        if self.target is None:
            raise ValueError(f"{self.card.name!r} was spent without naming a Wu — it does nothing")
        return self.target


def _draw(spend: _Spend) -> str | None:
    """Chronokinesis: the top of the pile, into your hand. An empty pile ends the run."""
    state = spend.state
    if not state.card_deck:
        return None
    spend.me.hand.append(state.card_deck.pop(0))
    if not state.card_deck:
        state.has_ended = True
    return DRAW_MESSAGE


def _read_deck(spend: _Spend) -> str | None:
    """Diaskopia: everything the opponent has shelved."""
    deck = spend.them.deck
    return DECK_MESSAGE.format(cards=_names(deck)) if deck else None


def _scan_pile(spend: _Spend) -> str | None:
    """Teleskopia: as far down the pile as the Wu can see."""
    coming = coming_wu(spend.state, SCOPE_DEPTH)
    return PILE_MESSAGE.format(cards=_names(coming)) if coming else None


def _listen(spend: _Spend) -> str | None:
    """Telepatheia: the next showdown's initiative, bought with an answer.

    ``priority`` is the *caster's* answer — do I want it? ``forced_priority`` is the duel's, and the
    duel asks a different question: does the **player** hold it? For the bot, the two are opposites.
    """
    if spend.priority is None:
        raise ValueError("Telepatheia was spent without an answer — ask before you fire it")
    spend.state.forced_priority = spend.priority if spend.is_player else not spend.priority
    return CONCH_MESSAGE.format(answer=TAKEN if spend.priority else REFUSED)


def _pull(spend: _Spend) -> str | None:
    """Attraction: a Wu of your choosing, out of your own deck.

    The hand does not grow: the Glove leaves it as the Wu it drew arrives.
    """
    deck = spend.me.deck
    if not deck:
        return None
    pulled = spend.wu()
    deck.pop(index_of(deck, pulled))
    spend.me.hand.append(pulled)
    return GLOVE_MESSAGE.format(name=pulled.name)


def _recover(spend: _Spend) -> str | None:
    """Anabiosis: the oldest Wu in the lost pile, back into the hand of whoever spent the Rooster.

    The **oldest**, and that is the whole of the rule. Letting its caster read the pile and pick would
    make it a tutor for the best Wu anyone ever failed to win; letting it roll would make it the second
    Wu in the game that gambles, and `GAMBLE_SPREAD` says there is exactly one. First lost, first back.
    """
    lost = spend.state.lost
    if not lost:
        return None
    revived = lost.pop(0)
    spend.me.hand.append(revived)
    return ROOSTER_MESSAGE.format(name=revived.name)


def _shove(spend: _Spend) -> str | None:
    """Repulsion: a Wu out of the opponent's hand, into the opponent's vault.

    Their points, not yours — the Wu is *pushed away*, not taken. The clamp is the one every deposit
    lives under: a bad roll costs banked points, never the run.
    """
    them = spend.them
    if not them.hand:
        return None
    if spend.rng is None:
        raise ValueError("Repulsion banks a Wu, and a banked Wu may need a roll — pass the rng")
    shoved = spend.wu()
    them.hand.pop(index_of(them.hand, shoved))
    paid = bank_value(shoved, spend.rng)
    them.points = max(0, them.points + paid)
    return RUBY_MESSAGE.format(name=shoved.name, paid=paid)


# What each `use` power does. A mechanic that is absent, or whose handler finds nothing to act on,
# fizzles — the gag Wu by design, and the rest when the pile or a hand has run dry.
_FIRE: dict[Mechanic, Callable[[_Spend], str | None]] = {
    Mechanic.CHRONOKINESIS: _draw,
    Mechanic.DIASKOPIA: _read_deck,
    Mechanic.TELESKOPIA: _scan_pile,
    Mechanic.TELEPATHEIA: _listen,
    Mechanic.ATTRACTION: _pull,
    Mechanic.REPULSION: _shove,
    Mechanic.ANABIOSIS: _recover,
}


def _fire(spend: _Spend) -> str:
    """What a ``use`` power does, before the Wu is spent on it.

    Every handler checks what it acts on, rather than trusting :func:`usable_powers` to have gated
    it: a power that reveals an empty pile would read as a bug rather than as the fizzle it is.
    """
    handler = _FIRE.get(mechanic_of(spend.card.power))
    if handler is None:
        return FIZZLE_MESSAGE
    return handler(spend) or FIZZLE_MESSAGE


def _names(cards: list[Card]) -> str:
    return ", ".join(card.name for card in cards)
