"""The console's commands — what a duelist may do to a run that is not playing it.

**These exist to make a new Wu testable.** A card is worth whatever it does in a real showdown, and a
40-card pile deals it to you when it feels like it — which is not a test, it is a wait. So: put the Wu
in a hand, stack the pile with the one you want fought over, and go and play the thing you are judging.

Every command acts on the **live run**, so the Wu you conjure is fielded, boosted, cursed and scored by
exactly the rules a dealt one would be. That is the whole point: a sandbox that plays by its own rules
tests nothing.

They are found by typing them and no other way (`~` opens the console). Nothing in the game links here.
"""

from __future__ import annotations

from collections.abc import Sequence
from copy import deepcopy
from typing import cast

from termcade.app.game import GameContext
from termcade.ui.screens.console import Command

from .logic.catalog import load_catalog
from .logic.turn import shelve
from .logic.models import Card
from .logic.state import XiaolinState


def _state(ctx: GameContext) -> XiaolinState:
    state = cast(XiaolinState | None, ctx.state)
    if state is None:
        raise ValueError("no run in progress — start a game first")
    return state


def _cards(words: Sequence[str]) -> list[Card]:
    """The Wu named by id. A fresh copy each time: the duel mutates what it is handed.

    Ids, not names — a name has spaces in it and a console splits on spaces, and `find` is one line
    away for anybody who does not know the number.
    """
    if not words:
        raise ValueError("name at least one Wu, by id — `find <word>` if you do not know it")
    catalog = load_catalog()
    return [deepcopy(catalog.card(int(word))) for word in words]


def _named(cards: Sequence[Card]) -> str:
    return ", ".join(card.name for card in cards)


def find(ctx: GameContext, args: Sequence[str]) -> str:
    """Which Wu is which — the command every other command needs first."""
    wanted = " ".join(args).lower()
    catalog = load_catalog()
    hits = [c for c in catalog.cards if wanted in c.name.lower()] if wanted else catalog.cards
    if not hits:
        return f"no Wu is called {wanted!r}"
    return "\n".join(
        f"{card.id:>3}  {card.name:<22} {str(list(card.stats.values())):<16} "
        f"{card.element:<6} {card.points}pt  {card.power.name}"
        for card in hits[:60]
    )


def give(ctx: GameContext, args: Sequence[str]) -> str:
    """Put a Wu straight into your hand — the one command this whole console is for."""
    state = _state(ctx)
    cards = _cards(args)
    state.player.hand.extend(cards)
    return f"dealt you {_named(cards)}"


def givebot(ctx: GameContext, args: Sequence[str]) -> str:
    """The same, to the opponent — a card is only tested once it has been *played against* you."""
    state = _state(ctx)
    cards = _cards(args)
    state.bot.hand.extend(cards)
    return f"dealt them {_named(cards)}"


def pile(ctx: GameContext, args: Sequence[str]) -> str:
    """Stack the top of the draw pile, so the next showdown is fought over the Wu you want to see."""
    state = _state(ctx)
    cards = _cards(args)
    state.card_deck[:0] = cards
    return f"{_named(cards)} on top of the pile"


_ME = ("me", "player", "mine")
_THEM = ("them", "bot", "theirs")


def deck(ctx: GameContext, args: Sequence[str]) -> str:
    """Shelve Wu onto a personal deck — what the deck powers read and pull from (Diaskopia, the Glove).

    ``deck them <id>...`` fills the opponent's shelf; a leading ``me``/``them`` picks whose, and with
    none it is yours. Shuffled in, exactly as the game shelves — the deck is an obstacle, not an order.
    """
    state = _state(ctx)
    who, rest = (args[0], args[1:]) if args and args[0] in (*_ME, *_THEM) else ("me", args)
    player = state.bot if who in _THEM else state.player
    cards = _cards(rest)
    for card in cards:
        shelve(player, card, rng=ctx.rng)
    return f"shelved onto {'their' if who in _THEM else 'your'} deck: {_named(cards)}"


def lose(ctx: GameContext, args: Sequence[str]) -> str:
    """Put a Wu on the lost pile, where nobody won it — the Rooster Booster's whole reason to exist."""
    state = _state(ctx)
    cards = _cards(args)
    state.lost.extend(cards)
    return f"lost: {_named(cards)}"


def points(ctx: GameContext, args: Sequence[str]) -> str:
    """Set the banked points, to play the end of a run without playing the whole of it."""
    state = _state(ctx)
    if not args:
        raise ValueError("points <yours> [theirs]")
    state.player.points = max(0, int(args[0]))
    if len(args) > 1:
        state.bot.points = max(0, int(args[1]))
    return f"points: you {state.player.points}, them {state.bot.points}"


def clear(ctx: GameContext, args: Sequence[str]) -> str:
    """Empty a hand, so what you deal into it next is the only thing in it."""
    state = _state(ctx)
    who = args[0] if args else "me"
    if who in ("me", "player", "mine"):
        state.player.hand.clear()
        return "your hand is empty"
    if who in ("them", "bot", "theirs"):
        state.bot.hand.clear()
        return "their hand is empty"
    raise ValueError("clear me | clear them")


def refresh(ctx: GameContext, args: Sequence[str]) -> str:
    """Give the turn's action back, so several powers can be spent in one temple turn.

    The one-action economy is the whole of the temple: a Wu spent is a Wu not banked, and that is what
    makes a hand a resource rather than a thing that refills itself. It is also what makes *testing* a
    power slow — two powers cost two turns, with a showdown in between whether you wanted one or not.

    So this hands the action back and does nothing else. The powers still fire by the real rules; you
    simply get to fire more than one before the showdown. `refresh them` does the same for the opponent,
    for a card that only shows what it is when it is used against you.

    (This replaced a `debug` command that printed the board. The console floats *over* the board — it
    was reading out what was already on screen behind it.)
    """
    state = _state(ctx)
    who = args[0] if args else "me"
    if who in ("me", "player", "mine"):
        state.actions_taken = 0
        return "your action is yours again"
    if who in ("them", "bot", "theirs"):
        state.bot_actions_taken = 0
        return "their action is theirs again"
    if who in ("both", "all"):
        state.actions_taken = state.bot_actions_taken = 0
        return "both actions are back"
    raise ValueError("refresh me | refresh them | refresh both")


COMMANDS: dict[str, Command] = {
    "find": Command(find, "find <word> — list the Wu whose name holds it, with their ids"),
    "give": Command(give, "give <id>... — deal a Wu straight into your hand"),
    "givebot": Command(givebot, "givebot <id>... — deal one to the opponent"),
    "pile": Command(pile, "pile <id>... — stack the top of the draw pile"),
    "deck": Command(deck, "deck [me|them] <id>... — shelve Wu onto a personal deck"),
    "lose": Command(lose, "lose <id>... — put a Wu on the lost pile"),
    "points": Command(points, "points <yours> [theirs] — set the banked score"),
    "clear": Command(clear, "clear me | clear them — empty a hand"),
    "refresh": Command(
        refresh, "refresh [me|them|both] — give the turn's action back, to spend another power"
    ),
}
