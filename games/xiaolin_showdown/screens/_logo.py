"""ASCII wordmarks for the start screen — generated once with pyfiglet (font "cybermedium").

Embedded as constants so the game carries no runtime figlet dependency, the same way the engine's
TERMCADE ``BANNER`` is a baked-in string. Raw strings: the glyphs use literal backslashes."""

TITLE_ART = r"""_  _ _ ____ ____ _    _ _  _    ____ _  _ ____ _ _ _ ___  ____ _ _ _ _  _
 \/  | |__| |  | |    | |\ |    [__  |__| |  | | | | |  \ |  | | | | |\ |
_/\_ | |  | |__| |___ | | \|    ___] |  | |__| |_|_| |__/ |__| |_|_| | \|"""

SUBTITLE_ART = r"""___ _  _ ____    ____ ____ _  _ ____ ____ _  _ ____
 |  |__| |___    |___ |__| |\ | | __ |__| |\/| |___
 |  |  | |___    |    |  | | \| |__] |  | |  | |___"""
