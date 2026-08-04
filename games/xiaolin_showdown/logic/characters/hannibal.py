"""Hannibal Roy Bean's Elemental Deflection — the one piece of him that isn't the shared MORPH
mechanic (``mechanics.powers.Mechanic.MORPH``, which Moby Morpher — an ordinary wudai any duelist
could hold — resolves through the same way).
"""

from __future__ import annotations

from ..mechanics.powers import Mechanic

# Hannibal's Elemental Deflection covers the four elements — never metal, which he cannot deflect.
# Set on both sides in `duel.Duel._ground`.
DEFLECTED_ELEMENTS = frozenset({"water", "fire", "wind", "earth"})

# Hannibal's five named counters (see docs/design/BOSSES.md). Each mechanic maps to exactly one:
# Star Hanabi (NULLIFY_BOOST), Celestial Dial Locket (REVERSE_ELEMENT), Kuzusu Atom (CLEANSE),
# Eye of Dashi (SET_ELEMENT), Monsoon Sandals (SET_ARENA) — verified against the seed.
counter = frozenset(
    {
        Mechanic.NULLIFY_BOOST,
        Mechanic.REVERSE_ELEMENT,
        Mechanic.CLEANSE,
        Mechanic.SET_ELEMENT,
        Mechanic.SET_ARENA,
    }
)
