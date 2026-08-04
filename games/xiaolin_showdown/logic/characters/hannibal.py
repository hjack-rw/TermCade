"""Hannibal Roy Bean's Elemental Deflection — the one piece of him that isn't the shared MORPH
mechanic (``mechanics.powers.Mechanic.MORPH``, which Moby Morpher — an ordinary wudai any duelist
could hold — resolves through the same way).
"""

from __future__ import annotations

from ..mechanics.powers import Mechanic

# Hannibal's Elemental Deflection covers the four elements — never metal, which he cannot deflect.
# Two halves: his own Wu of these ignore the arena's DRAG (-1 -> 0, the lift kept), and the foe's Wu
# of these lose their arena LIFT (+1 -> 0). Set on both sides in `duel.Duel._ground`.
DEFLECTED_ELEMENTS = frozenset({"water", "fire", "wind", "earth"})

# Hannibal's own five, measured (see docs/design/BOSSES.md): alone each is weak (Star Hanabi's
# boost-negate: 6.7%), but the full set held every showdown takes him 0.7% -> 49%. Every mechanic
# maps to exactly one of his five named counters — Star Hanabi (NULLIFY_BOOST), Celestial Dial
# Locket (REVERSE_ELEMENT), Kuzusu Atom (CLEANSE), Eye of Dashi (SET_ELEMENT), Monsoon Sandals
# (SET_ARENA) — verified against the seed, not guessed.
counter = frozenset(
    {
        Mechanic.NULLIFY_BOOST,
        Mechanic.REVERSE_ELEMENT,
        Mechanic.CLEANSE,
        Mechanic.SET_ELEMENT,
        Mechanic.SET_ARENA,
    }
)
