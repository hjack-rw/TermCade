"""In-duel power resolution (``resolve_played_power``) — how a played card fills the scoring queues.

Pure and TTY-free: a card is played into a :class:`Round`'s queues and the resulting mutations are
asserted directly. Covers the core behaviours — plain card, Moby Morpher, boost amplification, and
the negative-card curse.
"""

from __future__ import annotations

from termcade.core.rng import Rng

from xiaolin_showdown.logic.catalog import load_catalog
from xiaolin_showdown.logic.duel import Duel, DuelChoices, Round
from xiaolin_showdown.logic.constants import ELEMENTS
from xiaolin_showdown.logic.models import Card, Power
from xiaolin_showdown.logic.mechanics.resolve import resolve_played_power
from xiaolin_showdown.logic.settings import XiaolinSettings
from xiaolin_showdown.logic.setup import new_game
from xiaolin_showdown.logic.turn import refill_hands

_STATS = ("force", "agility", "intellect")


def _card(force, agility, intellect, *, element="water", trigger="hand", effect=0) -> Card:
    stats = {"force": force, "agility": agility, "intellect": intellect}
    return Card(1, "Wu", stats, Power(0, "", trigger, effect, ""), element, "item", 0)


def test_a_plain_card_enters_the_caster_queue_as_an_inert_stand_in():
    duel = Round()
    card = _card(3, 1, 0, element="water")

    resolve_played_power(duel, card, is_player=True, element="water")

    assert len(duel.player.queue) == 1
    assert not duel.bot.queue
    stand_in = duel.player.queue[0]
    assert stand_in.stats == {"force": 3, "agility": 1, "intellect": 0}
    assert stand_in.stats is not card.stats  # a private copy, safe to mutate in the duel
    assert stand_in.power.effect == 0  # neutral power — never re-triggers, never seen as a booster


def test_a_morpher_sets_every_stat_to_one_and_takes_the_chosen_element():
    duel = Round()
    morpher = _card(None, None, None, element="metal", trigger="play", effect=1)

    resolve_played_power(duel, morpher, is_player=True, element="earth")

    stand_in = duel.player.queue[0]
    assert stand_in.stats == {"force": 1, "agility": 1, "intellect": 1}
    assert stand_in.element == "earth"


def test_a_bot_morpher_falls_back_to_the_background_element():
    duel = Round()
    morpher = _card(None, None, None, element="metal", trigger="play", effect=1)

    resolve_played_power(duel, morpher, is_player=False, element="fire")

    assert duel.bot.queue[0].element == "fire"


def test_a_negative_card_curses_the_opponent_and_is_spent_on_your_side():
    duel = Round()
    curse = _card(-2, 0, 0, element="water")

    resolve_played_power(duel, curse, is_player=True, element="water")

    # your own copy contributes nothing...
    assert duel.player.queue[0].stats == {"force": 0, "agility": 0, "intellect": 0}
    # ...while a mirror lands on the opponent, keeping the element it is (it earns them no bonus,
    # because the duel leaves it out of their `earns_bonus` set — see `Duel._earns_bonus`).
    mirror = duel.bot.queue[0]
    assert mirror.stats == {"force": -2, "agility": 0, "intellect": 0}
    assert mirror.element == "water"


def test_a_boost_lends_no_stats_of_its_own():
    duel = Round()
    boost = _card(9, 9, 9, element="water", trigger="boost", effect=1)

    resolve_played_power(duel, boost, is_player=True, element="water")

    assert duel.player.queue[0].stats == {"force": 0, "agility": 0, "intellect": 0}


def test_a_queued_booster_amplifies_the_next_positive_card():
    duel = Round()
    booster = _card(0, 0, 0, element="water", trigger="boost", effect=1)
    duel.player.queue.append(booster)  # played in stage 4, keeps its real power at the head

    resolve_played_power(duel, _card(4, 0, 2, element="water"), is_player=True, element="water")

    # +1 on each stat the played card contributes, 0 where it did not.
    assert booster.stats == {"force": 1, "agility": 0, "intellect": 1}


def test_a_queued_booster_flips_to_the_opponent_on_a_negative_card():
    duel = Round()
    booster = _card(0, 0, 0, element="water", trigger="boost", effect=1)
    duel.player.queue.append(booster)

    resolve_played_power(duel, _card(-3, -1, 0, element="water"), is_player=True, element="water")

    assert booster.stats == {"force": 0, "agility": 0, "intellect": 0}  # spent on your side
    amplifier, curse = duel.bot.queue  # the booster lands left of the curse it doubled
    assert amplifier.stats == {"force": -1, "agility": -1, "intellect": 0}
    assert amplifier.element == "water"  # a mirror keeps what it is; only its power is stripped
    assert curse.stats == {"force": -3, "agility": -1, "intellect": 0}


