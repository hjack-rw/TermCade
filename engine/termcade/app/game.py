"""The wiring seam between a game and the engine.

``Game`` is a static descriptor a game supplies. ``GameContext`` is the runtime
service container every screen depends on. Both are built from ``core`` only, so
the whole service layer is unit-testable with no Textual and no TTY. ``root_screen``
is stored as an opaque callable so this module never imports the UI layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from termcade.core.audio import AudioPlayer, make_player
from termcade.core.paths import app_dir
from termcade.core.rng import Rng
from termcade.core.saves import SaveBackend, SaveManager, SqliteBackend
from termcade.core.settings import Settings, SettingsStore
from termcade.core.state import GameState


@dataclass
class Game:
    game_id: str
    title: str
    state_cls: type[GameState]
    version: str = "0.0.0"  # the cartridge's own version, shown in the menu corner
    default_settings: Settings = field(default_factory=Settings)
    saves_enabled: bool = True
    max_slots: int = 6
    # Zero-arg callable returning the game's root Screen. Opaque here (UI-free).
    root_screen: Callable[[], Any] | None = None
    # Absolute paths to the game's TCSS theme files; the engine app loads them app-wide.
    theme_paths: list[Path] = field(default_factory=list)
    # Minimum terminal (cols, rows); below it the engine shows a "too small" overlay. None = no
    # floor, for a game whose screens scroll.
    min_size: tuple[int, int] | None = None
    # The grid the browser build sizes its font to fit — the layout the game wants at rest.
    fit_size: tuple[int, int] | None = None


class GameContext:
    """Runtime services handed to every screen, plus the game's current ``state``.

    TUI-agnostic — built from ``core`` only.
    """

    def __init__(
        self,
        game: Game,
        *,
        data_dir: Path | None = None,
        seed: int | str | None = None,
        backend: SaveBackend | None = None,
        player: AudioPlayer | None = None,
    ) -> None:
        self.game = game
        self.data_dir = data_dir or app_dir(game.game_id)

        self.settings = SettingsStore(self.data_dir / "settings.json", game.default_settings)
        self.settings.load()

        # Always a real player where the platform has one. Whether it is *playing* is the music
        # setting's business, checked at the point of play — resolving it here would freeze the
        # answer at boot, and the toggle on the settings screen would do nothing until restart.
        self.audio = player if player is not None else make_player(cache_dir=self.data_dir)

        # SQLite is the real store; pass ``backend=`` to override (e.g. JsonFileBackend).
        if backend is None:
            backend = SqliteBackend(self.data_dir / "saves.db")
        self.saves = SaveManager(
            game.game_id,
            backend,
            saves_enabled=game.saves_enabled,
            max_slots=game.max_slots,
        )

        self.rng = Rng(seed)

        # The game's current live state (opaque GameState); set by the game on new-game/load.
        self.state: GameState | None = None
