"""Hannibal — Elemental Manipulation: he wields the Morpher, and he deflects the elements.

Elemental Deflection has two halves, both on the four elements only (never metal, which he cannot
deflect): his OWN Wu ignore the arena's drag (a ward), and the FOE's Wu lose their arena lift.
"""

from xiaolin_showdown.logic.characters.hannibal import DEFLECTED_ELEMENTS
from xiaolin_showdown.logic.mechanics.scoring import count_end_stats
from xiaolin_showdown.screens.display.duel_board import _played_stats_text

from factories import wu

NO_BASE = {"force": 0, "agility": 0, "intellect": 0}


def _his_value(card, background, *, deflect):
    """Hannibal's own end value: his elements ward off the arena's drag when Deflection is live."""
    return count_end_stats(
        "force", 1, [card], NO_BASE, background,
        earns_bonus=[card], ward=DEFLECTED_ELEMENTS if deflect else (),
    )


def _foe_value(card, background, *, deflect):
    """The player's end value against Hannibal: their elemental lift is turned aside."""
    return count_end_stats(
        "force", 1, [card], NO_BASE, background,
        earns_bonus=[card], deflect_lift=DEFLECTED_ELEMENTS if deflect else (),
    )


def test_his_own_element_wu_shrug_off_the_arena_drag():
    fire = wu(force=2, element="fire")  # dragged −1 in a water arena
    assert _his_value(fire, "water", deflect=False) == 2 - 1
    assert _his_value(fire, "water", deflect=True) == 2  # drag warded away, lift he'd keep anyway


def test_the_foes_element_lift_is_turned_aside():
    fire = wu(force=2, element="fire")  # resonant +1 in a fire arena — the foe's attack
    assert _foe_value(fire, "fire", deflect=False) == 2 + 1
    assert _foe_value(fire, "fire", deflect=True) == 2  # lift deflected to 0


def test_earth_is_covered_alongside_water_fire_wind():
    earth = wu(force=2, element="earth")
    assert _his_value(earth, "wind", deflect=True) == 2          # his earth Wu keep full value
    assert _foe_value(earth, "earth", deflect=True) == 2         # the foe's earth lift is gone


def test_metal_he_cannot_deflect_either_way():
    metal = wu(force=2, element="metal")
    # his metal Wu still eat the drag, and a foe's metal lift still lands — metal is never in the set
    assert _his_value(metal, "fire", deflect=True) == _his_value(metal, "fire", deflect=False) == 2 - 1
    assert _foe_value(metal, "metal", deflect=True) == _foe_value(metal, "metal", deflect=False) == 2 + 1


def _struck(card, background, deflect):
    """Does the board strike the printed value (a shift shown), reading the ⌞ that parts the two?"""
    return "⌞" in _played_stats_text(card, "force", background, 1, deflect).plain


def test_the_board_does_not_strike_a_deflected_foe_lift():
    fire = wu(force=1, element="fire")  # +1 lift in a fire arena — struck to 2, unless deflected
    assert _struck(fire, "fire", None)
    assert not _struck(fire, "fire", "lift")


def test_the_board_does_not_strike_hannibals_warded_drag():
    fire = wu(force=1, element="fire")  # −1 drag in a water arena — struck to 0, unless warded
    assert _struck(fire, "water", None)
    assert not _struck(fire, "water", "ward")