def test_a_mirrored_booster_cannot_boost_the_duelist_it_lands_on():
    """It keeps the booster's *name*, never its power — else the victim's next card is amplified
    by their attacker's Wu, because it sits at the head of their queue."""
    duel = Round()
    duel.player.queue.append(_card(0, 0, 0, element="water", trigger="boost", effect=1))

    resolve_played_power(duel, _card(-3, -1, 0, element="water"), is_player=True, element="water")

    assert all(card.power.trigger == "none" for card in duel.bot.queue)


# --- the stage machine (scripted, headless) ----------------------------------------------
# The stage machine awaits its choices, so the scripted "player" supplies async callbacks that
# always take the first legal option and never boost — enough to drive a full showdown.
async def _first(options: list[str]) -> str:
    return options[0]


async def _first_card(playable: list[Card]) -> Card:
    return playable[0]


async def _no_boost(_options: list[Card]) -> Card | None:
    return None


async def _one_wu(options: list[int]) -> int:
    return options[0]  # the smallest legal stake


async def _water(_background: str) -> str:
    return "water"


def _auto_choices() -> DuelChoices:
    return DuelChoices(
        challenge=_first, background=_first, wager=_one_wu,
        boost=_no_boost, card=_first_card, element=_water,
    )


async def test_a_scripted_showdown_walks_all_six_stages():
    cat = load_catalog()
    rng = Rng(1)
    state = new_game(cat, rng, cat.character(1))  # Omi
    duel = Duel(state, rng, _auto_choices())

    deck_before = len(state.card_deck)
    assert await duel.advance() == 1  # Commitment — prize drawn, priority resolved to a concrete side
    assert duel.duel.stakes is not None
    assert len(state.card_deck) == deck_before - 1
    assert isinstance(duel.duel.player_priority, bool)

    assert await duel.advance() == 2  # Challenge / Background — both contested terms now set
    assert duel.duel.challenge in _STATS
    assert duel.duel.background in ELEMENTS

    # Boost and Card repeat once per Wu wagered — a best-of-3 is three exchanges, not one.
    for expected in range(1, duel.duel.wager + 1):
        assert await duel.advance() == 3  # Boost (both decline here)
        assert await duel.advance() == 4  # Card — each plays; the exchange is scored at once
        assert duel.duel.round_number == expected
        assert duel.duel.round.player.queue and duel.duel.round.bot.queue
        assert len(duel.duel.round.player.result) == 3

    assert await duel.advance() == 5  # Resolvement — the match is weighed
    assert isinstance(duel.duel.winner, bool)
    assert len(duel.duel.rounds) == duel.duel.wager
    assert duel.duel.winner_character in (state.player.character.name, state.bot.character.name)

    assert await duel.advance() == 0  # End — the round's terms are recorded for the next showdown
    assert state.previous_challenge == [duel.duel.challenge] or state.previous_challenge == []


# --- initiative is a property of the hands, not a phase --------------------------------


def _duel_over(state) -> Duel:
    return Duel(state, Rng(1), _auto_choices())


async def test_a_showdown_opens_with_initiative_already_resolved():
    """Nothing is pressed yet, and the board can already show who leads."""
    cat = load_catalog()
    state = new_game(cat, Rng(1), cat.character(1))
    _flatten_initiative(state)
    state.player.hand[0].power = Power(9, "Buff", "hand", 0, "", 2)

    duel = _duel_over(state)

    assert duel.duel.stage == 0  # the opening board, before any Continue
    assert duel.duel.player.initiative == 2
    assert duel.duel.player_priority is True


def _flatten_initiative(state) -> None:
    """Strip every initiative bonus from both hands, so the two sides tie at 0."""
    for duelist in (state.player, state.bot):
        for card in duelist.hand:
            card.power = Power(0, "", "none", 0, "")


async def test_a_tied_initiative_leaves_priority_to_the_coin():
    cat = load_catalog()
    state = new_game(cat, Rng(1), cat.character(1))
    _flatten_initiative(state)

    duel = _duel_over(state)

    assert duel.duel.player.initiative == duel.duel.bot.initiative == 0
    assert duel.duel.player_priority is None  # the coin is thrown at Commitment


