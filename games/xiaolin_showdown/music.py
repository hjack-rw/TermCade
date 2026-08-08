"""The rules Xiaolin's soundtrack is composed under — slower and pentatonic, where the cabinet
itself is brisk and minor.

Yu pentatonic scale (no semitones) so a seeded, unheard melody can't land on a clashing note — only
a different one. Quartal chords (fourths/fifths, no thirds) keep the harmony open rather than reading
as Western major/minor.
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

# Only the tempo moves — same scale, progressions and roots, rendered off the same seed. Changing
# anything else here breaks the "same temple, faster" effect.
XIAOLIN_BOSS = Style(
    scale=XIAOLIN.scale,
    progressions=XIAOLIN.progressions,
    roots_hz=XIAOLIN.roots_hz,
    bpm_range=(126, 146),
)

# The outcome screen's pair: same melody, same seed, played under different rules. The win fanfare
# (see `music.VICTORY`) is a sting on top of this, not instead of it — this is what keeps playing
# once the sting has finished ringing out.
XIAOLIN_VICTORY = Style(
    scale=XIAOLIN.scale,
    progressions=XIAOLIN.progressions,
    roots_hz=tuple(hz * 2 for hz in XIAOLIN.roots_hz),
    bpm_range=(104, 120),
)
# A run running out: same melody, same seed, dropped an octave and dragging. The bass follows the
# root down there too, low enough that it would otherwise eat the mix's headroom (see `Style.
# bass_gain`) — pulled back so the drag reads as tempo, not as one voice drowning the rest.
XIAOLIN_DEFEAT = Style(
    scale=XIAOLIN.scale,
    progressions=XIAOLIN.progressions,
    roots_hz=tuple(hz / 2 for hz in XIAOLIN.roots_hz),
    bpm_range=(56, 68),
    bass_gain=0.55,
)
