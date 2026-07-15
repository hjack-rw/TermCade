"""Pure temple actions between duels — no I/O: deposit, use-power, and draw.

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
from .turn import bank_value, max_hand_size, shelve

# A fired power says its piece TWICE. The toast names the power and sets the scene; the log line drops
# the name and states only the outcome, because the Game Log entry above it already read "You played
# Chronokinesis from the...". See docs/design/VOICE.md.
#
# All past tense: a report is raised AFTER the thing happened and re-read a turn later, so "you draw a
# Wu" would read as an instruction for a move the game already spent.


@dataclass(frozen=True)
class PowerReport:
    """What a fired power says — twice. `toast` names the power and sets the scene; `log` states only
    the outcome, because the Game Log entry above it already read "You played <power> from the <Wu>".
    A template (with `{...}` fields) fills both forms at once through `_report`."""

    toast: str
    log: str


# Every acting power's two lines, keyed by mechanic — the same shape as `RULES` and `_FIRE`, so a power
# is defined once, in one place. To tweak a power's wording, edit its row here and nothing else.
#
# The TOAST is player-only (only you see a toast for your own action), so it is written first-person.
# The LOG is read by BOTH sides — your own move, and the opponent's — so it takes pronoun inserts that
# flip by who cast it (see `_voice`): {caster} You/They, {caster_poss} your/their, {victim}/{victim_poss}
# the other duelist. The rest (`{name}`, `{cards}`, `{answer}`, `{paid}`) come from the handler.
REPORTS: dict[Mechanic, PowerReport] = {
    Mechanic.CHRONOKINESIS: PowerReport(
        "Chronokinesis stopped time — you drew a Wu!",
        "{caster} drew a Wu.",
    ),
    # Diaskopia and Teleskopia reveal to the CASTER, and the opponent never spends them (they are always
    # banked — see temple_ai), so their log only ever reads player-cast. Left first-person.
    Mechanic.DIASKOPIA: PowerReport(
        "Diaskopia saw through the wall — their Deck holds: {cards}",
        "Their Deck holds: {cards}",
    ),
    Mechanic.TELESKOPIA: PowerReport(
        "Teleskopia saw down the line — next will come: {cards}",
        "Next will come: {cards}",
    ),
    Mechanic.TELEPATHEIA: PowerReport(
        "Telepatheia listened in — you {answer} Initiative in the next Showdown.",
        "{caster} {answer} Initiative in the next Showdown.",
    ),
    Mechanic.ATTRACTION: PowerReport(
        "Attraction pulled {name} out of your Deck and into your Hand.",
        "{name} came out of {caster_poss} Deck and into {caster_poss} Hand.",
    ),
    Mechanic.REPULSION: PowerReport(
        "Repulsion shoved {name} out of their Hand — they deposited it for {paid} points.",
        "{name} was deposited out of {victim_poss} Hand for {paid} points.",
    ),
    Mechanic.EUTHYMIA: PowerReport(
        "Euthymia called {name} back from the lost — it is yours.",
        "{name} came back from the lost into {caster_poss} possession.",
    ),
}

# Repulsion's OTHER destination: shoved into their deck (no points), not banked. Picked by `_fire` when
# the caster chose the deck — it sits by the temple version above, so both wordings tweak together.
REPULSION_TO_DECK = PowerReport(
    "Repulsion shoved {name} out of their Hand — it is lost in their Deck.",
    "{name} was shoved out of {victim_poss} Hand into {victim_poss} Deck.",
)

# The fizzle is not keyed to an acting power: the gag Wu (use/0) hits it, so does any power with
# nothing to act on. No outcome to keep — the non-event IS the joke, so both lines are the same.
FIZZLE_MESSAGE = PowerReport(
    "Something should have happened...",
    "Something should have happened...",
)


def _voice(is_player: bool) -> dict[str, str]:
    """The pronoun inserts for a log line, flipped by who cast the power — so one line reads right from
    either seat. The toast has no such inserts (it is first-person, and player-only)."""
    return {
        "caster": "You" if is_player else "They",
        "caster_poss": "your" if is_player else "their",
        "victim": "they" if is_player else "you",
        "victim_poss": "their" if is_player else "your",
    }


def _report(template: PowerReport, *, is_player: bool = True, **kw: object) -> PowerReport:
    """Fill both lines of a template. The log takes pronoun inserts (`_voice`); the toast ignores the
    ones it does not use, so the same call fills both."""
    fills = {**_voice(is_player), **kw}
    return PowerReport(template.toast.format(**fills), template.log.format(**fills))


# Not a power: the Early Bird logs its own line, so it stays a plain one-form message.
EARLY_BIRD_MESSAGE = "You outran your opponent to the next Wu: {taken} is yours. You gave up your {given} for it."

TAKEN, REFUSED = "took", "refused"
SPENT_MESSAGE = "You have already acted this turn."


def has_acted(state: XiaolinState, actions_per_turn: int) -> bool:
    """Is the turn's action already spent? Banking, using a power and drawing all cost the same one.

    The single budget is the whole of the temple economy: a Wu spent is a Wu not replaced, and the
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
    if mechanic is Mechanic.DIASKOPIA:
        return bool(them.deck)
    if mechanic is Mechanic.TELESKOPIA:
        return bool(state.card_deck)
    if mechanic is Mechanic.ATTRACTION:
        return bool(me.deck)
    if mechanic is Mechanic.REPULSION:
        # The opponent is held to the rule that binds you: a deposit may never empty a hand.
        return len(them.hand) > 1
    if mechanic is Mechanic.EUTHYMIA:
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
    me = state.duelist(is_player)
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
    Chronokinesis draws, Diaskopia and Teleskopia reveal, Telepatheia buys the next showdown's
    initiative, Attraction pulls a Wu to you, Repulsion shoves one out of your opponent's hand, and
    Euthymia calls one back from the lost; the gag Wu fizzles.

    ``is_player`` is which duelist fired it — the bot spends a Wu by exactly these rules. The rest
    are the answers a power needs and the logic layer cannot ask for: ``priority`` is Telepatheia's
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
    to_deck: bool = False  # Repulsion: shove into their deck (no points), not into their temple
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