async def test_the_coin_settles_a_tie_at_commitment():
    cat = load_catalog()
    state = new_game(cat, Rng(1), cat.character(1))
    _flatten_initiative(state)
    duel = _duel_over(state)

    await duel.advance()

    assert isinstance(duel.duel.player_priority, bool)


async def test_a_clear_initiative_is_never_re_rolled_by_the_coin():
    """Continue commits you to the priority you can already see on the board."""
    cat = load_catalog()
    state = new_game(cat, Rng(1), cat.character(1))
    _flatten_initiative(state)
    state.player.hand[0].power = Power(9, "Buff", "hand", 0, "", 1)
    duel = _duel_over(state)
    assert duel.duel.player_priority is True

    await duel.advance()

    assert duel.duel.player_priority is True


async def test_the_first_advance_commits_the_showdown():
    """The opening press draws the prize — from there nothing is un-staked, so no retreat."""
    cat = load_catalog()
    state = new_game(cat, Rng(1), cat.character(1))
    duel = _duel_over(state)
    assert duel.duel.stakes is None  # the opening board stakes nothing

    await duel.advance()

    assert duel.duel.stakes is not None


async def test_a_new_showdown_re_reads_initiative_from_the_hands():
    """Cards change hands at End, so the next round's initiative is not the last round's."""
    cat = load_catalog()
    state = new_game(cat, Rng(1), cat.character(1))
    duel = _duel_over(state)
    while await duel.advance() != 0:  # the showdown runs as many rounds as were wagered
        pass
    assert duel.duel.stage == 0

    _flatten_initiative(state)
    state.player.hand[0].power = Power(9, "Buff", "hand", 0, "", 3)
    await duel.advance()  # resets the round, re-reading the hands

    assert duel.duel.player.initiative == 3


async def test_the_loser_forfeits_staked_cards_to_the_winner():
    cat = load_catalog()
    rng = Rng(1)
    state = new_game(cat, rng, cat.character(1))
    duel = Duel(state, rng, _auto_choices())

    while await duel.advance() != 0:  # walk one full showdown through to the swap (the end phase)
        pass

    winner = state.player if duel.duel.winner else state.bot
    loser = state.bot if duel.duel.winner else state.player
    forfeit = duel.duel.bot.stakes if duel.duel.winner else duel.duel.player.stakes

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


# --- the duel wires both halves of the elemental bonus into scoring -------------------


async def test_resolvement_negates_the_bonus_a_curse_would_have_earned_its_caster():
    """The rule lives in `count_end_stats`; this asserts the duel actually hands it the mirrors."""
    cat = load_catalog()
    state = new_game(cat, Rng(1), cat.character(1))
    duel = _duel_over(state)
    duel.duel.stakes = cat.card(6)
    duel.duel.challenge, duel.duel.background = "force", "water"
    base = state.player.character.stats["force"]

    # a water curse landed on the player: its resonance must count against them
    duel.duel.rounds.append(Round())
    resolve_played_power(duel.duel.round, cat.card(23), is_player=False, element="water")  # Silk Spitter
    duel._score_round(duel.duel.round)

    assert duel.duel.round.player.result[0] == base - 1


# --- a boost is spent once a showdown, not once a round ------------------------------


def _boost_card(name: str) -> Card:
    return Card(9, name, {"force": None, "agility": None, "intellect": None},
                Power(0, "", "boost", 1, ""), "water", "item", 0)


async def test_a_boost_wu_cannot_be_played_twice_in_one_showdown():
    """Choosing WHICH round to amplify is the decision. Replaying one boost every round is not."""
    cat = load_catalog()
    state = new_game(cat, Rng(1), cat.character(1))
    bracelet = _boost_card("Wushu Bracelet")
    state.player.hand.append(bracelet)
    duel = Duel(state, Rng(1), _auto_choices())
    duel.duel.rounds.append(Round())

    offered_first = duel._boost_options(state.player, is_player=True)
    duel._commit_boost(bracelet, is_player=True)
    offered_again = duel._boost_options(state.player, is_player=True)

    assert any(c is bracelet for c in offered_first)
    assert not any(c is bracelet for c in offered_again)  # spent — never offered again


async def test_a_dragon_is_spent_once_too():
    """It is inalienable and never leaves the hand, so nothing else would stop it being replayed."""
    cat = load_catalog()
    state = new_game(cat, Rng(1), cat.character(1))
    dragon = next(c for c in state.player.inalienable_hand if c.power.trigger == "boost")
    duel = Duel(state, Rng(1), _auto_choices())
    duel.duel.rounds.append(Round())

    duel._commit_boost(dragon, is_player=True)

    assert not any(c is dragon for c in duel._boost_options(state.player, is_player=True))


