"""Sun Chi Lantern — Metempsychosis swaps the two hands entirely; the wudai slot never moves."""

from __future__ import annotations

from xiaolin_showdown.logic.actions import use_power
from xiaolin_showdown.logic.models import Mechanic
from xiaolin_showdown.logic.state import XiaolinState

from factories import duelist, wu


def _state_with_lantern() -> tuple[XiaolinState, object]:
    lantern = wu(0, 0, 0, mechanic=Mechanic.METEMPSYCHOSIS, name="Lantern", points=5)
    player = duelist(hand=[lantern, wu(1, name="Mine")])
    bot = duelist(hand=[wu(2, name="Theirs A"), wu(3, name="Theirs B")])
    return XiaolinState(catalog=None, player=player, bot=bot, card_deck=[]), lantern  # type: ignore[arg-type]


def test_the_lantern_swaps_the_two_hands():
    state, lantern = _state_with_lantern()
    use_power(state, lantern)
    assert [c.name for c in state.player.hand] == ["Theirs A", "Theirs B"]
    assert [c.name for c in state.bot.hand] == ["Mine"]


def test_the_spent_lantern_crosses_to_nobody():
    state, lantern = _state_with_lantern()
    use_power(state, lantern)
    assert all(c.name != "Lantern" for c in state.player.hand + state.bot.hand)
    assert state.actions_taken == 1


def test_the_wudai_slot_sits_out_the_swap():
    state, lantern = _state_with_lantern()
    dragon = wu(0, name="Wudai")
    state.player.inalienable_hand.append(dragon)
    use_power(state, lantern)
    assert state.player.inalienable_hand == [dragon]


def test_wear_crosses_by_the_hand_over_rule():
    state, lantern = _state_with_lantern()
    state.bot.hand[0].uses = 2  # worn twice by the opponent
    use_power(state, lantern)
    taken = next(c for c in state.player.hand if c.name == "Theirs A")
    assert taken.uses == 0 and taken.uses_memory == 2  # fresh for you; their count pocketed


def test_the_bot_spends_the_lantern_only_from_behind():
    from xiaolin_showdown.logic.settings import XiaolinSettings
    from xiaolin_showdown.logic.temple_ai import choose_temple_power

    lantern = wu(0, 0, 0, mechanic=Mechanic.METEMPSYCHOSIS, name="Lantern", points=5)
    behind = XiaolinState(  # type: ignore[arg-type]
        catalog=None, player=duelist(hand=[wu(5, 5, 5)]), bot=duelist(hand=[lantern]), card_deck=[]
    )
    play = choose_temple_power(behind, XiaolinSettings())
    assert play is not None and play.card is lantern

    level = XiaolinState(  # type: ignore[arg-type]
        catalog=None, player=duelist(hand=[wu(2)]), bot=duelist(hand=[lantern, wu(2)]), card_deck=[]
    )
    assert choose_temple_power(level, XiaolinSettings()) is None


def test_the_bot_leaves_a_near_worn_wu_to_bank_itself():
    from termcade.core.settings import Difficulty
    from xiaolin_showdown.logic.constants import WEAR_LIMIT
    from xiaolin_showdown.logic.turn import pick_deposit

    worn = wu(1, points=3)
    worn.uses = WEAR_LIMIT - 1
    fresh = wu(1, points=2)
    assert pick_deposit([worn, fresh], Difficulty.HARD) is fresh


def test_a_background_is_still_picked_against_an_empty_hand():
    # Wear vaults and the Lantern made empty hands reachable mid-run; the background pick must not
    # read a lead card that is not there.
    from termcade.core.rng import Rng
    from xiaolin_showdown.logic.bot import choose_background

    stats = {"force": 1, "agility": 1, "intellect": 1}
    assert choose_background(stats, ["fire", "water"], ([], []), stats, Rng(0)) in ("fire", "water")


def test_an_empty_opposing_hand_fizzles_the_swap():
    lantern = wu(0, 0, 0, mechanic=Mechanic.METEMPSYCHOSIS, name="Lantern")
    state = XiaolinState(  # type: ignore[arg-type]
        catalog=None, player=duelist(hand=[lantern, wu(1, name="Mine")]), bot=duelist(), card_deck=[]
    )
    use_power(state, lantern)
    assert [c.name for c in state.player.hand] == ["Mine"]  # nothing swapped, the Wu still spent
