"""The vault turn — hand-size upkeep between showdowns (`oversee_hand_size` / `refill_hands`).

Pure and TTY-free: small hand-crafted states are balanced directly, no catalog or screen needed.
This is the loop terminator, so the emphasis is the draw/discard edges that keep a hand playable.
"""

from __future__ import annotations

from termcade.core.rng import Rng
from termcade.core.settings import Difficulty

from xiaolin_showdown.logic.models import Card, Character, Player, Power
from xiaolin_showdown.logic.settings import XiaolinSettings
from xiaolin_showdown.logic.state import XiaolinState
from xiaolin_showdown.logic.mechanics.powers import GAMBLE_SPREAD
from xiaolin_showdown.logic.turn import DUEL_FLOOR, bank_value, bot_turn, max_hand_size, oversee_hand_size, refill_hands


def _card(*, trigger="hand", effect=0, points=0, stats=None) -> Card:
    stats = {"force": 1, "agility": 1, "intellect": 1} if stats is None else stats
    return Card(0, "Wu", stats, Power(0, "", trigger, effect, ""), "metal", "item", points)


_JUNK = {"force": 0, "agility": 0, "intellect": 0}  # no duel value — a hard bot banks this first


def _player(hand: int, *, deck: int = 0) -> Player:
    character = Character(0, "C", {"force": 0, "agility": 0, "intellect": 0}, _card().power, "xiaolin", True)
    return Player(character=character, hand=[_card() for _ in range(hand)], deck=[_card() for _ in range(deck)])


def _state(player: Player, bot: Player, *, main: int = 0) -> XiaolinState:
    return XiaolinState(catalog=None, player=player, bot=bot, card_deck=[_card() for _ in range(main)])  # type: ignore[arg-type]


_SETTINGS = XiaolinSettings(max_hand_size=6, draw_limit=1, empty_draw_limit=3)


def test_max_hand_size_grows_by_one_with_a_third_arm_sash():
    assert max_hand_size(_player(3), 6) == 6
    sashed = _player(2)
    sashed.hand.append(_card(trigger="hand", effect=-1))  # the Third-Arm Sash
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
    assert state.draw_counter == 0


def test_an_empty_hand_is_refilled_from_the_main_pile():
    player = _player(0)  # empty hand, empty personal deck
    state = _state(player, _player(3), main=5)

    oversee_hand_size(state, is_player=True, settings=_SETTINGS, rng=Rng(0))

    assert len(player.hand) == 3  # emergency-drawn from the main pile, capped by empty_draw_limit
    assert len(state.card_deck) == 2


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
    bot.hand.append(_card(trigger="none", effect=0, points=3))
    state = _state(_player(3), bot, main=5)

    bot_turn(state, _SETTINGS, rng=Rng(1), difficulty=Difficulty.HARD)  # deposit_limit is 1

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
    booster = _card(trigger="boost", effect=1, points=3, stats=_JUNK)  # statless but decisive
    bot.hand.extend([booster, _card(points=1, stats=_JUNK)])

    bot_turn(_state(_player(3), bot, main=5), _SETTINGS, rng=Rng(1), difficulty=Difficulty.EASY)

    assert any(card is booster for card in bot.hand)  # the premium keeps it out of the bank


def test_a_bot_passes_when_nothing_in_hand_is_worth_points():
    bot = _player(3)  # every filler card is worth 0 points

    log = bot_turn(_state(_player(3), bot, main=5), _SETTINGS, rng=Rng(1), difficulty=Difficulty.HARD)

    assert bot.points == 0
    assert log == ["C passed"]


def test_bot_turn_swaps_a_deposit_power_wu_for_a_fresh_draw():
    bot = _player(2)
    power_wu = _card(trigger="use", effect=1, points=9)
    bot.hand.append(power_wu)
    state = _state(_player(3), bot, main=5)

    bot_turn(state, _SETTINGS, rng=Rng(1))

    assert all(card is not power_wu for card in bot.hand)  # the power Wu was spent
    assert len(state.card_deck) == 4  # one drawn from the main pile in its place
    assert state.bot.points == 0  # a swap banks no points


