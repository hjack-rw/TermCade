"""The rules Xiaolin's soundtrack is composed under. Slower and pentatonic, where the cabinet
itself is brisk and minor.

Two changes carry the whole sound, and they work together:

**Yu pentatonic** — the minor five-note scale. It has no semitones in it at all, so no two notes
in the game's vocabulary can clash the way a minor second does. The engine's promise is that an
unheard seed cannot produce a wrong note, only a different one; on this scale that promise costs
nothing to keep, because there is no wrong note left to play.

**Quartal chords** — fourths and fifths, no thirds. The third is the interval that tells an ear
"major" or "minor", and with it the harmony reads as Western however exotic the melody on top.
Take it out and the chords go open and modal, and the pentatonic line above them stops sounding
like a Western tune wearing a costume.
"""

from __future__ import annotations

from termcade.core.music import Style

XIAOLIN = Style(
    # Yu mode: root, minor third, fourth, fifth, minor seventh.
    scale=(0, 3, 5, 7, 10),
    progressions=(
        ((0, 7, 12), (3, 10, 15), (5, 12, 17), (0, 7, 12)),
        ((0, 7, 12), (5, 12, 17), (10, 17, 22), (0, 7, 12)),
        ((0, 7, 12), (10, 17, 22), (3, 10, 15), (5, 12, 17)),
    ),
    roots_hz=(174.6, 196.0, 220.0),  # F3, G3, A3 — a shade below the cabinet's, which sits brighter
    # Well under the cabinet's floor of 120. The temple, not the arcade.
    bpm_range=(80, 100),
)
