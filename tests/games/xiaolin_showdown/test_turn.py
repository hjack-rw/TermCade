"""The vault turn — hand-size upkeep between showdowns (`oversee_hand_size` / `refill_hands`).

Pure and TTY-free: small hand-crafted states are balanced directly, no catalog or screen needed.
This is the loop terminator, so the emphasis is the draw/discard edges that keep a hand playable.
"""

from __future__ import annotations

from termcade.core.rng import Rng

from xiaolin_showdown.logic.models import Card, Character, Player, Power
from xiaolin_showdown.logic.settings import XiaolinSettings
from xiaolin_showdown.logic.state import XiaolinState
from xiaolin_showdown.logic.turn import bot_turn, max_hand_size, oversee_hand_size, refill_hands


def _card(*, trigger="hand", effect=0, points=0) -> Card:
    stats = {"force": 1, "agility": 1, "intellect": 1}
    return Card(0, "Wu", stats, Power(0, "", trigger, effect, ""), "metal", "item", points)


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


def test_bot_turn_cashes_a_deposit_wu_for_points():
    bot = _player(2)
    bot.hand.append(_card(trigger="deposit", effect=0, points=3))
    state = _state(_player(3), bot, main=5)

    bot_turn(state, _SETTINGS)  # deposit_limit is 1

    assert state.bot.points == 3
    assert len(bot.hand) == 2  # the deposited Wu left the hand


def test_bot_turn_swaps_a_deposit_power_wu_for_a_fresh_draw():
    bot = _player(2)
    power_wu = _card(trigger="deposit", effect=1, points=9)
    bot.hand.append(power_wu)
    state = _state(_player(3), bot, main=5)

    bot_turn(state, _SETTINGS)

    assert all(card is not power_wu for card in bot.hand)  # the power Wu was spent
    assert len(state.card_deck) == 4  # one drawn from the main pile in its place
    assert state.bot.points == 0  # a swap banks no points


def test_bot_turn_stops_at_the_deposit_limit():
    bot = _player(0)
    bot.hand.extend(_card(trigger="deposit", effect=0, points=2) for _ in range(3))
    state = _state(_player(3), bot, main=0)

    bot_turn(state, XiaolinSettings(max_hand_size=6, deposit_limit=1))

    assert state.bot.points == 2  # only one deposit, though three Wu could be cashed
    assert len(bot.hand) == 2


def test_bot_turn_recovers_one_card_from_its_own_deck():
    bot = _player(2, deck=2)  # under the limit, with cards shelved in its personal deck
    state = _state(_player(3), bot, main=0)

    bot_turn(state, _SETTINGS)  # nothing to deposit — it just tops up (it has no manual Draw)

    assert len(bot.hand) == 3
    assert len(bot.deck) == 1


def test_bot_turn_reports_what_it_did():
    idle = _state(_player(3), _player(3))  # nothing to deposit, empty deck
    assert bot_turn(idle, _SETTINGS) == ["C passed"]

    banker = _player(2)
    banker.hand.append(_card(trigger="deposit", effect=0, points=3))
    log = bot_turn(_state(_player(3), banker, main=5), _SETTINGS)
    assert any("deposited" in line for line in log)
