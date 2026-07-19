"""The wear rule — "Three Times in a Row": the third showdown a Wu is committed to vaults it."""

from __future__ import annotations

from termcade.core.rng import Rng

from xiaolin_showdown.logic.state import XiaolinState
from xiaolin_showdown.logic.wear import WEAR_LIMIT, hand_over, record_showdown

from factories import duelist, wu


def test_a_committed_wu_wears_by_one():
    player = duelist(hand=[wu(1, name="Sword")])
    record_showdown(player, [player.hand[0]], rng=Rng(0))
    assert player.hand[0].uses == 1


def test_a_wu_sitting_in_the_hand_never_wears():
    player = duelist(hand=[wu(1, name="Sword"), wu(1, name="Shield")])
    record_showdown(player, [player.hand[0]], rng=Rng(0))
    assert player.hand[1].uses == 0


def test_the_last_showdown_vaults_the_wu_for_its_points():
    worn = wu(1, name="Sword", points=3)
    worn.uses = WEAR_LIMIT - 1
    player = duelist(hand=[worn, wu(1)])
    vaulted = record_showdown(player, [worn], rng=Rng(0))
    assert [(card.name, paid) for card, paid in vaulted] == [("Sword", 3)]
    assert worn not in player.hand and player.points == 3


def test_vaulting_by_wear_spends_no_action():
    worn = wu(1, points=2)
    worn.uses = WEAR_LIMIT - 1
    state = XiaolinState(catalog=None, player=duelist(hand=[worn]), bot=duelist(), card_deck=[])  # type: ignore[arg-type]
    record_showdown(state.player, [worn], rng=Rng(0))
    assert state.actions_taken == 0


def test_a_wu_changing_hands_arrives_fresh():
    card = wu(1)
    card.uses = WEAR_LIMIT - 1
    assert hand_over(card).uses == 0


def test_winning_a_wu_back_resumes_the_old_count():
    card = wu(1)
    card.uses = 2  # worn twice by its first owner
    hand_over(card)  # lost to the opponent — fresh for them
    card.uses += 1  # the opponent wears it once
    hand_over(card)  # won back
    assert card.uses == 2  # the first owner resumes
    assert card.uses_memory == 1  # and the opponent's count waits in the pocket


def test_a_wu_the_showdown_took_away_does_not_wear_for_its_old_owner():
    # The loser's staked Wu moved to the winner before the count — absent from the hand, no wear.
    lost_card = wu(1, name="Taken")
    player = duelist(hand=[])
    record_showdown(player, [lost_card], rng=Rng(0))
    assert lost_card.uses == 0


def test_the_inalienable_wudai_never_wears():
    player = duelist(hand=[])
    dragon = wu(0, name="Wudai")
    player.inalienable_hand.append(dragon)
    record_showdown(player, [dragon], rng=Rng(0))
    assert dragon.uses == 0 and dragon in player.inalienable_hand


def test_a_save_keeps_the_wear(state):
    state.player.hand[0].uses = WEAR_LIMIT - 1
    state.player.hand[0].uses_memory = 1
    restored = XiaolinState.restore(state.snapshot(), None)
    assert restored.player.hand[0].uses == WEAR_LIMIT - 1
    assert restored.player.hand[0].uses_memory == 1
