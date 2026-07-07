"""In-duel power resolution (``resolve_played_power``) — how a played card fills the scoring queues.

Pure and TTY-free: a card is played into a :class:`DuelState`'s queues and the resulting queue
mutations are asserted directly. Covers the four core behaviours — plain card,
Moby Morpher, boost amplification, and the negative-card curse.
"""

from __future__ import annotations

from termcade.core.rng import Rng

from xiaolin_showdown.logic.catalog import load_catalog
from xiaolin_showdown.logic.duel import Duel, DuelChoices, DuelState
from xiaolin_showdown.logic.elements import ELEMENTS
from xiaolin_showdown.logic.models import Card, Power
from xiaolin_showdown.logic.powers import resolve_played_power
from xiaolin_showdown.logic.settings import XiaolinSettings
from xiaolin_showdown.logic.setup import new_game
from xiaolin_showdown.logic.turn import refill_hands

_STATS = ("force", "agility", "intellect")


def _card(force, agility, intellect, *, element="water", trigger="hand", effect=0) -> Card:
    stats = {"force": force, "agility": agility, "intellect": intellect}
    return Card(1, "Wu", stats, Power(0, "", trigger, effect, ""), element, "item", 0)


def test_a_plain_card_enters_the_caster_queue_as_an_inert_stand_in():
    duel = DuelState(background="water")
    card = _card(3, 1, 0, element="water")

    resolve_played_power(duel, card, is_player=True, element="water")

    assert len(duel.player_queue) == 1
    assert not duel.bot_queue
    stand_in = duel.player_queue[0]
    assert stand_in.stats == {"force": 3, "agility": 1, "intellect": 0}
    assert stand_in.stats is not card.stats  # a private copy, safe to mutate in the duel
    assert stand_in.power.effect == 0  # neutral power — never re-triggers, never seen as a booster


def test_a_morpher_sets_every_stat_to_one_and_takes_the_chosen_element():
    duel = DuelState(background="fire")
    morpher = _card(None, None, None, element="metal", trigger="play", effect=1)

    resolve_played_power(duel, morpher, is_player=True, element="earth")

    stand_in = duel.player_queue[0]
    assert stand_in.stats == {"force": 1, "agility": 1, "intellect": 1}
    assert stand_in.element == "earth"


def test_a_bot_morpher_falls_back_to_the_background_element():
    duel = DuelState(background="fire")
    morpher = _card(None, None, None, element="metal", trigger="play", effect=1)

    resolve_played_power(duel, morpher, is_player=False, element="fire")

    assert duel.bot_queue[0].element == "fire"


def test_a_negative_card_curses_the_opponent_and_is_spent_on_your_side():
    duel = DuelState(background="water")
    curse = _card(-2, 0, 0, element="water")

    resolve_played_power(duel, curse, is_player=True, element="water")

    # your own copy contributes nothing...
    assert duel.player_queue[0].stats == {"force": 0, "agility": 0, "intellect": 0}
    # ...while a mirror lands on the opponent, stripped of its element so it earns no bonus.
    mirror = duel.bot_queue[0]
    assert mirror.stats == {"force": -2, "agility": 0, "intellect": 0}
    assert mirror.element == ""


def test_a_boost_lends_no_stats_of_its_own():
    duel = DuelState(background="water")
    boost = _card(9, 9, 9, element="water", trigger="boost", effect=1)

    resolve_played_power(duel, boost, is_player=True, element="water")

    assert duel.player_queue[0].stats == {"force": 0, "agility": 0, "intellect": 0}


def test_a_queued_booster_amplifies_the_next_positive_card():
    duel = DuelState(background="water")
    booster = _card(0, 0, 0, element="water", trigger="boost", effect=1)
    duel.player_queue.append(booster)  # played in stage 4, keeps its real power at the head

    resolve_played_power(duel, _card(4, 0, 2, element="water"), is_player=True, element="water")

    # +1 on each stat the played card contributes, 0 where it did not.
    assert booster.stats == {"force": 1, "agility": 0, "intellect": 1}


