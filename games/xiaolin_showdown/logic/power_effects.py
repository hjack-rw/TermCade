"""Firing a ``use`` power: the effect handlers and the two-line report each one raises.

Split from :mod:`.actions`, which owns the temple verbs (deposit, draw, train...) and the public
:func:`~.actions.use_power` entry. This module is the machinery behind that entry: one handler per
mechanic, the :class:`_Spend` it runs against, and the ``REPORTS`` wording it fills.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from termcade.core.rng import Rng

from .mechanics.cards import index_of
from .mechanics.powers import SCOPE_DEPTH, Mechanic, mechanic_of
from .models import Card, Player
from .state import XiaolinState
from .turn import bank_value, shelve
from .wear import hand_over


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
    Mechanic.DRAW: PowerReport(
        "Chronokinesis stopped time — you drew {name}!",
        "{caster} drew {name}.",
    ),
    # Diaskopia and Teleskopia reveal to the CASTER, and the opponent never spends them (they are always
    # banked — see temple_ai), so their log only ever reads player-cast. Left first-person.
    Mechanic.READ_DECK: PowerReport(
        "Diaskopia saw through the wall — their Deck holds: {cards}",
        "Their Deck holds: {cards}",
    ),
    Mechanic.SCRY: PowerReport(
        "Teleskopia saw down the line — next will come: {cards}",
        "Next will come: {cards}",
    ),
    Mechanic.ENHANCED_VISION: PowerReport(
        "Oxyderkia saw them coming — you {answer} Initiative in the next Showdown.",
        "{caster} {answer} Initiative in the next Showdown.",
    ),
    Mechanic.FETCH: PowerReport(
        "Attraction pulled {name} out of your Deck and into your Hand.",
        "{name} came out of {caster_poss} Deck and into {caster_poss} Hand.",
    ),
    Mechanic.BOUNCE: PowerReport(
        "Repulsion shoved {name} out of their Hand — they deposited it for {paid} points.",
        "{name} was deposited out of {victim_poss} Hand for {paid} points.",
    ),
    Mechanic.LUCK: PowerReport(
        "Euthymia called {name} back from the lost — it is yours.",
        "{name} came back from the lost into {caster_poss} possession.",
    ),
    Mechanic.REFRESH: PowerReport(
        "{name} is refreshed — back in your hand, ready to spend again.",
        "{caster} called {name} back from the used pile into {caster_poss} hand.",
    ),
    Mechanic.PROGNOSIS: PowerReport(
        "The Conch read them — next Showdown they lead with {answer}, but the ground is yours.",
        "{caster} let {victim} lead the next Showdown, but kept the challenger's ground.",
    ),
    Mechanic.TRANSFER: PowerReport(
        "The Lantern shone on you both — every Wu in your hand is theirs, and theirs are yours.",
        "{caster} swapped the two hands entirely: {count} Wu crossed to {caster_poss} side.",
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

# Both duelists reached for the initiative the same turn (Conch and/or Glasses): neither answer stands.
# Swapped in by `_fire` for the second such power played — the coin toss decides who leads instead.
CONTESTED_INITIATIVE = PowerReport(
    "You both reached for the initiative — a coin toss will decide who leads.",
    "{caster} contested the initiative — the coin decides who leads the next Showdown.",
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


TAKEN, REFUSED = "took", "refused"


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
    drawn = state.card_deck.pop(0)
    spend.me.hand.append(drawn)
    if not state.card_deck:
        state.has_ended = True
    return {"name": drawn.name}


def _read_deck(spend: _Spend) -> _Fill | None:
    """Diaskopia: everything the opponent has shelved."""
    deck = spend.them.deck
    return {"cards": _names(deck)} if deck else None


def _scan_pile(spend: _Spend) -> _Fill | None:
    """Teleskopia: as far down the pile as the Wu can see."""
    coming = spend.state.card_deck[:SCOPE_DEPTH]
    return {"cards": _names(coming)} if coming else None


def _already_answered(state: XiaolinState) -> bool:
    """Has an initiative power (Conch or Glasses) already spoken for the coming showdown this turn?"""
    return state.forced_priority is not None or state.initiative_contested


def _contest_initiative(state: XiaolinState) -> None:
    """A second initiative power lands on an already-answered showdown: neither answer stands. Wipe the
    priority claims and flag the contest — the coin decides, since the two cannot be played at once."""
    state.initiative_contested = True
    state.forced_priority = None
    state.conch_tiebreak = None
    state.locked_challenge = None


def _listen(spend: _Spend) -> _Fill | None:
    """Oxyderkia: the next showdown's initiative, bought with an answer.

    ``priority`` is the *caster's* answer — do I want it? ``forced_priority`` is the duel's, and the
    duel asks a different question: does the **player** hold it? For the bot, the two are opposites.
    """
    if spend.priority is None:
        raise ValueError("Oxyderkia was spent without an answer — ask before you fire it")
    if _already_answered(spend.state):
        _contest_initiative(spend.state)
    else:
        spend.state.forced_priority = spend.priority if spend.is_player else not spend.priority
    return {"answer": TAKEN if spend.priority else REFUSED}


def _foresee(spend: _Spend) -> _Fill | None:
    """Prognosis (the new Mind Reader Conch): let the opponent lead, but read their every move.

    The opponent takes priority next showdown — they name the challenge — but the caster keeps the
    challenger's ground (wins the level battles). When the opponent is the bot, its challenge is
    PINNED now (from its current stats and hand) and revealed to the caster; a human opponent still
    names theirs live, so nothing is pinned there and only the ground changes hands.
    """
    from . import bot  # local: bot imports this module

    if _already_answered(spend.state):
        _contest_initiative(spend.state)
        return {"answer": "the coin"}  # ignored: `_fire` swaps in CONTESTED_INITIATIVE
    spend.state.forced_priority = not spend.is_player  # the opponent leads
    spend.state.conch_tiebreak = spend.is_player  # the caster keeps the ground despite not leading
    if spend.is_player:  # the opponent is the bot — its call is deterministic, so pin and reveal it
        stats = list(spend.them.character.stats)
        spend.state.locked_challenge = bot.choose_challenge(
            spend.them.character.stats, stats, spend.them.whole_hand,
            spend.me.character.stats, spend.rng or Rng(0),  # a tie-break stream; the caster supplies it
        )
        return {"answer": spend.state.locked_challenge.upper()}
    return {"answer": "their lead"}


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
    """Luck: the oldest Wu in the lost pile, back into the hand of whoever spent the Rooster.

    The **oldest**, and that is the whole of the rule. Letting its caster read the pile and pick would
    make it a tutor for the best Wu anyone ever failed to win; letting it roll would make it the second
    Wu in the game that gambles, and `GAMBLE_SPREAD` says there is exactly one. First lost, first back.
    """
    lost = spend.state.lost
    if not lost:
        return None
    revived = lost.pop(0)
    # A change of hands like any other (see wear.hand_over) — moot today, since only unclaimed
    # prizes reach the lost pile and nobody has worn those.
    spend.me.hand.append(hand_over(revived))
    return {"name": revived.name}


def _refresh(spend: _Spend) -> _Fill | None:
    """Refresh: the Wu most recently used by *either* duelist, back into the caster's hand.

    The used pile is shared and in order, so the newest spend comes back — yours or theirs, and if it
    was theirs you take it. It returns *healed*: its wear resets to zero, a fresh Wu in the caster's
    hand. Fizzles when nobody has used anything yet.
    """
    used = spend.state.used
    if not used:
        return None
    revived = used.pop()
    revived.uses = revived.uses_memory = 0  # healed — three showdowns' wear undone
    spend.me.hand.append(revived)
    return {"name": revived.name}


def _swap_souls(spend: _Spend) -> _Fill | None:
    """Transfer: the two duelists' hands change owners entirely.

    The plain hands only — an inalienable wudai is soul-bound and stays. The Lantern itself sits
    out the swap: it is mid-spend, and must be in its caster's hand when the spend removes it.
    Every crossing Wu goes through ``hand_over``, so wear resumes per wearer like any other change
    of hands.
    """
    if not spend.them.hand:
        return None  # nothing to swap into — a one-way gift is not a swap
    mine = [card for card in spend.me.hand if card is not spend.card]
    theirs = list(spend.them.hand)
    spend.me.hand[:] = [spend.card] + [hand_over(card) for card in theirs]
    spend.them.hand[:] = [hand_over(card) for card in mine]
    return {"count": len(theirs)}


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
    Mechanic.DRAW: _draw,
    Mechanic.READ_DECK: _read_deck,
    Mechanic.SCRY: _scan_pile,
    Mechanic.ENHANCED_VISION: _listen,
    Mechanic.FETCH: _pull,
    Mechanic.BOUNCE: _shove,
    Mechanic.LUCK: _recover,
    Mechanic.REFRESH: _refresh,
    Mechanic.PROGNOSIS: _foresee,
    Mechanic.TRANSFER: _swap_souls,
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
    # An initiative power that lands on an already-answered showdown contests it: neither stands, the
    # coin decides, and the wording says so instead of promising an answer the handler did not keep.
    if spend.state.initiative_contested and mechanic in (Mechanic.ENHANCED_VISION, Mechanic.PROGNOSIS):
        return _report(CONTESTED_INITIATIVE, is_player=spend.is_player, **fills)
    # Repulsion is the one power with two outcomes — the deck version has its own wording.
    template = REPULSION_TO_DECK if mechanic is Mechanic.BOUNCE and spend.to_deck else REPORTS[mechanic]
    return _report(template, is_player=spend.is_player, **fills)


def _names(cards: list[Card]) -> str:
    return ", ".join(card.name for card in cards)