async def test_holding_two_boosts_lets_you_amplify_two_rounds():
    """Guards the rule above: spending one must not lock the other out."""
    cat = load_catalog()
    state = new_game(cat, Rng(1), cat.character(1))
    first, second = _boost_card("Bracelet A"), _boost_card("Bracelet B")
    state.player.hand.extend([first, second])
    duel = Duel(state, Rng(1), _auto_choices())
    duel.duel.rounds.append(Round())

    duel._commit_boost(first, is_player=True)

    assert any(c is second for c in duel._boost_options(state.player, is_player=True))


async def test_a_spent_boost_stays_spent_across_rounds():
    """The showdown is the unit, not the round — a new Round must not resurrect it."""
    cat = load_catalog()
    state = new_game(cat, Rng(1), cat.character(1))
    bracelet = _boost_card("Wushu Bracelet")
    state.player.hand.append(bracelet)
    duel = Duel(state, Rng(1), _auto_choices())
    duel.duel.rounds.append(Round())
    duel._commit_boost(bracelet, is_player=True)

    duel.duel.rounds.append(Round())  # round two opens

    assert not any(c is bracelet for c in duel._boost_options(state.player, is_player=True))


async def test_a_booster_fielded_as_an_ordinary_wu_cannot_also_boost():
    """A best-of-3 can force a booster into the card slot. Once staked, it is gone.

    Otherwise the same Wu is spent twice: played as a card in round one, and still lifting another
    card in round two.
    """
    cat = load_catalog()
    state = new_game(cat, Rng(1), cat.character(1))
    bracelet = _boost_card("Wushu Bracelet")
    state.player.hand.append(bracelet)
    duel = Duel(state, Rng(1), _auto_choices())
    duel.duel.rounds.append(Round())

    duel.duel.player.stakes.append(bracelet)  # forced to play it as an ordinary Wu

    assert not any(c is bracelet for c in duel._boost_options(state.player, is_player=True))


async def test_a_booster_left_in_hand_is_still_offered():
    """Guards the test above: staking one Wu must not lock every boost out."""
    cat = load_catalog()
    state = new_game(cat, Rng(1), cat.character(1))
    played, held = _boost_card("Bracelet A"), _boost_card("Bracelet B")
    state.player.hand.extend([played, held])
    duel = Duel(state, Rng(1), _auto_choices())
    duel.duel.rounds.append(Round())

    duel.duel.player.stakes.append(played)

    assert any(c is held for c in duel._boost_options(state.player, is_player=True))


async def test_you_cannot_boost_with_a_wu_you_owe_to_a_round():
    """Three Wu owed, three Wu in hand — the booster among them must be FIELDED, not spent.

    Otherwise a duelist boosts with it and then has nothing to field in the last round, which is a
    way of answering a best-of-3 with two Wu.
    """
    cat = load_catalog()
    state = new_game(cat, Rng(1), cat.character(1))
    bracelet = _boost_card("Wushu Bracelet")
    state.player.hand = state.player.hand[:2] + [bracelet]  # exactly three, one a booster
    duel = Duel(state, Rng(1), _auto_choices())
    duel.duel.wager = 3
    duel.duel.rounds.append(Round())

    offered = duel._boost_options(state.player, is_player=True)

    assert not any(c is bracelet for c in offered)


async def test_the_inalienable_dragon_is_always_affordable():
    """It can never be fielded as a card, so spending it costs you no round."""
    cat = load_catalog()
    state = new_game(cat, Rng(1), cat.character(1))
    state.player.hand = state.player.hand[:3]
    dragon = next(c for c in state.player.inalienable_hand if c.power.trigger == "boost")
    duel = Duel(state, Rng(1), _auto_choices())
    duel.duel.wager = 3
    duel.duel.rounds.append(Round())

    assert any(c is dragon for c in duel._boost_options(state.player, is_player=True))


async def test_a_spare_wu_makes_the_booster_affordable_again():
    """Guards the rule: the cost is what you OWE, not the mere presence of a booster."""
    cat = load_catalog()
    state = new_game(cat, Rng(1), cat.character(1))
    bracelet = _boost_card("Wushu Bracelet")
    state.player.hand = state.player.hand[:3] + [bracelet]  # four Wu, three owed
    duel = Duel(state, Rng(1), _auto_choices())
    duel.duel.wager = 3
    duel.duel.rounds.append(Round())

    assert any(c is bracelet for c in duel._boost_options(state.player, is_player=True))
