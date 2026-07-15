"""Typography rules for terminal text — the ones a proportional-font habit gets wrong.

A terminal is not a page. Type set for a page and it comes out looking broken here, in ways that are
invisible until somebody screenshots them at you.
"""

from __future__ import annotations

EM_DASH = "—"

# The em dash is drawn a FULL CELL WIDE in most terminal fonts, and it fills that cell edge to edge —
# so the space after it visually disappears and "power — spent" reads as "power —spent". The text is
# correct; the glyph is greedy. A second space is what puts the gap back, and it costs one column.
DASH_GAP = "  "


def spaced_dashes(text: str) -> str:
    """Give every em dash room to breathe: a space before, and *two* after.

    Not a preference. In the game's font the dash glyph eats the single space that follows it, and a
    line reading ``clear me | clear them —empty a hand`` looks like a typo the reader has to forgive.
    Applied at *render* time so the source strings stay readable prose — nobody should be typing double
    spaces into a sentence to work around a font.
    """
    parts = [part.strip() for part in text.split(EM_DASH)]
    spaced = f" {EM_DASH}{DASH_GAP}".join(parts)
    # A line that BEGINS with a dash gets no space in front of it — there is nothing to separate it
    # from, and the stray column would indent that line alone. (A wrapped paragraph can break exactly
    # there, so this is not a hypothetical.)
    return spaced if text[:1].isspace() else spaced.lstrip(" ")
