"""The Xiaolin Showdown ``Game`` descriptor — how the cartridge plugs into the engine.

Supplies the game's identity, its ``GameState`` class, its default (player-editable)
ruleset as settings, and the root screen the engine boots into.
"""

from __future__ import annotations

from pathlib import Path

from termcade.app.game import Game

from .logic.settings import default_settings
from .logic.state import XiaolinState
from .screens.start import StartScreen

THEME = Path(__file__).resolve().parent / "theme" / "xiaolin.tcss"


def build_game() -> Game:
    return Game(
        game_id="xiaolin_showdown",
        title="Xiaolin Showdown",
        state_cls=XiaolinState,
        default_settings=default_settings(),
        saves_enabled=True,
        max_slots=6,
        root_screen=StartScreen,
        theme_paths=[THEME],
    )