def test_bot_turn_stops_at_the_deposit_limit():
    bot = _player(0)
    bot.hand.extend(_card(trigger="none", effect=0, points=2) for _ in range(3))
    state = _state(_player(3), bot, main=0)

    bot_turn(state, XiaolinSettings(max_hand_size=6, deposit_limit=1), rng=Rng(1), difficulty=Difficulty.EASY)

    assert state.bot.points == 2  # only one deposit, though three Wu could be cashed
    assert len(bot.hand) == 2


def test_bot_turn_fills_its_hand_from_its_own_deck():
    """To the limit, not one card at a time — a duelist sitting on a deck it could be holding is
    simply not playing the game."""
    bot = _player(2, deck=2)  # under the limit, with cards shelved in its personal deck
    state = _state(_player(3), bot, main=0)

    bot_turn(state, _SETTINGS, rng=Rng(1))  # nothing to deposit — it just tops up (it has no manual Draw)

    assert len(bot.hand) == 4
    assert bot.deck == []


def test_bot_turn_reports_what_it_did():
    idle = _state(_player(3), _player(3))  # nothing to deposit, empty deck
    assert bot_turn(idle, _SETTINGS, rng=Rng(1)) == ["C passed"]

    banker = _player(2)
    banker.hand.append(_card(trigger="none", effect=0, points=3))
    log = bot_turn(_state(_player(3), banker, main=5), _SETTINGS, rng=Rng(1), difficulty=Difficulty.EASY)
    assert any("deposited" in line for line in log)


def test_a_bot_never_banks_its_hand_below_the_duel_floor():
    """It has no card income but winning, so an unfloored bot cashes its own bench and ends the run
    holding a single Wu against a full hand. Measured: 5 -> 1.3 Wu over a run, before the floor."""
    bot = _player(0)
    bot.hand.extend(_card(trigger="none", effect=0, points=2) for _ in range(DUEL_FLOOR))
    state = _state(_player(3), bot, main=0)

    bot_turn(state, XiaolinSettings(max_hand_size=6, deposit_limit=9), rng=Rng(1), difficulty=Difficulty.HARD)

    assert len(bot.hand) == DUEL_FLOOR  # it banked nothing: everything it holds, it needs
    assert state.bot.points == 0


def test_a_bot_banks_whatever_sits_above_the_floor():
    """Guards the test above: the floor must not become a reason never to deposit at all."""
    bot = _player(0)
    bot.hand.extend(_card(trigger="none", effect=0, points=2) for _ in range(DUEL_FLOOR + 1))
    state = _state(_player(3), bot, main=0)

    bot_turn(state, XiaolinSettings(max_hand_size=6, deposit_limit=9), rng=Rng(1), difficulty=Difficulty.HARD)

    assert len(bot.hand) == DUEL_FLOOR
    assert state.bot.points == 2  # the one Wu above the floor


# --- the gamble Wu (`deposit`/0): banked for an unknown number of points ---------------


def test_a_gamble_wu_pays_its_roll_not_its_printed_points():
    """Its printed 1 is a polite fiction. What it pays is drawn, and can beat every Wu in the deck."""
    rolls = {bank_value(_card(trigger="use", effect=0, points=1), Rng(seed)) for seed in range(60)}

    assert rolls - {1}, "every roll came back as the printed points — it is not being rolled at all"
    assert min(rolls) < 0, "it can never cost you anything, so keeping it is not a gamble"
    assert min(rolls) >= GAMBLE_SPREAD[0] and max(rolls) <= GAMBLE_SPREAD[1]


def test_an_ordinary_wu_is_never_rolled():
    """Only the gamble gambles. The rest of the game is open hands."""
    assert {bank_value(_card(trigger="none", points=3), Rng(seed)) for seed in range(30)} == {3}


def test_a_bad_gamble_never_takes_the_bot_below_zero():
    bot = _player(3)
    bot.hand.append(_card(trigger="use", effect=0, points=1))
    state = _state(_player(3), bot, main=5)

    for seed in range(40):  # some of these roll negative
        state.bot.points = 0
        state.deposit_counter = 0
        bot_turn(state, _SETTINGS, rng=Rng(seed), difficulty=Difficulty.HARD)
        assert state.bot.points >= 0
