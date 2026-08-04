"""Sands of Time — takes the opponent's strongest hand Wu, or a random deck card if the hand is
empty. Open to any duelist who plays it, not gated to Jack."""

from __future__ import annotations

from termcade.core.rng import Rng

from factories import auto_choices, wu

from xiaolin_showdown.logic.flow.battle import Round
from xiaolin_showdown.logic.schema.catalog import load_catalog
from xiaolin_showdown.logic.flow.duel import Duel
from xiaolin_showdown.logic.flow.setup import new_game


def _duel() -> Duel:
    cat = load_catalog()
    state = new_game(cat, Rng(1), cat.character(1), opponent=cat.character(2))
    duel = Duel(state, Rng(1), auto_choices())
    duel.duel.rounds = [Round(stat="")]
    return duel


def test_steal_takes_the_opponents_strongest_hand_card():
    duel = _duel()
    weak = wu(0, name="Weak", points=1)
    strong = wu(3, name="Strong", points=3)
    duel.state.bot.hand = [weak, strong]
    player_before = len(duel.state.player.hand)
    duel._steal_wu(True)
    assert strong not in duel.state.bot.hand
    assert weak in duel.state.bot.hand
    assert strong in duel.state.player.hand
    assert len(duel.state.player.hand) == player_before + 1


def test_steal_takes_a_deck_card_when_the_opponents_hand_is_empty():
    duel = _duel()
    buried = wu(2, name="Buried", points=2)
    duel.state.bot.hand = []
    duel.state.bot.deck = [buried]
    duel._steal_wu(True)
    assert buried not in duel.state.bot.deck
    assert buried in duel.state.player.hand


def test_steal_is_a_no_op_when_hand_and_deck_are_both_empty():
    duel = _duel()
    duel.state.bot.hand = []
    duel.state.bot.deck = []
    player_before = len(duel.state.player.hand)
    duel._steal_wu(True)
    assert len(duel.state.player.hand) == player_before


def test_steal_works_for_the_bot_against_the_player_too():
    duel = _duel()
    strong = wu(3, name="Strong", points=3)
    duel.state.player.hand = [strong]
    bot_before = len(duel.state.bot.hand)
    duel._steal_wu(False)
    assert strong not in duel.state.player.hand
    assert strong in duel.state.bot.hand
    assert len(duel.state.bot.hand) == bot_before + 1
