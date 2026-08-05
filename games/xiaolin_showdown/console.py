"""The console's commands — what a duelist may do to a run that is not playing it.

These exist to make a new Wu testable without waiting for the draw pile to deal it: put it in a hand
or stack the pile, then play it. Every command acts on the **live run**, so the Wu is fielded, boosted,
cursed and scored by exactly the rules a dealt one would be.

They are found by typing them and no other way (`~` opens the console). Nothing in the game links here.
"""

from __future__ import annotations

from collections.abc import Sequence
from copy import deepcopy
from dataclasses import replace
from typing import cast

from termcade.app.game import GameContext
from termcade.ui.screens.console import Command

from .logic.schema.catalog import load_catalog
from .logic.flow.turn import shelve
from .logic.characters.jong import PART_TYPES
from .logic.config.ladder import LADDER, LADDER_OPTION
from .logic.mechanics.powers import Mechanic, mechanic_of
from .logic.schema.models import Card
from .logic.schema.state import XiaolinState


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


def fill(ctx: GameContext, args: Sequence[str]) -> str:
    """Fill a training bar outright, to test the payout without grinding ten losses.

    Yours waits for the stat pick (the temple offers it, or Train opens it); the opponent's is
    cashed by their own turn, exactly as a real full bar would be.
    """
    from .logic.config.settings import XiaolinSettings
    from .logic.flow.training import add_progress, can_train

    state = _state(ctx)
    settings = XiaolinSettings.from_settings(ctx.settings.current)
    who = args[0] if args else "me"
    if who not in (*_ME, *_THEM):
        raise ValueError("fill me | fill them")
    is_player = who not in _THEM
    player = state.player if is_player else state.bot
    if player.just_trained:
        return "the payout was just taken — that bar resets next turn"
    if not can_train(player, settings):
        return "nothing left to train — every stat is at the cap"
    train_length = settings.train_length_player if is_player else settings.train_length_bot
    add_progress(player, settings, train_length, is_player=is_player)
    return "their bar is full" if who in _THEM else "your bar is full — Train (5) picks the stat"


def jong(ctx: GameContext, args: Sequence[str]) -> str:
    """Deal a full Mala Mala Jong set — one Wu of each slot plus the Heart — so Construct is one temple
    turn away. The assembly is exodia-rare by design, so the console is the only way to reach it on
    demand. ``jong them`` stacks the opponent's hand instead; the Construct itself still runs by the
    real rules (temple power, hand purge, the locked form)."""
    state = _state(ctx)
    who = args[0] if args and args[0] in (*_ME, *_THEM) else "me"
    player = state.bot if who in _THEM else state.player
    catalog = load_catalog()
    picks: dict[str, Card] = {}
    for card in catalog.cards:
        if card.type in PART_TYPES and card.type not in picks:
            picks[card.type] = card
    heart = next(card for card in catalog.cards if mechanic_of(card.power) is Mechanic.ANIMATE)
    dealt = [deepcopy(picks[slot]) for slot in PART_TYPES] + [deepcopy(heart)]
    player.hand.extend(dealt)
    whose = "them" if who in _THEM else "you"
    return f"dealt {whose} a Jong set: {_named(dealt)} — Construct at the temple"


def clear(ctx: GameContext, args: Sequence[str]) -> str:
    """Empty a hand, so what you deal into it next is the only thing in it."""
    state = _state(ctx)
    who = args[0] if args else "me"
    if who in _ME:
        state.player.hand.clear()
        return "your hand is empty"
    if who in _THEM:
        state.bot.hand.clear()
        return "their hand is empty"
    raise ValueError("clear me | clear them")


def refresh(ctx: GameContext, args: Sequence[str]) -> str:
    """Give the turn's action back, so several powers can be spent in one temple turn instead of one
    per turn. The powers still fire by the real rules; only the turn budget is reset. `refresh them`
    does the same for the opponent.
    """
    state = _state(ctx)
    who = args[0] if args else "me"
    if who in _ME:
        state.actions_taken = 0
        return "your action is yours again"
    if who in _THEM:
        state.bot_actions_taken = 0
        return "their action is theirs again"
    if who in ("both", "all"):
        state.actions_taken = state.bot_actions_taken = 0
        return "both actions are back"
    raise ValueError("refresh me | refresh them | refresh both")


def unlock(ctx: GameContext, args: Sequence[str]) -> str:
    """Clear the whole boss ladder at once — every boss selectable from the settings screen,
    without grinding Hard and three boss wins to reach the one you actually want to test.

    Written into the settings file (like a real ladder win), so it survives a restart same as
    genuine progress would.
    """
    settings = ctx.settings.current
    updated = replace(settings, options={**settings.options, LADDER_OPTION: len(LADDER)})
    ctx.settings.save(updated)
    return f"boss ladder fully unlocked: {len(LADDER)}/{len(LADDER)} bosses"


COMMANDS: dict[str, Command] = {
    "find": Command(find, "find <word> — list the Wu whose name holds it, with their ids"),
    "give": Command(give, "give <id>... — deal a Wu straight into your hand"),
    "givebot": Command(givebot, "givebot <id>... — deal one to the opponent"),
    "pile": Command(pile, "pile <id>... — stack the top of the draw pile"),
    "deck": Command(deck, "deck [me|them] <id>... — shelve Wu onto a personal deck"),
    "lose": Command(lose, "lose <id>... — put a Wu on the lost pile"),
    "points": Command(points, "points <yours> [theirs] — set the banked score"),
    "fill": Command(fill, "fill [me|them] — fill a training bar, to test the payout"),
    "jong": Command(jong, "jong [me|them] — deal a full Mala Mala Jong set (5 slots + the Heart)"),
    "clear": Command(clear, "clear me | clear them — empty a hand"),
    "refresh": Command(
        refresh, "refresh [me|them|both] — give the turn's action back, to spend another power"
    ),
    "unlock": Command(unlock, "unlock — clear the whole boss ladder, every boss selectable"),
}
