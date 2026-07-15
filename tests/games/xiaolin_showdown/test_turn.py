"""The vault turn — hand-size upkeep between showdowns (`oversee_hand_size` / `refill_hands`).

Pure and TTY-free: small hand-crafted states are balanced directly, no catalog or screen needed.
This is the loop terminator, so the emphasis is the draw/discard edges that keep a hand playable.
"""

from __future__ import annotations

from termcade.core.rng import Rng
from termcade.core.settings import Difficulty

from xiaolin_showdown.logic.models import Card, Mechanic, Player
from xiaolin_showdown.logic.settings import XiaolinSettings
from xiaolin_showdown.logic.state import XiaolinState
from xiaolin_showdown.logic.mechanics.powers import GAMBLE_SPREAD
from xiaolin_showdown.logic.turn import (
    VAULT,
    DUEL_FLOOR,
    PASSED,
    bank_value,
    bot_turn,
    max_hand_size,
    oversee_hand_size,
    refill_hands,
)

from factories import duelist, wu


def _card(*, mechanic=Mechanic.INITIATIVE, points=0, stats=None) -> Card:
    stats = {"force": 1, "agility": 1, "intellect": 1} if stats is None else stats
    return wu(**stats, mechanic=mechanic, points=points)


_JUNK = {"force": 0, "agility": 0, "intellect": 0}  # no duel value — a hard bot banks this first


def _player(hand: int, *, deck: int = 0) -> Player:
    return duelist(hand=[_card() for _ in range(hand)], deck=[_card() for _ in range(deck)])


def _state(player: Player, bot: Player, *, main: int = 0) -> XiaolinState:
    return XiaolinState(catalog=None, player=player, bot=bot, card_deck=[_card() for _ in range(main)])  # type: ignore[arg-type]


_SETTINGS = XiaolinSettings(max_hand_size=6, actions_per_turn=1, empty_draw_limit=3)


def test_max_hand_size_grows_by_one_with_a_third_arm_sash():
    assert max_hand_size(_player(3), 6) == 6
    sashed = _player(2)
    sashed.hand.append(_card(mechanic=Mechanic.HAND_SIZE))  # the Third-Arm Sash
    assert max_hand_size(sashed, 6) == 7


def test_an_over_limit_hand_sheds_the_surplus_to_the_personal_deck():
    player = _player(8)  # two over the limit of six
    state = _state(player, _player(3))

    settled = oversee_hand_size(state, is_player=True, settings=_SETTINGS, rng=Rng(0))

    assert settled is False  # it shed cards — the vault loop will re-check
    assert len(player.hand) == 6
    assert len(player.deck) == 2  # the two surplus Wu went to the personal deck


def test_a_short_hand_is_left_for_the_player_to_draw():
    player = _player(4, deck=3)  # under the limit, with cards waiting in the personal deck
    state = _state(player, _player(3))

    settled = oversee_hand_size(state, is_player=True, settings=_SETTINGS, rng=Rng(0))

    assert settled is True  # a short hand is not auto-topped-up — that is the player's Draw
    assert len(player.hand) == 4  # unchanged
    assert state.actions_taken == 0


def test_an_empty_hand_is_refilled_from_the_main_pile():
    player = _player(0)  # empty hand, empty personal deck
    state = _state(player, _player(3), main=5)

    oversee_hand_size(state, is_player=True, settings=_SETTINGS, rng=Rng(0))

    assert len(player.hand) == 3  # emergency-drawn from the main pile, capped by empty_draw_limit
    assert len(state.card_deck) == 2


def test_the_mercy_rule_empties_your_own_shelf_before_it_touches_the_pile():
    """Your shelved Wu are already yours. Dealing off the pile while your own deck sits full would be
    paying you for having forgotten about it — and it would drain the pile that ends the run."""
    # A shelf deep enough to cover the whole mercy — so if the pile is touched at all, it is a bug
    player = _player(0, deck=_SETTINGS.empty_draw_limit)
    state = _state(player, _player(3), main=5)

    refill_hands(state, _SETTINGS, rng=Rng(0))

    assert len(player.hand) == _SETTINGS.empty_draw_limit  # every Wu came off the shelf
    assert len(state.card_deck) == 5, "the pile was touched while the shelf still had Wu on it"


def test_the_pile_finishes_what_the_shelf_cannot():
    """The shelf answers first, but it is not required to answer in full."""
    player = _player(0, deck=1)
    state = _state(player, _player(3), main=5)

    refill_hands(state, _SETTINGS, rng=Rng(0))

    assert len(player.hand) == _SETTINGS.empty_draw_limit  # brought up to the mercy limit
    assert player.deck == []
    assert len(state.card_deck) == 3  # the shelf gave one, the pile gave the other two


def test_being_dealt_back_in_spends_the_turn_it_lands_on():
    """The mercy rule is income, and income costs the action — the same one a Draw would have cost.

    Free, it would pay a duelist for running themselves dry: spend the hand, get a new one, and take
    the turn's action on top.
    """
    player = _player(0)  # nothing fieldable — the pile has to deal them back in
    state = _state(player, _player(3), main=5)

    refill_hands(state, _SETTINGS, rng=Rng(0))

    assert player.hand  # they were dealt back in
    assert state.actions_taken == _SETTINGS.actions_per_turn  # and the turn it lands on is spent


