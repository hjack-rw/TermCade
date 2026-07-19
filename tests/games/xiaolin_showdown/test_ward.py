"""The ward — a played -phylaxia Wu shields its own element from the arena's drag, never its lift."""

from __future__ import annotations

from xiaolin_showdown.logic.mechanics.scoring import count_end_stats

from factories import wu


def _force(card, background, ward=None):
    return count_end_stats("force", 1, [card], {"force": 0}, background, ward=ward)


def test_the_ward_ignores_the_opposite_arenas_drag():
    card = wu(2, element="wind")
    assert _force(card, "earth") == 1  # dragged: 2 stats − 1 bonus
    assert _force(card, "earth", ward="wind") == 2  # warded: the drag never lands


def test_the_ward_ignores_metals_drag_too():
    card = wu(2, element="wind")
    assert _force(card, "metal", ward="wind") == 2


def test_the_ward_keeps_the_lift():
    card = wu(2, element="wind")
    assert _force(card, "wind", ward="wind") == _force(card, "wind") == 3


def test_the_ward_shields_only_its_own_element():
    bystander = wu(2, element="fire")
    assert _force(bystander, "water", ward="wind") == 1  # still dragged: not the warded colour
