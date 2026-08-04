"""ASCII wordmarks for the start screen — generated once with pyfiglet (font "cybermedium").

Embedded as constants so the game carries no runtime figlet dependency. Raw strings: the glyphs use
literal backslashes."""

TITLE_ART = r"""
_  _ _ ____ ____ _    _ _  _    ____ _  _ ____ _ _ _ ___  ____ _ _ _ _  _
 \/  | |__| |  | |    | |\ |    [__  |__| |  | | | | |  \ |  | | | | |\ |
_/\_ | |  | |__| |___ | | \|    ___] |  | |__| |_|_| |__/ |__| |_|_| | \|
"""

# Plain ASCII, letter-spaced, not fullwidth: the bundled 0xProto covers neither the fullwidth forms
# (U+FF21..) nor U+3000, so those fall back to tofu wherever the system has nothing to lend.
SUBTITLE_ART = "T H E   F A N G A M E"

# Stacked wordmark for a screen too narrow for one line. TITLE_ART is 73 columns: survives a 390px
# phone with eight to spare, runs off a smaller one entirely.
#
# XIAOLIN is 28 columns and SHOWDOWN is 41, so the first word is INDENTED BY SIX to sit centred over
# the second. The indent is baked into the art rather than left to the stylesheet: an auto-width
# widget (needed so the Center wrapper can place it) centres the block, not each line within it, so
# `text-align: center` alone would leave the lines ragged. Six is (41 - 28) / 2, correct only for
# these two words.
TITLE_ART_STACKED = r"""
      _  _ _ ____ ____ _    _ _  _
       \/  | |__| |  | |    | |\ |
      _/\_ | |  | |__| |___ | | \|
____ _  _ ____ _ _ _ ___  ____ _ _ _ _  _
[__  |__| |  | | | | |  \ |  | | | | |\ |
___] |  | |__| |_|_| |__/ |__| |_|_| | \|
"""
