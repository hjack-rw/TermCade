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
    default_settings: Settings = field(default_factory=Settings)
    saves_enabled: bool = True
    max_slots: int = 6
    # Zero-arg callable returning the game's root Screen. Opaque here (UI-free).
    root_screen: Callable[[], Any] | None = None
    # Absolute paths to the game's TCSS theme files; the engine app loads them app-wide.
    theme_paths: list[Path] = field(default_factory=list)


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
    ) -> None:
        self.game = game
        self.data_dir = data_dir or app_dir(game.game_id)

        self.settings = SettingsStore(self.data_dir / "settings.json", game.default_settings)
        self.settings.load()

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
