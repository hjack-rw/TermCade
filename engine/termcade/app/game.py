"""The wiring seam between a game and the engine.

``Game`` is a static descriptor a game supplies. ``GameContext`` is the runtime
service container every screen depends on. Both are built from ``core`` only, so
the whole service layer is unit-testable with no Textual and no TTY. ``root_screen``
is stored as an opaque callable so this module never imports the UI layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from collections.abc import Mapping
from typing import Any, Callable

from termcade.core.audio import AudioPlayer, make_player
from termcade.core.journal import Journal
from termcade.core.music import ARCADE, Style
from termcade.core.paths import app_dir
from termcade.core.rng import Rng
from termcade.core.saves import SaveBackend, SaveManager, SqliteBackend
from termcade.core.settings import Settings, SettingsStore
from termcade.core.state import GameState


@dataclass(frozen=True)
class SaveNote:
    """A mark against a save, and what it means when you hover it.

    Two fields and not one, because they answer different questions. The **mark** sits in the slot's
    label, where there is room for a character and no more — so it must be small enough to ignore. The
    **explanation** is what it is *for*, and it can afford a sentence.
    """

    mark: str
    explanation: str


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
    # The musical rules the cartridge's theme is composed under. Default is the cabinet's own
    # voice, so a game that says nothing still gets a soundtrack that sounds like it belongs.
    music_style: Style = ARCADE
    # A last word over the settings once they are loaded, for a game whose defaults are DERIVED from
    # its own data rather than chosen by a player.
    #
    # `SettingsStore` merges a saved file *over* the defaults — which is right for a preference and
    # wrong for a derived value: the file keeps whatever it was written with, forever. Xiaolin's deck
    # size and win target are read off the card pool, and a `settings.json` written when the pool held
    # ~20 Wu went on dealing 20 of 40 cards and ending at a target meant for a game half the size,
    # months after the pool grew. Every Wu printed since that file was written could simply never
    # appear. This is where a cartridge gets to notice that and put it right.
    refresh_settings: Callable[[Settings], Settings] | None = None
    # Option keys the game writes for its own bookkeeping rather than for a player. They survive the
    # settings prune (which drops anything nobody declares) but are not preferences — see
    # `SettingsStore._pruned`.
    private_options: frozenset[str] = frozenset()
    # What to say about a saved run whose rules differ from the ones a NEW run would be dealt. Given
    # the save's frozen settings, a cartridge returns a `SaveNote` — or None when there is nothing to
    # tell. A save keeps its own rules (that run is that game), and this is how a player finds out.
    save_note: Callable[[Settings], "SaveNote | None"] | None = None
    # The dev console's commands, by name (see `termcade.ui.screens.console`). The engine owns the
    # console — `~` opens it, it survives a command that raises, it prints what it is told — and the
    # GAME owns what a command can do, because only the game knows what a card is.
    #
    # Empty by default: a cartridge that supplies none simply has a console with nothing in it.
    console_commands: "Mapping[str, Any]" = field(default_factory=dict)
    # How a line of the journal is DRAWN in the Game Log (see `termcade.ui.screens.log`). Given the
    # message, a cartridge returns Rich text.
    #
    # The engine cannot do this itself: the log's lines are prose the game wrote ("Katnappé played Bras
    # Finger"), and only the game knows that "Bras Finger" is a Wu — which element colours it, what its
    # stats are, that a card is written `Name (1/2/3)` everywhere else it appears. Without this the log
    # is the one screen in the game where a card is plain grey words, and it reads as a different game.
    # None = draw the message as it was written.
    log_line: Callable[[str], Any] | None = None


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

        self.settings = SettingsStore(
            self.data_dir / "settings.json",
            game.default_settings,
            private_options=game.private_options,
        )
        loaded = self.settings.load()
        if game.refresh_settings is not None:
            refreshed = game.refresh_settings(loaded)
            if refreshed != loaded:
                self.settings.save(refreshed)  # heal the file, so it is right for the next launch too

        # Always a real player where the platform has one. Whether it is *playing* is the music
        # setting's business, checked at the point of play — resolving it here would freeze the
        # answer at boot, and the toggle on the settings screen would do nothing until restart.
        self.audio = player if player is not None else make_player()

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

        # Everything the run has said, in order — every notification, plus whatever the game writes
        # down itself. Built BEFORE `state`, because assigning a state empties it.
        self.journal = Journal()

        # The game's current live state (opaque GameState); set by the game on new-game/load.
        self._state: GameState | None = None

    @property
    def state(self) -> GameState | None:
        return self._state

    @state.setter
    def state(self, state: GameState | None) -> None:
        """Set the live state — and empty the journal, because a new state is a new run.

        A property and not a plain attribute for exactly this: the log is emptied in *one* place. A
        new game and a loaded save both land here, and neither should open showing the tail of the
        game before it — a record of a run must be a record of *that* run.
        """
        self._state = state
        self.journal.clear()
