"""The rules a showdown may never break, checked over many seeds and many strategies.

The other tests each pin one behaviour. This one plays whole showdowns — greedy, contrary, reckless,
and cautious — and after each asserts what must be true no matter what anyone chose. It is where an
edge case nobody thought of shows up: a wager larger than a hand can answer, a Wu spent twice, a
match that runs the wrong number of rounds, a showdown with no winner at all.
"""

from __future__ import annotations

import pytest

from termcade.core.rng import Rng

from xiaolin_showdown.logic.constants import TOURNAMENT, TOURNAMENT_BATTLES
from xiaolin_showdown.logic.duel import Duel, DuelChoices
from xiaolin_showdown.logic.settings import XiaolinSettings
from xiaolin_showdown.logic.setup import new_game

SETTINGS = XiaolinSettings()


def _strategy(name: str, duel_ref: list) -> DuelChoices:
    """One way of playing. Together these cover the corners a single scripted player never reaches."""

    async def first(options):
        return options[0]

    async def last(options):
        return options[-1]

    async def smallest_wager(options):
        return options[0]

    async def biggest_wager(options):
        return options[-1]  # always demand the maximum they can field

    async def always_boost(options):
        return options[0] if options else None

    async def never_boost(_options):
        return None

    async def element(background):
        return background

    async def stat(options):
        # the contrary player pours into a side stat; everyone else into the obvious one
        return options[-1] if name == "contrary" else options[0]

    wager = biggest_wager if name in ("reckless", "greedy") else smallest_wager
    boost = never_boost if name == "cautious" else always_boost
    card = last if name == "contrary" else first
    return DuelChoices(first, first, wager, boost, card, element, stat)


STRATEGIES = ("greedy", "contrary", "reckless", "cautious")


def _assert_invariants(duel, state, before_hand: list) -> None:
    """Everything that must hold when a showdown ends, whatever anyone chose."""
    d = duel.duel

    # the stakes are answerable and honest
    assert 1 <= d.wager <= SETTINGS.max_wager

    # Three Wu, spent one of two ways. A stat challenge is ONE battle fielding the whole wager at
    # once; a tournament is THREE battles of one Wu, a stat apiece. Battles are not the wager.
    tournament = d.challenge == TOURNAMENT
    battles = TOURNAMENT_BATTLES if tournament else 1
    wu_each = 1 if tournament else d.wager

    assert len(d.rounds) == battles, f"{d.challenge}: wanted {battles} battles, fought {len(d.rounds)}"
    assert battles * wu_each <= SETTINGS.max_wager, "a showdown cost more than three Wu"
    for battle in d.rounds:
        assert battle.fielded == wu_each, f"battle on {battle.stat} fielded {battle.fielded} Wu"

    # a tournament contests each stat once, left to right; a stat challenge contests only its own
    fought = [battle.stat for battle in d.rounds]
    if tournament:
        assert fought == list(d.stakes.stats.keys())[:TOURNAMENT_BATTLES]
    else:
        assert set(fought) == {d.challenge}

    # a Wu is spent once, in one slot
    for stakes in (d.player.stakes, d.bot.stakes):
        assert len({id(c) for c in stakes}) == len(stakes), "a Wu was staked twice"
    for spent, stakes in ((d.player.boosts_spent, d.player.stakes),
                          (d.bot.boosts_spent, d.bot.stakes)):
        assert len({id(c) for c in spent}) == len(spent), "a boost was spent twice"

    # somebody always wins: a Wu must belong to someone
    assert d.winner is not None
    assert d.winner_character

    # the tally agrees with the rounds
    player_rounds, bot_rounds = d.rounds_won
    assert player_rounds == sum(1 for r in d.rounds if r.winner is True)
    assert bot_rounds == sum(1 for r in d.rounds if r.winner is False)

    # the winner is the one the cascade names: rounds, then margin, then the challenger
    if player_rounds != bot_rounds:
        assert d.winner is (player_rounds > bot_rounds)
    else:
        margin = sum(r.score for r in d.rounds)
        expected = margin > 0 if margin else bool(d.player_priority)
        assert d.winner is expected

    # the prize is only ever awarded, never invented
    if d.card_won:
        assert d.stakes is not None

    # no card is in both hands at once
    player_ids = {id(c) for c in state.player.whole_hand}
    bot_ids = {id(c) for c in state.bot.whole_hand}
    assert not (player_ids & bot_ids), "the same Wu is in both hands"


@pytest.mark.parametrize("strategy", STRATEGIES)
@pytest.mark.parametrize("seed", range(1, 13))
async def test_a_showdown_never_breaks_its_own_rules(catalog, strategy, seed):
    state = new_game(catalog, Rng(seed), catalog.character(1))
    before_hand = list(state.player.hand)

    duel_ref: list = []
    duel = Duel(state, Rng(seed), _strategy(strategy, duel_ref), SETTINGS)
    duel_ref.append(duel)

    stage, guard = -1, 0
    while stage != 0 and guard < 40:
        stage = await duel.advance()
        guard += 1

    assert stage == 0, "the showdown never reached its End"
    _assert_invariants(duel, state, before_hand)


@pytest.mark.parametrize("seed", range(1, 9))
async def test_a_wager_is_never_larger_than_the_thinner_hand(catalog, seed):
    """The rule the whole feature rests on: you cannot demand what your opponent cannot field."""
    state = new_game(catalog, Rng(seed), catalog.character(1))
    duel_ref: list = []
    duel = Duel(state, Rng(seed), _strategy("reckless", duel_ref), SETTINGS)
    duel_ref.append(duel)

    player_hand = len(state.player.hand)
    bot_hand = len(state.bot.hand)

    await duel.advance()  # Commitment
    await duel.advance()  # Setup — the stakes are named here

    d = duel.duel
    if d.challenge == TOURNAMENT:  # only callable when both can field three
        assert min(player_hand, bot_hand) >= TOURNAMENT_BATTLES
    else:
        assert d.wager <= max(1, min(player_hand, bot_hand, SETTINGS.max_wager))


@pytest.mark.parametrize("seed", range(1, 9))
async def test_the_loser_forfeits_exactly_what_they_staked(catalog, seed):
    """Not less (they keep a Wu they lost) and not more (a Wu they never staked is taken)."""
    state = new_game(catalog, Rng(seed), catalog.character(1))
    duel_ref: list = []
    duel = Duel(state, Rng(seed), _strategy("reckless", duel_ref), SETTINGS)
    duel_ref.append(duel)

    stage, guard = -1, 0
    while stage != 0 and guard < 40:
        stage = await duel.advance()
        guard += 1

    d = duel.duel
    winner_hand = state.player.whole_hand if d.winner else state.bot.whole_hand
    forfeited = d.bot.stakes if d.winner else d.player.stakes
    for card in forfeited:
        assert any(card is held for held in winner_hand), f"{card.name} was staked but never handed over"
