"""The temple hand is shown slot-ordered (screens/format._by_slot).

Two rules ride on that order: an assembling Mala Mala Jong set reads down the body head-to-boots (a
missing part is a visible gap), and within the wudai slot the elemental dragon weapons always outrank
the metal Shimo Staff — metal is favoured on no arena, so the dragons read first.
"""

from __future__ import annotations

from factories import wu

from xiaolin_showdown.screens.format import _by_slot


def test_the_hand_shows_wudai_first_then_the_body_head_to_boots():
    hand = [
        wu(type="item", name="a"),
        wu(type="boots", name="b"),
        wu(type="head", name="c"),
        wu(type="wudai", element="water", name="d"),
    ]
    assert [c.type for c in sorted(hand, key=_by_slot)] == ["wudai", "head", "boots", "item"]


def test_elemental_dragon_wudai_outrank_the_metal_shimo_staff():
    shimo = wu(type="wudai", element="metal", name="Shimo Staff")
    dragon = wu(type="wudai", element="water", name="Silver Manta Ray")
    assert sorted([shimo, dragon], key=_by_slot) == [dragon, shimo]  # the elemental dragon leads


def test_the_metal_wudai_sinks_below_every_elemental_dragon():
    shimo = wu(type="wudai", element="metal", name="AAA Shimo")  # name-first would put it top
    dragons = [wu(type="wudai", element=e, name=f"z{e}") for e in ("water", "fire", "wind", "earth")]
    ordered = sorted([shimo, *dragons], key=_by_slot)
    assert ordered[-1] is shimo  # last despite the alphabetically-first name — element wins over name