def test_a_turn_that_needed_no_mercy_opens_with_its_action_unspent():
    """Guards the test above: the charge must not fall on a duelist who was never dealt back in."""
    state = _state(_player(3), _player(3), main=5)
    state.actions_taken = 1  # last turn's action

    refill_hands(state, _SETTINGS, rng=Rng(0))

    assert state.actions_taken == 0  # a new turn, and it is theirs to spend


def test_refill_flags_the_run_over_at_the_point_limit():
    player = _player(3)
    player.points = 13
    state = _state(player, _player(3))

    refill_hands(state, XiaolinSettings(point_limit=13), rng=Rng(0))

    assert state.has_ended


def test_refill_sheds_an_over_hand_and_leaves_a_short_one():
    state = _state(_player(8), _player(2, deck=4), main=0)

    refill_hands(state, _SETTINGS, rng=Rng(0))

    assert len(state.player.hand) == 6  # shed down to the limit
    assert len(state.bot.hand) == 2  # a short hand is left as-is (no auto-top-up)


def test_a_hard_bot_cashes_its_most_valuable_wu_for_points():
    """The run is won on banked points, so chasing the biggest number is the STRONG play."""
    bot = _player(2)
    bot.hand.append(_card(mechanic=Mechanic.FILLER, points=3))
    state = _state(_player(3), bot, main=5)

    bot_turn(state, _SETTINGS, rng=Rng(1), difficulty=Difficulty.HARD)  # one action a turn

    assert state.bot.points == 3
    assert len(bot.hand) == 2  # the deposited Wu left the hand


def test_an_easy_bot_hoards_its_weapons_and_banks_the_trinket():
    """Clinging to your Wu feels clever and loses: the trinket is 1 point, the weapon was 3."""
    bot = _player(2)
    weapon = _card(points=3)  # 3 pts, but 1/1/1 of duel value
    bot.hand.extend([weapon, _card(points=1, stats=_JUNK)])  # a statless 1-pt trinket

    bot_turn(_state(_player(3), bot, main=5), _SETTINGS, rng=Rng(1), difficulty=Difficulty.EASY)

    assert bot.points == 1  # banked the trinket, kept the weapon — and scored almost nothing
    assert any(card is weapon for card in bot.hand)


def test_an_easy_bot_never_banks_a_booster():
    bot = _player(2)
    booster = _card(mechanic=Mechanic.BOOST, points=3, stats=_JUNK)  # statless but decisive
    bot.hand.extend([booster, _card(points=1, stats=_JUNK)])

    bot_turn(_state(_player(3), bot, main=5), _SETTINGS, rng=Rng(1), difficulty=Difficulty.EASY)

    assert any(card is booster for card in bot.hand)  # the premium keeps it out of the bank


def test_a_bot_passes_when_nothing_in_hand_is_worth_points():
    bot = _player(3)  # every filler card is worth 0 points

    log = bot_turn(_state(_player(3), bot, main=5), _SETTINGS, rng=Rng(1), difficulty=Difficulty.HARD)

    assert bot.points == 0
    assert [move.action for move in log] == [PASSED]


def test_bot_turn_swaps_a_deposit_power_wu_for_a_fresh_draw():
    bot = _player(2)
    power_wu = _card(mechanic=Mechanic.CHRONOKINESIS, points=9)
    bot.hand.append(power_wu)
    state = _state(_player(3), bot, main=5)

    bot_turn(state, _SETTINGS, rng=Rng(1))

    assert all(card is not power_wu for card in bot.hand)  # the power Wu was spent
    assert len(state.card_deck) == 4  # one drawn from the main pile in its place
    assert state.bot.points == 0  # a swap banks no points


def test_bot_turn_stops_at_its_one_action():
    bot = _player(0)
    bot.hand.extend(_card(mechanic=Mechanic.FILLER, points=2) for _ in range(3))
    state = _state(_player(3), bot, main=0)

    bot_turn(state, XiaolinSettings(max_hand_size=6, actions_per_turn=1), rng=Rng(1), difficulty=Difficulty.EASY)

    assert state.bot.points == 2  # only one deposit, though three Wu could be cashed
    assert len(bot.hand) == 2


def test_bot_turn_draws_one_wu_and_pays_its_action_for_it():
    """The rule that binds the player binds the bot: a draw is the turn's action, and buys one Wu.

    It used to top its hand up to the limit for free, every turn, on top of banking. A hand that
    refills itself is not a resource, and a bot that never pays for one is not playing the game the
    player is.
    """
    bot = _player(2, deck=2)  # a thin hand, with cards shelved in its personal deck
    state = _state(_player(3), bot, main=0)

    bot_turn(state, _SETTINGS, rng=Rng(1))

    assert len(bot.hand) == 3  # one Wu, not the whole shelf
    assert len(bot.deck) == 1