# A handler does the game work and returns the values that fill its `REPORTS` row — or ``None`` when it
# found nothing to act on, which fizzles. It carries no text: the wording all lives in `REPORTS`.
_Fill = dict[str, object]


def _draw(spend: _Spend) -> _Fill | None:
    """Chronokinesis: the top of the pile, into your hand. An empty pile ends the run."""
    state = spend.state
    if not state.card_deck:
        return None
    spend.me.hand.append(state.card_deck.pop(0))
    if not state.card_deck:
        state.has_ended = True
    return {}


def _read_deck(spend: _Spend) -> _Fill | None:
    """Diaskopia: everything the opponent has shelved."""
    deck = spend.them.deck
    return {"cards": _names(deck)} if deck else None


def _scan_pile(spend: _Spend) -> _Fill | None:
    """Teleskopia: as far down the pile as the Wu can see."""
    coming = coming_wu(spend.state, SCOPE_DEPTH)
    return {"cards": _names(coming)} if coming else None


def _listen(spend: _Spend) -> _Fill | None:
    """Telepatheia: the next showdown's initiative, bought with an answer.

    ``priority`` is the *caster's* answer — do I want it? ``forced_priority`` is the duel's, and the
    duel asks a different question: does the **player** hold it? For the bot, the two are opposites.
    """
    if spend.priority is None:
        raise ValueError("Telepatheia was spent without an answer — ask before you fire it")
    spend.state.forced_priority = spend.priority if spend.is_player else not spend.priority
    return {"answer": TAKEN if spend.priority else REFUSED}


def _pull(spend: _Spend) -> _Fill | None:
    """Attraction: a Wu of your choosing, out of your own deck.

    The hand does not grow: the Glove leaves it as the Wu it drew arrives.
    """
    deck = spend.me.deck
    if not deck:
        return None
    pulled = spend.wu()
    deck.pop(index_of(deck, pulled))
    spend.me.hand.append(pulled)
    return {"name": pulled.name}


def _recover(spend: _Spend) -> _Fill | None:
    """Euthymia: the oldest Wu in the lost pile, back into the hand of whoever spent the Rooster.

    The **oldest**, and that is the whole of the rule. Letting its caster read the pile and pick would
    make it a tutor for the best Wu anyone ever failed to win; letting it roll would make it the second
    Wu in the game that gambles, and `GAMBLE_SPREAD` says there is exactly one. First lost, first back.
    """
    lost = spend.state.lost
    if not lost:
        return None
    revived = lost.pop(0)
    spend.me.hand.append(revived)
    return {"name": revived.name}


def _shove(spend: _Spend) -> _Fill | None:
    """Repulsion: a Wu out of the opponent's hand — the caster picks where it lands.

    Two destinations, each with a cost. **Vault** (``to_deck=False``): they *bank the points*, the Wu
    is gone for good — you pay them to remove it. **Deck** (``to_deck=True``): no points to them, but
    it is shuffled into their deck and they will draw it back — a delay, not a removal. The clamp on the
    deposit is the one every deposit lives under: a bad roll costs banked points, never the run.
    """
    them = spend.them
    if not them.hand:
        return None
    if spend.rng is None:
        raise ValueError("Repulsion moves a Wu that may need a roll or a shuffle — pass the rng")
    shoved = spend.wu()
    them.hand.pop(index_of(them.hand, shoved))
    if spend.to_deck:
        shelve(them, shoved, rng=spend.rng)
        return {"name": shoved.name}
    paid = bank_value(shoved, spend.rng)
    them.points = max(0, them.points + paid)
    return {"name": shoved.name, "paid": paid}


# What each `use` power does. A mechanic that is absent, or whose handler finds nothing to act on,
# fizzles — the gag Wu by design, and the rest when the pile or a hand has run dry.
_FIRE: dict[Mechanic, Callable[[_Spend], _Fill | None]] = {
    Mechanic.CHRONOKINESIS: _draw,
    Mechanic.DIASKOPIA: _read_deck,
    Mechanic.TELESKOPIA: _scan_pile,
    Mechanic.TELEPATHEIA: _listen,
    Mechanic.ATTRACTION: _pull,
    Mechanic.REPULSION: _shove,
    Mechanic.EUTHYMIA: _recover,
}


def _fire(spend: _Spend) -> PowerReport:
    """What a ``use`` power does, before the Wu is spent on it.

    Every handler checks what it acts on, rather than trusting :func:`usable_powers` to have gated
    it: a power that reveals an empty pile would read as a bug rather than as the fizzle it is.
    """
    mechanic = mechanic_of(spend.card.power)
    handler = _FIRE.get(mechanic)
    if handler is None:
        return FIZZLE_MESSAGE
    fills = handler(spend)
    if fills is None:
        return FIZZLE_MESSAGE
    # Repulsion is the one power with two outcomes — the deck version has its own wording.
    template = REPULSION_TO_DECK if mechanic is Mechanic.REPULSION and spend.to_deck else REPORTS[mechanic]
    return _report(template, is_player=spend.is_player, **fills)


def _names(cards: list[Card]) -> str:
    return ", ".join(card.name for card in cards)
