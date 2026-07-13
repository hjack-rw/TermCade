"""In-duel power resolution (``resolve_played_power``) — how a played card fills the scoring queues.

Pure and TTY-free: a card is played into a :class:`Round`'s queues and the resulting mutations are
asserted directly. Covers the core behaviours — plain card, Moby Morpher, boost amplification, and
the negative-card curse.
"""

from __future__ import annotations

from copy import deepcopy

import pytest

from termcade.core.rng import Rng

from xiaolin_showdown.logic.catalog import load_catalog
from xiaolin_showdown.logic.battle import Round
from xiaolin_showdown.logic.mechanics.cards import excluding
from xiaolin_showdown.logic.mechanics.powers import MORPH_ASIDE, MORPH_CONTESTED
from xiaolin_showdown.logic.duel import Duel, DuelChoices
from xiaolin_showdown.logic.constants import ELEMENTS, TOURNAMENT, TOURNAMENT_BATTLES
from xiaolin_showdown.logic.models import Card, Mechanic, Power
from xiaolin_showdown.logic.mechanics.resolve import resolve_played_power
from xiaolin_showdown.logic.settings import XiaolinSettings
from xiaolin_showdown.logic.setup import new_game
from xiaolin_showdown.logic.turn import refill_hands

_STATS = ("force", "agility", "intellect")


def _card(force, agility, intellect, *, element="water", mechanic=Mechanic.INITIATIVE) -> Card:
    stats = {"force": force, "agility": agility, "intellect": intellect}
    return Card(1, "Wu", stats, Power(0, "", mechanic, ""), element, "item", 0)


def test_a_plain_card_enters_the_caster_queue_as_an_inert_stand_in():
    duel = Round()
    card = _card(3, 1, 0, element="water")

    resolve_played_power(duel, card, is_player=True, element="water")

    assert len(duel.player.queue) == 1
    assert not duel.bot.queue
    stand_in = duel.player.queue[0]
    assert stand_in.stats == {"force": 3, "agility": 1, "intellect": 0}
    assert stand_in.stats is not card.stats  # a private copy, safe to mutate in the duel
    assert stand_in.power.mechanic is Mechanic.FILLER  # neutral — never re-triggers, never a booster


def test_a_morpher_dips_on_the_contested_stat_and_takes_the_chosen_element():
    """It gives ground where the battle is actually fought — and buys the element that lifts it."""
    duel = Round(stat="force")
    morpher = _card(None, None, None, element="metal", mechanic=Mechanic.MORPH)

    resolve_played_power(duel, morpher, is_player=True, element="earth")

    stand_in = duel.player.queue[0]
    assert stand_in.stats == {
        "force": MORPH_CONTESTED,  # the stat this battle contests
        "agility": MORPH_ASIDE,
        "intellect": MORPH_ASIDE,
    }
    assert stand_in.element == "earth"


def test_a_bot_morpher_falls_back_to_the_background_element():
    duel = Round(stat="force")
    morpher = _card(None, None, None, element="metal", mechanic=Mechanic.MORPH)

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
    boost = _card(9, 9, 9, element="water", mechanic=Mechanic.BOOST)

    resolve_played_power(duel, boost, is_player=True, element="water")

    assert duel.player.queue[0].stats == {"force": 0, "agility": 0, "intellect": 0}


def test_a_queued_booster_amplifies_the_next_positive_card():
    duel = Round()
    booster = _card(0, 0, 0, element="water", mechanic=Mechanic.BOOST)
    duel.player.queue.append(booster)  # played in stage 4, keeps its real power at the head

    resolve_played_power(duel, _card(4, 0, 2, element="water"), is_player=True, element="water")

    # +1 on each stat the played card contributes, 0 where it did not.
    assert booster.stats == {"force": 1, "agility": 0, "intellect": 1}