def test_bot_turn_reports_what_it_did():
    """Both halves of a move: the action it is filed under, and a line of prose to show for it.

    The prose is not restated here — it is the game's wording and the game may reword it. What must
    hold is that a move always carries one, and that it names the duelist it belonged to.
    """
    idle = _state(_player(3), _player(3))  # nothing to deposit, empty deck
    passed = bot_turn(idle, _SETTINGS, rng=Rng(1))
    assert [move.action for move in passed] == [PASSED]
    assert passed[0].line.startswith("C ")

    banker = _player(2)
    banker.hand.append(_card(mechanic=Mechanic.FILLER, points=3))
    log = bot_turn(_state(_player(3), banker, main=5), _SETTINGS, rng=Rng(1), difficulty=Difficulty.EASY)
    assert any("deposited" in move.line for move in log)
    assert VAULT in [move.action for move in log]


def test_a_bot_never_banks_its_hand_below_the_duel_floor():
    """It has no card income but winning, so an unfloored bot cashes its own bench and ends the run
    holding a single Wu against a full hand. Measured: 5 -> 1.3 Wu over a run, before the floor."""
    bot = _player(0)
    bot.hand.extend(_card(mechanic=Mechanic.FILLER, points=2) for _ in range(DUEL_FLOOR))
    state = _state(_player(3), bot, main=0)

    bot_turn(state, XiaolinSettings(max_hand_size=6, actions_per_turn=9), rng=Rng(1), difficulty=Difficulty.HARD)

    assert len(bot.hand) == DUEL_FLOOR  # it banked nothing: everything it holds, it needs
    assert state.bot.points == 0


def test_a_bot_banks_whatever_sits_above_the_floor():
    """Guards the test above: the floor must not become a reason never to deposit at all."""
    bot = _player(0)
    bot.hand.extend(_card(mechanic=Mechanic.FILLER, points=2) for _ in range(DUEL_FLOOR + 1))
    state = _state(_player(3), bot, main=0)

    bot_turn(state, XiaolinSettings(max_hand_size=6, actions_per_turn=9), rng=Rng(1), difficulty=Difficulty.HARD)

    assert len(bot.hand) == DUEL_FLOOR
    assert state.bot.points == 2  # the one Wu above the floor


# --- the gamble Wu (`deposit`/0): banked for an unknown number of points ---------------


def test_a_gamble_wu_pays_its_roll_not_its_printed_points():
    """Its printed 1 is a polite fiction. What it pays is drawn, and can beat every Wu in the deck."""
    rolls = {bank_value(_card(mechanic=Mechanic.GAMBLE, points=1), Rng(seed)) for seed in range(60)}

    assert rolls - {1}, "every roll came back as the printed points — it is not being rolled at all"
    assert min(rolls) < 0, "it can never cost you anything, so keeping it is not a gamble"
    assert min(rolls) >= GAMBLE_SPREAD[0] and max(rolls) <= GAMBLE_SPREAD[1]


def test_an_ordinary_wu_is_never_rolled():
    """Only the gamble gambles. The rest of the game is open hands."""
    assert {bank_value(_card(mechanic=Mechanic.FILLER, points=3), Rng(seed)) for seed in range(30)} == {3}


def test_a_bad_gamble_never_takes_the_bot_below_zero():
    bot = _player(3)
    bot.hand.append(_card(mechanic=Mechanic.GAMBLE, points=1))
    state = _state(_player(3), bot, main=5)

    for seed in range(40):  # some of these roll negative
        state.bot.points = 0
        state.actions_taken = 0
        bot_turn(state, _SETTINGS, rng=Rng(seed), difficulty=Difficulty.HARD)
        assert state.bot.points >= 0


def test_a_hand_with_nothing_fieldable_is_refilled():
    """A Wu that can only ever be a boost cannot answer a showdown, so a hand of them is empty."""
    player = _player(0)
    player.inalienable_hand.append(_card())  # boost-only: never fielded, staked or lost
    state = _state(player, _player(3), main=5)

    oversee_hand_size(state, is_player=True, settings=_SETTINGS, rng=Rng(1))

    assert player.hand, "left holding only a Wu that cannot be fielded"


def test_the_refill_counts_what_cannot_be_fielded_toward_the_mercy():
    """``empty_draw_limit`` is the hand you are brought up to, not a count of cards dealt."""
    player = _player(0)
    player.inalienable_hand.append(_card())
    state = _state(player, _player(3), main=9)

    oversee_hand_size(state, is_player=True, settings=_SETTINGS, rng=Rng(1))

    assert len(player.whole_hand) == _SETTINGS.empty_draw_limit
    assert len(player.hand) == _SETTINGS.empty_draw_limit - 1  # the boost-only Wu filled a slot


def test_a_wu_that_cannot_be_fielded_still_takes_a_slot_against_the_limit():
    """The other half of the rule: it is not free, it just cannot be played."""
    player = _player(6)  # already at the limit
    player.inalienable_hand.append(_card())
    state = _state(player, _player(3))

    settled = oversee_hand_size(state, is_player=True, settings=_SETTINGS, rng=Rng(1))

    assert not settled, "it did not count against the limit, so nothing was shed"
