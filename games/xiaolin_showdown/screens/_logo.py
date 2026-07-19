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
