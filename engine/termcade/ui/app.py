"""The base Textual application every termcade game runs on."""

from __future__ import annotations

from pathlib import Path, PurePath

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.timer import Timer
from textual.widgets import Footer, Header, Static

from termcade.app.game import Game, GameContext

from .screens.base import EngineScreen
from .theme import TERMCADE_THEME

# "TermCade" in an ANSI-shadow figure font — the cabinet's brand banner.
BANNER = """\
███████████                                      █████████                █████
░█░░░███░░░█                                     ███░░░░░███              ░░███
░   ░███  ░   ██████  ████████  █████████████   ███     ░░░   ██████    ███████   ██████
    ░███     ███░░███░░███░░███░░███░░███░░███ ░███          ░░░░░███  ███░░███  ███░░███
    ░███    ░███████  ░███ ░░░  ░███ ░███ ░███ ░███           ███████ ░███ ░███ ░███████
    ░███    ░███░░░   ░███      ░███ ░███ ░███ ░░███     ███ ███░░███ ░███ ░███ ░███░░░
    █████   ░░██████  █████     █████░███ █████ ░░█████████ ░░████████░░████████░░██████
   ░░░░░     ░░░░░░  ░░░░░     ░░░░░ ░░░ ░░░░░   ░░░░░░░░░   ░░░░░░░░  ░░░░░░░░  ░░░░░░"""

# At or above this width a screen is "-wide" (room for side-by-side panels); below it, "-narrow".
WIDE_COLS = 100


class HelloScreen(EngineScreen):
    """Attract scene for the empty cabinet — shown when no game is loaded."""

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="hello-root"):
            yield Static(BANNER, id="banner")
            yield Static("engine online", id="hello")
        yield Footer()


class TooSmallScreen(EngineScreen):
    """Overlay shown when the window is below the game's minimum size. No number — a browser player
    thinks in pixels, a terminal player in cells, and neither maps to the other; "make it bigger" is
    the only instruction that always makes sense."""

    def compose(self) -> ComposeResult:
        # Both levers: a bigger window adds rows only up to the screen; a smaller font is what
        # actually fits more rows in a maxed terminal (or zooms out the browser).
        yield Static(
            "Window too small.\n\nMake it bigger — or shrink the font (Ctrl+minus).",
            id="too-small",
        )


class EngineApp(App[None]):
    """Base Textual application for termcade games.

    Given a ``Game``, it builds the ``GameContext`` (settings, saves, rng) and boots the
    game's root screen. With no game it shows the attract scene, so the engine stays
    runnable and testable on its own (``python -m termcade``). A game may declare a minimum
    terminal size; below it the app shows a "too small" overlay until the terminal grows.
    """

    TITLE = "TERMCADE"

    # Responsive classes, stamped on the active screen by width, so a game's TCSS can reflow.
    HORIZONTAL_BREAKPOINTS = [(0, "-narrow"), (WIDE_COLS, "-wide")]

    # Keyboard navigation for every screen and modal. Tab is a *toggle* into "focus mode" — press it
    # once to highlight the first option, again to step back out (no option highlighted); up/down move
    # within the mode. Tab is `priority` so it overrides Textual's built-in Screen tab binding (plain
    # focus-next) app-wide, modals included. Arrows are app-level, so they yield to a widget that uses
    # the key itself (an Input keeps its own cursor). All hidden from the footer to keep it uncluttered.
    BINDINGS = [
        Binding("tab", "toggle_focus", "Focus", show=False, priority=True),
        Binding("up", "focus_previous", "Previous", show=False),
        Binding("down", "focus_next", "Next", show=False),
    ]

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
        self._min_size = game.min_size if game is not None else None
        self._resize_timer: Timer | None = None

    def on_mount(self) -> None:
        self.register_theme(TERMCADE_THEME)
        self.theme = "termcade"
        if self.game is not None and self.game.root_screen is not None:
            self.push_screen(self.game.root_screen())
        else:
            self.push_screen(HelloScreen())

    def action_toggle_focus(self) -> None:
        """Tab toggles keyboard-nav mode: focus the first option if nothing is focused, or clear focus
        (step out of the mode) if something already is."""
        if self.screen.focused is None:
            self.screen.focus_next()
        else:
            self.screen.set_focus(None)

    def on_resize(self) -> None:
        # A drag-resize fires a burst of events; coalesce to one check after it settles, so we never
        # race the async push/pop into a stuck overlay.
        if self._resize_timer is not None:
            self._resize_timer.stop()
        self._resize_timer = self.set_timer(0.15, self._enforce_min_size)

    def _enforce_min_size(self) -> None:
        """Show the overlay while the window is below the game's minimum, hide it once it fits.
        Keyed off the *actual* top screen, not a bool that drifts out of sync with the stack — that
        drift was the "grow the window back and the game never returns" bug (a stale flag popped the
        game screen instead of the overlay)."""
        if self._min_size is None:
            return
        min_width, min_height = self._min_size
        too_small = self.size.width < min_width or self.size.height < min_height
        showing = isinstance(self.screen, TooSmallScreen)
        if too_small and not showing:
            self.push_screen(TooSmallScreen())
        elif not too_small and showing:
            self.pop_screen()
