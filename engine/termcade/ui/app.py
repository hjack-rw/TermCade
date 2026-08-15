"""The base Textual application every termcade game runs on."""

from __future__ import annotations

import os
from pathlib import Path, PurePath
from typing import Any, Callable, cast

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.timer import Timer
from textual.widgets import Button, Footer, Header, Static

from termcade.app.game import Game, GameContext
from termcade.app.tunes import MUSIC_CROSSFADE, TunePlayer
from termcade.ui.screens.console import ConsoleScreen, debug_enabled
from termcade.ui.screens.dialog import ChoiceModal
from termcade.core import audio, music
from termcade.core.audio import make_player
from termcade.core.music import Style

from .screens.base import TOUCH_ENV, EngineScreen
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

# The same wordmark at 38 columns, for a screen with no room for the full one. BANNER is 89 wide and
# a phone held upright has about 81, so the brand is the one thing on the start screen that would
# not fit.
#
# Still a figure font (pyfiglet "small", generated once and baked in like BANNER itself) rather than
# a plain letter-spaced line: a wordmark that is just text stops the start screen looking like a
# cabinet and starts it looking like a form.
BANNER_COMPACT = (
    r" _____              ___         _     " "\n"
    r"|_   _|__ _ _ _ __ / __|__ _ __| |___ " "\n"
    r"  | |/ -_) '_| '  \ (__/ _` / _` / -_)" "\n"
    r"  |_|\___|_| |_|_|_\___\__,_\__,_\___|"
)

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

        ``False`` removes it outright, and that is what a touch session gets. Focus mode is a way to
        drive the game with keys a phone does not have: there is no Tab to enter it with and no
        arrows to move inside it, so advertising it spends a slot in a footer that is already the
        most crowded row on a 6cm screen. Tapping the thing you want was always the better answer
        there — focus mode exists for the players who cannot do that.
        """
        if action == "toggle_focus":
            # Hides the key. It does NOT disable it — this binding is priority, and a priority
            # binding runs without asking. The action itself refuses; see action_toggle_focus.
            if self.is_touch:
                return False
            return True if self.screen.focus_chain else None
        return True

    def __init__(
        self,
        game: Game | None = None,
        *,
        data_dir: Path | None = None,
        seed: int | str | None = None,
        is_touch: bool | None = None,
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
        # Read once, at boot, never at every call site (every other site below reads this attribute
        # instead) -- that made it awkward to override in a test without monkeypatching the
        # environment 7 times over, and it is now load-bearing for a second reason: a session's
        # subprocess is told this via its OWN environment at spawn (see `termcade.session`), which
        # works because each subprocess gets a real, OS-isolated env block. An in-process session has
        # no such isolation -- os.environ is one shared, process-wide dict once several sessions
        # share a process -- so it is passed explicitly there instead. The env var stays as the
        # fallback for the (still-current, subprocess-per-session) production entry point, which does
        # not pass it explicitly.
        self.is_touch = is_touch if is_touch is not None else bool(os.environ.get(TOUCH_ENV))
        # With no game there is no context to own the player, but the empty cabinet still hums.
        player = self.ctx.audio if self.ctx is not None else make_player()
        self._music = TunePlayer(player, game=game, settings=self.ctx.settings if self.ctx else None)

    def on_mount(self) -> None:
        self.register_theme(TERMCADE_THEME)
        self.theme = "termcade"
        self._use_browser_audio()
        if self.game is not None and self.game.root_screen is not None:
            self.push_screen(self.game.root_screen())
        else:
            self.push_screen(HelloScreen())
        self.apply_music_setting()

    def _use_browser_audio(self) -> None:
        """Send sound to the page instead of the machine, when there is a page.

        Not decided in ``__init__``: the driver does not exist until the app is running, and the
        driver is what knows whether anyone is watching through a browser. The device player built
        for a local run is released rather than left holding a stream — under ``xiaolin-play`` the
        server and the browser are the *same* machine, so leaving it open would play the soundtrack
        twice, once out of each.

        Resolving ``write_meta`` off ``self._driver`` here, not in ``core.audio``: only this
        (Textual-aware) layer knows the driver's shape, and core's own contract is to never import
        Textual to go looking for it.
        """
        write_meta = getattr(getattr(self, "_driver", None), "write_meta", None)
        player = audio.browser_player(
            cast("Callable[[dict[str, object]], None] | None", write_meta) if callable(write_meta) else None
        )
        if player is None:
            return
        self._music.player.close()
        self._music.player = player
        if self.ctx is not None:
            self.ctx.audio = player

    def _set_mouse_over(self, widget: Any, hover_widget: Any) -> None:
        """A finger does not hover, so on a touch session nothing ever does.

        Textual re-applies the hover at ``mouse_position`` on every repaint, to keep it honest when
        widgets move under a stationary mouse. A finger has no resting position for it to be honest
        about: ``mouse_position`` is wherever the last tap landed, and it stays there. So the widget
        the NEXT screen puts on that spot comes up hovered without being touched — and a hovered
        `Button` wears the accent border and the flattened label, which is what a *chosen* option
        looks like. Tap Play, and the character screen arrives with Raimundo already lit.

        Suppressed at the source rather than in the theme: hover reaches the screen by two routes —
        the `:hover` pseudo-class the TCSS styles, and the `mouse_hover` flag `Button.render` reads —
        and both are set here. A `.-touch` twin for every `:hover` rule would have to be written
        again for every rule a cartridge adds, and would still leave the flag set.

        Nothing else is lost. A tap is routed by what is under it, not by what is hovered, and a
        tooltip is a thing you get by resting a pointer you do not have.
        """
        if self.is_touch:
            return
        super()._set_mouse_over(widget, hover_widget)

    @property
    def music_on(self) -> bool:
        return self._music.music_on

    @property
    def sfx_on(self) -> bool:
        return self._music.sfx_on

    def play_sfx(self, name: str) -> None:
        self._music.play_sfx(name)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Every button in the cabinet clicks, including a game's own — the event bubbles up here
        after the screen has handled it, so a cartridge gets this for free and cannot forget it."""
        self.play_sfx(music.CLICK)

    def apply_music_setting(self, *, crossfade: float = 0.0) -> None:
        self._music.apply_music_setting(crossfade=crossfade)

    def play_tune(
        self,
        style: Style,
        *,
        name: str,
        seed: str | None = None,
        crossfade: float = MUSIC_CROSSFADE,
        echo: bool = False,
        sync: bool = False,
    ) -> None:
        self._music.play_tune(style, name=name, seed=seed, crossfade=crossfade, echo=echo, sync=sync)

    def prerender_tune(self, style: Style, *, name: str, seed: str, echo: bool = False) -> None:
        self._music.prerender_tune(style, name=name, seed=seed, echo=echo)

    def notify(self, message: str, *, title: str = "", log: bool = True, **kwargs: Any) -> None:
        """Raise a toast, and journal it — the Game Log reads the journal back.

        ``log=False`` for a toast that is not an *event*: a refusal ("no retreat from a showdown"), or
        something the game writes down better itself.

        The toast is spaced through `spaced_dashes` on the way to the screen — the em dash is drawn a
        full cell wide and eats the space after it. The JOURNAL keeps the raw text, so the Game Log
        applies its own spacing when it draws.
        """
        if log and self.ctx is not None:
            self.ctx.journal.add(message, title=title, severity=kwargs.get("severity", "information"))
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
        # `ctx` itself must exist (a Game is running); its `state` need not — most commands act on a
        # live run and say so plainly ("no run in progress") when there isn't one, but not every
        # command does (a cartridge may offer one that only touches settings, e.g. an unlock cheat
        # reachable from the main menu).
        if self.ctx is None:
            return
        self.push_screen(ConsoleScreen())

    def action_toggle_focus(self) -> None:
        """Tab toggles keyboard-nav mode: focus the first option if nothing is focused, or clear focus
        (step out of the mode) if something already is.

        Refused outright on a touch session, and the guard has to be HERE rather than in
        ``check_action``: this binding is ``priority=True``, and a priority binding runs without
        consulting the check. Hiding the key from the footer therefore left it fully live — pressed
        from a tablet's keyboard case it would drop a player into a mode with no visible way out,
        since the footer no longer advertises the key that leaves it.
        """
        if self.is_touch:
            return
        if self.screen.focused is None:
            self.screen.focus_next()
        else:
            self.screen.set_focus(None)

    def action_focus_next(self) -> None:
        """The arrows move *within* focus mode, so they are off wherever the mode is."""
        if self.is_touch:
            return
        self.screen.focus_next()

    def action_focus_previous(self) -> None:
        if self.is_touch:
            return
        self.screen.focus_previous()

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
        self._music.closing = True
        self._music.player.stop()
        self._music.player.close()

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
