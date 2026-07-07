"""The base Textual application every termcade game runs on."""

from __future__ import annotations

from pathlib import Path, PurePath

from textual.app import App, ComposeResult
from textual.widgets import Footer, Header, Static

from termcade.app.game import Game, GameContext

from .screens.base import EngineScreen


class HelloScreen(EngineScreen):
    """Attract scene for the empty cabinet — shown when no game is loaded."""

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("TermCade — engine online", id="hello")
        yield Footer()


class EngineApp(App[None]):
    """Base Textual application for termcade games.

    Given a ``Game``, it builds the ``GameContext`` (settings, saves, rng) and boots the
    game's root screen. With no game it shows the attract scene, so the engine stays
    runnable and testable on its own (``python -m termcade``).
    """

    TITLE = "TermCade"

    def __init__(
        self,
        game: Game | None = None,
        *,
        data_dir: Path | None = None,
        seed: int | str | None = None,
    ) -> None:
        # Engine theme is always loaded; a game contributes its own theme files on top.
        engine_theme: str | PurePath = Path(__file__).resolve().parent / "theme" / "engine.tcss"
        css_paths: list[str | PurePath] = [engine_theme]
        if game is not None:
            css_paths.extend(game.theme_paths)
        super().__init__(css_path=css_paths)
        self.game = game
        self.ctx: GameContext | None = (
            GameContext(game, data_dir=data_dir, seed=seed) if game is not None else None
        )

    def on_mount(self) -> None:
        if self.game is not None and self.game.root_screen is not None:
            self.push_screen(self.game.root_screen())
        else:
            self.push_screen(HelloScreen())