def test_a_queued_booster_flips_to_the_opponent_on_a_negative_card():
    duel = Round()
    booster = _card(0, 0, 0, element="water", mechanic=Mechanic.BOOST)
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
    duel.player.queue.append(_card(0, 0, 0, element="water", mechanic=Mechanic.BOOST))

    resolve_played_power(duel, _card(-3, -1, 0, element="water"), is_player=True, element="water")

    assert all(card.power.mechanic is Mechanic.FILLER for card in duel.bot.queue)


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


async def _first_stat(options: list[str]) -> str:
    """Where an Orb of Tornami or a Kaijin's Curse pours itself, when nobody is choosing on purpose."""
    return options[0]


def _auto_choices() -> DuelChoices:
    return DuelChoices(
        challenge=_first, background=_first, wager=_one_wu,
        boost=_no_boost, card=_first_card, element=_water, stat=_first_stat,
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
    assert duel.duel.challenge in (*_STATS, TOURNAMENT)
    assert duel.duel.background in ELEMENTS

    # Boost and Card repeat once per Wu that must be fielded — three into one battle, or one into
    # each of three. A battle is only scored once it is full, so `result` fills on its last Wu.
    tournament = duel.duel.challenge == TOURNAMENT
    battles = TOURNAMENT_BATTLES if tournament else 1
    wu_per_battle = 1 if tournament else duel.duel.wager

    for wu in range(1, battles * wu_per_battle + 1):
        assert await duel.advance() == 3  # Boost (both decline here)
        assert await duel.advance() == 4  # Card — each fields one Wu
        assert duel.duel.round_number == (wu - 1) // wu_per_battle + 1
        assert duel.duel.round.player.queue and duel.duel.round.bot.queue
        full = duel.duel.round.fielded == wu_per_battle
        assert len(duel.duel.round.player.result) == (3 if full else 0)

    assert await duel.advance() == 5  # Resolvement — the showdown is weighed
    assert isinstance(duel.duel.winner, bool)
    assert len(duel.duel.rounds) == battles
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
    state.player.hand[0].power = Power(9, "Buff", Mechanic.INITIATIVE, "", 2)

    duel = _duel_over(state)

    assert duel.duel.stage == 0  # the opening board, before any Continue
    assert duel.duel.player.initiative == 2
    assert duel.duel.player_priority is True


def _flatten_initiative(state) -> None:
    """Strip every initiative bonus from both hands, so the two sides tie at 0."""
    for duelist in (state.player, state.bot):
        for card in duelist.hand:
            card.power = Power(0, "", Mechanic.FILLER, "")


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
    state.player.hand[0].power = Power(9, "Buff", Mechanic.INITIATIVE, "", 1)
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
    state.player.hand[0].power = Power(9, "Buff", Mechanic.INITIATIVE, "", 3)
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

    # a water curse landed on the player: its resonance must count against them, and its own force
    # wound with it. Both read off the card — this test is about the *bonus*, not the card's balance.
    spitter = cat.card(23)  # Silk Spitter, water
    duel.duel.rounds.append(Round(stat="force"))  # the battle contests force
    resolve_played_power(duel.duel.round, spitter, is_player=False, element="water")
    duel._score_round(duel.duel.round)

    wound = spitter.stats["force"]  # negative
    assert duel.duel.round.player.result[0] == base + wound - 1  # -1: it resonates, so it bites deeper


# --- a boost is spent once a showdown, not once a round ------------------------------


def _boost_card(name: str) -> Card:
    return Card(9, name, {"force": None, "agility": None, "intellect": None},
                Power(0, "", Mechanic.BOOST, ""), "water", "item", 0)


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
    dragon = next(c for c in state.player.inalienable_hand if c.power.mechanic is Mechanic.DRAGON)
    duel = Duel(state, Rng(1), _auto_choices())
    duel.duel.rounds.append(Round())

    duel._commit_boost(dragon, is_player=True)

    assert not any(c is dragon for c in duel._boost_options(state.player, is_player=True))


async def test_the_dragon_you_were_born_holding_is_never_at_stake():
    """The birthright cannot be lost — boosting with it stakes nothing."""
    cat = load_catalog()
    state = new_game(cat, Rng(1), cat.character(1))
    dragon = next(c for c in state.player.inalienable_hand if c.power.mechanic is Mechanic.DRAGON)
    duel = Duel(state, Rng(1), _auto_choices())
    duel.duel.rounds.append(Round())

    duel._commit_boost(dragon, is_player=True)

    assert not duel.duel.player.stakes


async def test_a_wudai_weapon_you_found_is_at_stake_like_anything_else():
    """The Shimo Staff boosts exactly as a dragon does — and is lost exactly as a Wu does.

    The rule is *where the Wu sits*, not what its power is: only the inalienable slot is safe. A
    dragon pulled out of the draw pile was never anybody's birthright, so laying it down risks it.
    """
    cat = load_catalog()
    state = new_game(cat, Rng(1), cat.character(1))
    staff = deepcopy(cat.card(44))  # Shimo Staff — a dragon nobody was born holding
    state.player.hand.append(staff)
    duel = Duel(state, Rng(1), _auto_choices())
    duel.duel.rounds.append(Round())

    duel._commit_boost(staff, is_player=True)

    assert any(c is staff for c in duel.duel.player.stakes)


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
    dragon = next(c for c in state.player.inalienable_hand if c.power.mechanic is Mechanic.DRAGON)
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


# --- three Wu, spent one of two ways -------------------------------------------------


def test_a_second_boost_in_a_battle_lifts_the_second_wu_not_the_first():
    """A battle can field three Wu, each with its own boost.

    Boosts and Wu go down as pairs, so the live boost is the tail of the queue: everything before it
    is a spent stand-in. Each boost lifts the Wu laid down after it, and only that one.
    """
    duel = Round(stat="force")
    first_boost = _card(0, 0, 0, element="water", mechanic=Mechanic.BOOST)
    duel.player.queue.append(first_boost)
    resolve_played_power(duel, _card(4, 0, 0, element="water"), is_player=True, element="water")
    assert first_boost.stats == {"force": 1, "agility": 0, "intellect": 0}  # lifted Wu one

    second_boost = _card(0, 0, 0, element="water", mechanic=Mechanic.BOOST)
    duel.player.queue.append(second_boost)
    resolve_played_power(duel, _card(0, 0, 3, element="water"), is_player=True, element="water")

    assert second_boost.stats == {"force": 0, "agility": 0, "intellect": 1}, "the second boost was inert"
    assert first_boost.stats == {"force": 1, "agility": 0, "intellect": 0}, "the first boost fired twice"


async def _run(duel) -> None:
    stage, guard = -1, 0
    while stage != 0 and guard < 40:
        stage = await duel.advance()
        guard += 1


def _forced(challenge: str, wager: int) -> DuelChoices:
    """A player who always calls ``challenge`` and always answers ``wager``."""

    async def pick_challenge(options):
        return challenge if challenge in options else options[0]

    async def pick_wager(options):
        return wager if wager in options else options[-1]

    return DuelChoices(
        pick_challenge, _first, pick_wager, _no_boost, _first_card, _water, _first_stat
    )


async def _leading_player(cat, challenge: str, wager: int):
    """A showdown on the first seed where the PLAYER holds priority — only then do they call the
    challenge. Priority is read off the hands inside `advance`, so it cannot simply be assigned."""
    for seed in range(1, 40):
        rng = Rng(seed)
        state = new_game(cat, rng, cat.character(1))
        duel = Duel(state, rng, _forced(challenge, wager), XiaolinSettings())
        await duel.advance()  # Commitment — priority is now a concrete side
        if duel.duel.player_priority:
            return duel
    raise AssertionError("no seed in 1..40 gave the player priority")


async def test_a_wagered_stat_challenge_is_one_battle_fielding_every_wu_at_once():
    """Three Wu is not three fights. They land together, on one field, and are summed."""
    cat = load_catalog()
    duel = await _leading_player(cat, "force", 3)

    await _run(duel)

    assert duel.duel.challenge == "force"
    assert len(duel.duel.rounds) == 1, "a wager bought extra battles — it must only widen the one"
    assert duel.duel.round.fielded == duel.duel.wager
    assert duel.duel.round.stat == "force"


async def test_a_tournament_is_three_battles_contesting_each_stat_left_to_right():
    cat = load_catalog()
    duel = await _leading_player(cat, TOURNAMENT, 1)

    await _run(duel)

    if duel.duel.challenge != TOURNAMENT:
        pytest.skip("a tournament was not on the table for this seed (a hand held under three Wu)")

    assert [battle.stat for battle in duel.duel.rounds] == list(_STATS)
    assert all(battle.fielded == 1 for battle in duel.duel.rounds), "a tournament fields one Wu a battle"
    assert len(duel.duel.player.stakes) <= TOURNAMENT_BATTLES + 1  # three Wu, plus a boost at most


async def test_neither_duelist_can_see_the_wu_the_other_fields():
    """Gong Yi Tanpai is a simultaneous reveal.

    The code has to run in some order, so the danger is that the order leaks: whoever the machine
    happens to ask second could answer a Wu already on the ground. Nobody may. The player is asked
    first, so this watches the board they are shown — the opponent must never have fielded yet.
    """
    cat = load_catalog()
    ahead: list[bool] = []

    def _fielded(side) -> int:
        """Wu this duelist actually put down. A fielded Wu is a neutral-power stand-in; a boost keeps
        its real power, and a curse the *opponent* cast lands here as a stand-in that is not yours."""
        own = excluding(side.queue, side.suffered)
        return sum(1 for c in own if c.power.mechanic is Mechanic.FILLER)

    async def watch(playable):
        battle = ref[0].duel.round
        # `fielded` counts the exchanges already closed, so the opponent may have that many Wu down
        # and no more. One more would be the Wu of THIS exchange — an answer to a card not yet played.
        ahead.append(_fielded(battle.bot) > battle.fielded)
        return playable[0]

    for seed in range(1, 30):
        rng = Rng(seed)
        state = new_game(cat, rng, cat.character(1))
        ref: list = []
        duel = Duel(
            state,
            rng,
            DuelChoices(_first, _first, _one_wu, _no_boost, watch, _water, _first_stat),
            XiaolinSettings(),
        )
        ref.append(duel)

        ahead.clear()
        stage, guard = -1, 0
        while stage != 0 and guard < 40:
            stage = await duel.advance()
            guard += 1

        assert not any(ahead), f"seed {seed}: the player was answering a Wu the opponent had just fielded"


async def test_the_opponent_chooses_against_the_board_before_you_moved():
    """The mirror of the above: the opponent must not read the Wu the player just committed.

    It is the same leak from the other side, and the only one a test of the player's view cannot see.
    """
    cat = load_catalog()
    boards: list[int] = []

    import xiaolin_showdown.logic.duel as duel_module

    real = duel_module.bot.choose_card

    def spy(battle, ground, playable, rng, *, is_player=False):
        boards.append(sum(1 for c in battle.player.queue if c.power.mechanic is Mechanic.FILLER))
        return real(battle, ground, playable, rng, is_player=is_player)

    duel_module.bot.choose_card = spy
    try:
        for seed in range(1, 20):
            rng = Rng(seed)
            state = new_game(cat, rng, cat.character(1))
            duel = Duel(state, rng, _auto_choices(), XiaolinSettings())
            stage, guard = -1, 0
            boards.clear()
            while stage != 0 and guard < 40:
                stage = await duel.advance()
                guard += 1
            # within a battle the opponent may see Wu fielded in EARLIER exchanges of that battle,
            # but never the one the player is committing to right now
            assert boards == sorted(boards), f"seed {seed}: the opponent read a Wu mid-exchange"
            assert boards[:1] in ([], [0]), f"seed {seed}: the opponent saw the opening Wu"
    finally:
        duel_module.bot.choose_card = real
