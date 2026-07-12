"""The Xiaolin Showdown ``Game`` descriptor — how the cartridge plugs into the engine.

Supplies the game's identity, its ``GameState`` class, its default (player-editable)
ruleset as settings, and the root screen the engine boots into.
"""

from __future__ import annotations

from pathlib import Path

from termcade.app.game import Game

from .logic.settings import default_settings
from .logic.state import XiaolinState
from .music import XIAOLIN
from .screens.start import StartScreen

THEME = Path(__file__).resolve().parent / "theme" / "xiaolin.tcss"


def build_game() -> Game:
    return Game(
        game_id="xiaolin_showdown",
        title="Xiaolin Showdown",
        version="1.2",
        state_cls=XiaolinState,
        default_settings=default_settings(),
        saves_enabled=True,
        max_slots=4,
        root_screen=StartScreen,
        theme_paths=[THEME],
        music_style=XIAOLIN,
        # No floor. Every screen scrolls once its content outgrows the window (Textual's `Screen`
        # defaults to `overflow-y: auto`), verified reachable down to 60x14 — so a "too small"
        # overlay would only ever hide a board the player can already scroll. Zooming in past the
        # fit is a choice, not an error.
        min_size=None,
        # The browser sizes its font to fit this grid, so it must cover the *tallest* screen, not
        # the board: the start menu (banner + wordmark + 5 buttons) measures 42 rows, the vault 30.
        fit_size=(110, 44),
    )
