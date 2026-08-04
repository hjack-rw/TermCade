"""ASCII wordmarks for the start screen — generated once with pyfiglet (font "cybermedium").

Embedded as constants so the game carries no runtime figlet dependency, the same way the engine's
TERMCADE ``BANNER`` is a baked-in string. Raw strings: the glyphs use literal backslashes."""

TITLE_ART = r"""
_  _ _ ____ ____ _    _ _  _    ____ _  _ ____ _ _ _ ___  ____ _ _ _ _  _
 \/  | |__| |  | |    | |\ |    [__  |__| |  | | | | |  \ |  | | | | |\ |
_/\_ | |  | |__| |___ | | \|    ___] |  | |__| |_|_| |__/ |__| |_|_| | \|
"""

# One row, not a figlet block: the subtitle only has to read as a subtitle, and the four rows it used
# to spend are the room the menu needs to grow by a button.
#
# Plain ASCII, letter-spaced. Fullwidth forms (U+FF21..) were tried to make the row read bigger and
# reverted: the bundled 0xProto covers neither them nor U+3000, so the game's own title fell back to
# tofu wherever the system had nothing to lend. The icons already spend that budget; the title is the
# last thing that should gamble on a glyph.
SUBTITLE_ART = "T H E   F A N G A M E"

# The same wordmark stacked, for a screen too narrow for one line of it. TITLE_ART is 73 columns:
# it survives a 390px phone with eight to spare and runs off a smaller one entirely.
#
# Same font, broken at the word — not a smaller font and not plain text. Dropping to letter-spaced
# ASCII was tried and it flattened the start screen; the wordmark is the reason the first thing a
# player sees looks like a cabinet rather than a menu, so it keeps its figure font and spends rows
# instead of columns.
# XIAOLIN is 28 columns and SHOWDOWN is 41, so the first word is INDENTED BY SIX to sit centred over
# the second. The indent is baked into the art rather than left to the stylesheet: `text-align:
# center` centres each line of a block independently, which is the same thing here, but a widget
# that is auto-width — as this one is, so the Center wrapper can place it — centres the block and
# leaves its lines ragged inside. Six is (41 - 28) / 2, and it is only correct for these two words.
TITLE_ART_STACKED = r"""
      _  _ _ ____ ____ _    _ _  _
       \/  | |__| |  | |    | |\ |
      _/\_ | |  | |__| |___ | | \|
____ _  _ ____ _ _ _ ___  ____ _ _ _ _  _
[__  |__| |  | | | | |  \ |  | | | | |\ |
___] |  | |__| |_|_| |__/ |__| |_|_| | \|
"""
