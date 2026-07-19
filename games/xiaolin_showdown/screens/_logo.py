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
# FULLWIDTH forms (U+FF21..U+FF3A) + an ideographic space (U+3000): a terminal has one font size, so
# the only way a single row reads BIGGER is glyphs that occupy two cells each. That doubles the
# wordmark's width to sit under the title without costing a second row.
SUBTITLE_ART = "ＴＨＥ　ＦＡＮＧＡＭＥ"