def test_a_queued_booster_flips_to_the_opponent_on_a_negative_card():
    duel = DuelState(background="water")
    booster = _card(0, 0, 0, element="water", trigger="boost", effect=1)
    duel.player_queue.append(booster)

    resolve_played_power(duel, _card(-3, -1, 0, element="water"), is_player=True, element="water")

    assert booster.stats == {"force": 0, "agility": 0, "intellect": 0}  # spent on your side
    opponent_booster = duel.bot_queue[-1]
    assert opponent_booster.stats == {"force": -1, "agility": -1, "intellect": 0}
    assert opponent_booster.element == ""


# --- the stage machine (scripted, headless) ----------------------------------------------
# The stage machine awaits its choices, so the scripted "player" supplies async callbacks that
# always take the first legal option and never boost — enough to drive a full showdown.
async def _first(options: list[str]) -> str:
    return options[0]


async def _first_card(playable: list[Card]) -> Card:
    return playable[0]


async def _no_boost(_options: list[Card]) -> Card | None:
    return None


async def _water(_background: str) -> str:
    return "water"


def _auto_choices() -> DuelChoices:
    return DuelChoices(challenge=_first, background=_first, boost=_no_boost, card=_first_card, element=_water)


async def test_a_scripted_showdown_walks_all_seven_stages():
    cat = load_catalog()
    rng = Rng(1)
    state = new_game(cat, rng, cat.character(1))  # Omi
    duel = Duel(state, rng, _auto_choices())

    assert await duel.advance() == 1  # Initiative — priority decided (a tie defers to the coin toss)

    deck_before = len(state.card_deck)
    assert await duel.advance() == 2  # Commitment — prize drawn, priority resolved to a concrete side
    assert duel.duel.stakes is not None
    assert len(state.card_deck) == deck_before - 1
    assert isinstance(duel.duel.player_priority, bool)

    assert await duel.advance() == 3  # Challenge / Background — both contested terms now set
    assert duel.duel.challenge in _STATS
    assert duel.duel.background in ELEMENTS

    assert await duel.advance() == 4  # Power (both decline a boost here)
    assert await duel.advance() == 5  # Card — each side plays, queues fill
    assert duel.duel.player_queue and duel.duel.bot_queue

    assert await duel.advance() == 6  # Resolvement — a winner and a per-stat scoreline
    assert isinstance(duel.duel.winner, bool)
    assert len(duel.duel.player_result) == 3
    assert duel.duel.winner_character in (state.player.character.name, state.bot.character.name)

    assert await duel.advance() == 0  # End — the round's terms are recorded for the next showdown
    assert state.previous_challenge == [duel.duel.challenge] or state.previous_challenge == []


async def test_the_loser_forfeits_staked_cards_to_the_winner():
    cat = load_catalog()
    rng = Rng(1)
    state = new_game(cat, rng, cat.character(1))
    duel = Duel(state, rng, _auto_choices())

    while await duel.advance() != 0:  # walk one full showdown through to the swap (the end phase)
        pass

    winner = state.player if duel.duel.winner else state.bot
    loser = state.bot if duel.duel.winner else state.player
    forfeit = duel.duel.bot_stakes if duel.duel.winner else duel.duel.player_stakes

    assert forfeit  # the loser staked at least the card they played
    # identity, not equality: duplicate blank cards make value-based membership meaningless
    for staked in forfeit:
        assert any(card is staked for card in winner.hand)  # the exact card moved to the winner
        assert all(card is not staked for card in loser.hand)  # and left the loser


async def test_the_showdown_loop_runs_until_the_draw_pile_is_empty():
    # A vault turn between showdowns refills the hands, so the loop always terminates on an empty
    # pile (no auto-play deposits → the point limit is never reached; the deck is the terminator).
    cat = load_catalog()
    settings = XiaolinSettings()
    for seed in (1, 3, 7):
        rng = Rng(seed)
        state = new_game(cat, rng, cat.character(1))
        duel = Duel(state, rng, _auto_choices())
        refill_hands(state, settings, rng=rng)

        for _ in range(500):  # bounded guard; a real run ends in ~8–11 showdowns
            if await duel.advance() == 0:  # a showdown ended → take the vault turn before the next
                refill_hands(state, settings, rng=rng)
            if duel.is_over:
                break

        assert duel.is_over
        assert not state.card_deck
