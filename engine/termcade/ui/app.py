"""The base Textual application every termcade game runs on."""

from __future__ import annotations

from array import array
from pathlib import Path, PurePath
from typing import Any

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.timer import Timer
from textual.widgets import Button, Footer, Header, Static

from termcade.app.game import Game, GameContext
from termcade.ui.screens.console import ConsoleScreen, debug_enabled
from termcade.ui.screens.dialog import ChoiceModal
from termcade.core import music
from termcade.core.audio import MUSIC_OPTION, SFX_OPTION, make_player

from .screens.base import EngineScreen
from .theme import TERMCADE_THEME
from .typography import spaced_dashes

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

    # A tooltip hides whenever the pointer moves and reappears once it rests. Textual's 0.5s makes
    # that read as a flicker; a shorter rest feels like the tooltip is simply following the cursor.
    TOOLTIP_DELAY = 0.2

    # Keyboard navigation for every screen and modal. Tab is a *toggle* into "focus mode" — press it
    # once to highlight the first option, again to step back out (no option highlighted); up/down move
    # within the mode. Tab is `priority` so it overrides Textual's built-in Screen tab binding (plain
    # focus-next) app-wide, modals included. Arrows are app-level, so they yield to a widget that uses
    # the key itself (an Input keeps its own cursor). All hidden from the footer to keep it uncluttered.
    BINDINGS = [
        # Shown in the footer, and live only where focus has somewhere to go (see `check_action`). Tab
        # moves focus in every Textual app and says so in none of them, and `EngineScreen.AUTO_FOCUS = ""`
        # makes that worse here: nothing starts focused, so nothing hints that focus is a thing at all.
        # A key a player cannot discover is a key they do not have.
        #
        # `priority=True` is why this must be fixed HERE and could not be fixed on the screen: an
        # app-level priority binding beats a screen's, so a `Binding("tab", ...)` added to EngineScreen
        # is dead the moment it is written.
        Binding("tab", "toggle_focus", "Focus", show=True, priority=True),
        # Dev console, four names. `~` needs Shift and may never arrive over textual-serve/xterm.js;
        # the backtick needs no modifier and is the one that works. `Pilot.press("~")` maps the
        # character for you, so a passing test proves nothing here — only a terminal does.
        Binding("grave_accent,~,tilde,f12", "console", "Console", show=False, priority=True),
        Binding("up", "focus_previous", "Previous", show=False),
        Binding("down", "focus_next", "Next", show=False),
    ]

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """Grey the focus key out on a screen with nothing to focus.

        ``None`` marks the binding *disabled*, and Textual's ``Footer`` renders a disabled key dimmed
        rather than dropping it (`Footer.compose` filters on ``binding.show``, not on ``enabled``). So
        the key is always listed and is only *live* where focus has somewhere to go — which is the
        honest compromise: a player learns the key exists, and the screen tells them when it does
        nothing here.
        """
        if action == "toggle_focus":
            return True if self.screen.focus_chain else None
        return True

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
        # With no game there is no context to own the player, but the empty cabinet still hums.
        self._player = self.ctx.audio if self.ctx is not None else make_player()
        self._closing = False
        self._theme: bytes | None = None  # rendered once, then kept — a toggle must be instant
        self._sfx: dict[str, array] = {}  # synthesized on first press, then kept

    def on_mount(self) -> None:
        self.register_theme(TERMCADE_THEME)
        self.theme = "termcade"
        if self.game is not None and self.game.root_screen is not None:
            self.push_screen(self.game.root_screen())
        else:
            self.push_screen(HelloScreen())
        self.apply_music_setting()

    @property
    def music_on(self) -> bool:
        """The live answer, re-read every time — this is what makes the toggle take effect now."""
        if self.ctx is None:
            return True
        return bool(self.ctx.settings.current.options.get(MUSIC_OPTION, True))

    @property
    def sfx_on(self) -> bool:
        if self.ctx is None:
            return True
        return bool(self.ctx.settings.current.options.get(SFX_OPTION, True))

    def play_sfx(self, name: str) -> None:
        """Sound one effect. Synthesized once and kept — a click has to answer the key that caused
        it, and re-rendering it on every press would put that work on the UI thread."""
        if not self.sfx_on:
            return
        if name not in self._sfx:
            self._sfx[name] = music.sfx(name)
        self._player.play_once(self._sfx[name])

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Every button in the cabinet clicks, including a game's own — the event bubbles up here
        after the screen has handled it, so a cartridge gets this for free and cannot forget it."""
        self.play_sfx(music.CLICK)

    def apply_music_setting(self) -> None:
        """Start or stop the soundtrack to match the setting. Safe to call as often as you like."""
        if not self.music_on:
            self._player.stop()
        elif self._theme is not None:
            self._player.play_loop(self._theme)
        else:
            self.run_worker(self._start_theme, thread=True, group="theme")

    def _start_theme(self) -> None:
        """Synthesize and start the soundtrack off the UI thread — rendering it takes long enough
        to be seen as a stutter on the first frame. Only ever runs once; the toggle replays the
        bytes it left behind.

        Seeded by ``game_id`` so a cartridge always sounds like itself, and *not* from ``ctx.rng``:
        pulling decoration off the play stream is exactly the mistake ``Rng.spawn`` exists to
        prevent, and a fixed string can't make it in the first place. The seed picks the tune; the
        cartridge's ``music_style`` decides what kind of music it is a tune of.
        """
        seed = self.game.game_id if self.game is not None else "termcade"
        style = self.game.music_style if self.game is not None else music.ARCADE
        self._theme = music.theme(seed, style)
        # The render outlives a fast quit, and a player who muted while it ran wants silence, not a
        # late start — both would otherwise leave the OS looping a sound nobody asked for.
        if not self._closing and self.music_on:
            self._player.play_loop(self._theme)

    def notify(self, message: str, *, title: str = "", log: bool = True, **kwargs: Any) -> None:
        """Raise a toast, and journal it — the Game Log reads the journal back.

        ``log=False`` for a toast that is not an *event*: a refusal ("no retreat from a showdown"), or
        something the game writes down better itself.

        The toast is spaced through `spaced_dashes` on the way to the screen — the em dash is drawn a
        full cell wide and eats the space after it. The JOURNAL keeps the raw text, so the Game Log
        applies its own spacing when it draws.
        """
        if log and self.ctx is not None:
            self.ctx.journal.add(message, title=title)
        super().notify(spaced_dashes(message), title=title, **kwargs)

    def report_crash(self, error: BaseException, *, where: str) -> None:
        """A crashed worker's exception, named and dismissible, instead of a dead game. See
        `termcade.ui.work`."""
        self.log.error(f"worker {where!r} crashed", error)
        self.push_screen(
            ChoiceModal(
                f"{type(error).__name__}: {error}",
                [("Continue", None)],
                title="SOMETHING BROKE",
            )
        )

    def action_console(self) -> None:
        """Toggle the dev console over whatever is on screen — the key that opens it shuts it.

        A *toggle*, and it has to live here rather than on the console: this is an app-level priority
        binding, so it fires before any binding the console itself declares. A "close" binding on the
        console screen looked right and never ran.
        """
        if isinstance(self.screen, ConsoleScreen):
            self.pop_screen()
            return
        # Locked behind TERMCADE_DEBUG. A console that can deal a player any Wu in the game does not
        # belong in a shipped build behind nothing but an undocumented key — hidden is not the same as
        # absent, and this is absent.
        if not debug_enabled():
            return
        # And only over a RUNNING game: every command acts on a run — deal a Wu into a hand, stack a
        # pile, set the score — so a console on the start menu is a box whose every answer is "there is
        # no game".
        if self.ctx is None or self.ctx.state is None:
            return
        self.push_screen(ConsoleScreen())

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

    def on_unmount(self) -> None:
        # Don't leave the coalescing timer armed past shutdown — it would fire into a torn-down app.
        if self._resize_timer is not None:
            self._resize_timer.stop()
            self._resize_timer = None
        # The stream outlives the terminal: an open device keeps its callback thread running and
        # the theme audible after the app has let go of the screen. Closing is not optional.
        self._closing = True
        self._player.stop()
        self._player.close()

    def _enforce_min_size(self) -> None:
        """Show the overlay while the window is below the game's minimum, hide it once it fits.
        Keyed off the *actual* top screen, not a bool that drifts out of sync with the stack — that
        drift was the "grow the window back and the game never returns" bug (a stale flag popped the
        game screen instead of the overlay)."""
        if self._min_size is None or not self.screen_stack:
            # The resize timer outlives the screens: a resize within 0.15s of quitting lands here
            # after the stack is gone, where `self.screen` raises ScreenStackError.
            return
        min_width, min_height = self._min_size
        too_small = self.size.width < min_width or self.size.height < min_height
        showing = isinstance(self.screen, TooSmallScreen)
        if too_small and not showing:
            self.push_screen(TooSmallScreen())
        elif not too_small and showing:
            self.pop_screen()
