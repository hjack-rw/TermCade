"""The Xiaolin Showdown ``Game`` descriptor — how the cartridge plugs into the engine.

Supplies the game's identity, its ``GameState`` class, its default (player-editable)
ruleset as settings, and the root screen the engine boots into.
"""

from __future__ import annotations

from pathlib import Path

from termcade.app.game import Game

from .console import COMMANDS
from .logic.settings import default_settings, refreshed_for_pool, save_note
from .logic.state import XiaolinState
from .music import XIAOLIN
from .screens.format import wu_in_prose
from .screens.start import StartScreen

THEME = Path(__file__).resolve().parent / "theme" / "xiaolin.tcss"


def build_game() -> Game:
    return Game(
        game_id="xiaolin_showdown",
        title="Xiaolin Showdown",
        version="1.3 (beta)",
        state_cls=XiaolinState,
        default_settings=default_settings(),
        # The deck size and the win target are read off the CARD POOL, not chosen by a player, so a
        # settings file written for a smaller pool must not go on dealing a smaller game. A save
        # keeps its own frozen settings — that run is that game — but the defaults a NEW run is
        # dealt with follow the pool.
        refresh_settings=refreshed_for_pool,
        # The pool fingerprint is bookkeeping, not a preference: it records which card pool this
        # settings file was written for. It must survive the prune and must NOT be shipped in the
        # defaults, or a stale file inherits it and reads as current.
        private_options=frozenset({"pool"}),
        # A run saved under a smaller pool still plays by its own rules. The slot says so, rather
        # than leaving the player to wonder why the game feels different.
        save_note=save_note,
        # `~` opens the console; these are what it can do. It exists to make a NEW Wu testable:
        # deal it into a hand, stack the pile with it, and play the thing you are judging by the
        # same rules a dealt Wu would be played by.
        console_commands=COMMANDS,
        # The Game Log is the engine's; the Wu in it are ours. Without this a card is plain grey words
        # on the one screen that recounts the whole run.
        log_line=wu_in_prose,
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
        # the board: the start menu (banner + wordmark + 5 buttons) measures 42 rows, the temple 30.
        fit_size=(110, 44),
    )
