"""The cabinet's music and sound effects — one ``TunePlayer`` per app, entirely Textual-free.

Built from ``core`` only (an ``AudioPlayer`` plus the pieces of ``Game``/``SettingsStore`` it needs),
so the render pipeline is unit-testable with no TTY. ``EngineApp`` owns one and forwards to it under
the same method names it used to define itself — the split cost its callers nothing.
"""

from __future__ import annotations

import queue
import threading
from array import array
from typing import Callable

from termcade.core import music
from termcade.core.audio import MUSIC_OPTION, SFX_OPTION, AudioPlayer
from termcade.core.music import Style
from termcade.core.settings import SettingsStore

from .game import Game

# How long one tune takes to become another. Long enough that the two overlap as a change of mood
# rather than a cut, short enough that the new tune is established before the moment has passed.
MUSIC_CROSSFADE = 1.2


class TunePlayer:
    """Renders, caches and plays the cabinet's tunes and sound effects.

    ``game`` and ``settings`` are read-only references (never reassigned once construction hands
    them over) — the same objects ``EngineApp`` itself holds, so a music-setting change or a
    cartridge default reaches both sides without any syncing.
    """

    def __init__(self, player: AudioPlayer, *, game: Game | None, settings: SettingsStore | None) -> None:
        self.player = player
        self._game = game
        self._settings = settings
        # The stream outlives the terminal unless told otherwise — see EngineApp.on_unmount.
        self.closing = False
        # Tunes are rendered once and KEPT, keyed by name — a toggle must be instant, and so must
        # switching back to a tune already heard (a boss run ending, say).
        self._tunes: dict[str, bytes] = {}
        # Each tune's own grid-step duration, keyed the same way — a later switch needs the
        # OUTGOING tune's step_seconds too, and it may no longer be the one rendering.
        self._tune_step_seconds: dict[str, float] = {}
        # Names queued or currently rendering — guards `prerender_tune` against queuing the same
        # tune twice while it's already waiting or in flight.
        self._prerendering: set[str] = set()
        # One render at a time, off the UI thread: a separate `threading.Thread` per tune let two
        # or three CPU-bound renders fight the UI thread for GIL slices at once, which is what was
        # producing torn frames and audio glitches on a real terminal (see `prerender_tune`). A
        # single persistent worker serializes them — still off the UI thread, never competing with
        # itself.
        self._render_jobs: queue.Queue[Callable[[], None]] = queue.Queue()
        threading.Thread(target=self._render_worker, daemon=True, name="tune-render").start()
        self._tune = ""  # which tune is current; "" is the cartridge's own `music_style`
        self._tune_style: Style | None = None  # set when a cartridge switched to one of its own
        self._tune_seed: str | None = None  # set when that tune is composed off its own seed
        # None (unset) defers to the cartridge's own `music_echo`; a `play_tune` call always pins
        # an explicit True/False of its own, which is why this can't just default to `False`.
        self._tune_echo: bool | None = None
        self._tune_sync = False  # set per switch by `play_tune`; see its docstring
        self._crossfade = 0.0  # seconds, carried to the render worker when a switch has to wait on it
        self._sfx: dict[str, array] = {}  # synthesized on first press, then kept

    @property
    def music_on(self) -> bool:
        """The live answer, re-read every time — this is what makes the toggle take effect now."""
        if self._settings is None:
            return True
        return bool(self._settings.current.options.get(MUSIC_OPTION, True))

    @property
    def sfx_on(self) -> bool:
        if self._settings is None:
            return True
        return bool(self._settings.current.options.get(SFX_OPTION, True))

    def play_sfx(self, name: str) -> None:
        """Sound one effect. Synthesized once and kept — a click has to answer the key that caused
        it, and re-rendering it on every press would put that work on the UI thread."""
        if not self.sfx_on:
            return
        if name not in self._sfx:
            self._sfx[name] = music.sfx(name)
        self.player.play_once(self._sfx[name])

    def apply_music_setting(self, *, crossfade: float = 0.0) -> None:
        """Start or stop the soundtrack to match the setting. Safe to call as often as you like."""
        if not self.music_on:
            self.player.stop()
        elif (tune := self._tunes.get(self._tune)) is not None:
            self.player.play_loop(
                tune,
                crossfade=crossfade,
                step_seconds=self._tune_step_seconds.get(self._tune),
                sync=self._tune_sync,
            )
        else:
            self._crossfade = crossfade
            # A thread worker here (`run_worker(self._start_theme, thread=True, group="theme")`)
            # hangs indefinitely when a second tune is rendered after the first — reproduced via
            # `test_reaching_the_point_limit_ends_the_game_instead_of_dueling` (the outcome screen's
            # victory jingle, started from `end_run`, after the temple's own boot theme already used
            # this same path). A `faulthandler` thread dump at the hang showed the event loop simply
            # idling and every pool thread idle too — nothing computing, consistent with something in
            # Textual's worker bookkeeping never resolving, not a slow render (confirmed independently
            # fast, ~1s, run directly). Synchronous costs that ~1s on the UI thread once per NEW tune
            # instead of a background render — real, but far better than a run that never ends.
            self._start_theme()

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
        """Switch the soundtrack to another style of the cartridge's own — a boss theme, say.

        The cabinet knows how to play a tune; only the cartridge knows *which* tune a moment calls for,
        so the style is passed in rather than looked up. Calling with the tune already playing is a
        no-op, so a screen may call it on every mount without restarting the music under the player.

        A switch CROSSFADES, because one tune is replacing another under a player who is mid-run and
        did not ask for a jolt. Starting from silence still cuts — there is nothing to fade from.
        ``crossfade`` defaults to the cabinet's own pace; pass a longer one to keep the incoming
        tune quiet in the background for longer — under a jingle it's meant to stay behind, say,
        rather than climbing to full volume partway through it.

        ``seed`` defaults to the cartridge's own ``game_id`` — the same melody under different rules,
        which is what makes a boss theme read as "the same place, tenser" rather than a new track.
        Pass one of your own when the moment needs to sound like an unrelated piece instead — the
        outcome screen's win jingle is not a variation on the temple's theme, it just isn't the same
        song, and no amount of octave or tempo makes a transposition stop sounding like one.

        ``sync`` asks the switch to land on the outgoing tune's current position in the bar instead
        of restarting at 0 — only sensible between tunes sharing a seed (the default ``seed``, not
        one of your own), since that is what makes them the same underlying pattern at a possibly
        different tempo. Set it on the switches that should read as one piece continuing (a boss
        fight kicking the temple's own theme into a higher gear); leave it off where the new tune
        is deliberately a different piece (the win jingle's own ``seed`` already makes ``sync``
        meaningless there).
        """
        if name == self._tune:
            return
        playing = self._tunes.get(self._tune) is not None
        self._tune, self._tune_style, self._tune_seed = name, style, seed
        self._tune_echo, self._tune_sync = echo, sync
        self.apply_music_setting(crossfade=crossfade if playing else 0.0)

    def _render_worker(self) -> None:
        """The one thread that ever synthesizes a tune. Started once in ``__init__``; runs for the
        life of the app, pulling jobs off ``_render_jobs`` one at a time."""
        while True:
            self._render_jobs.get()()

    def prerender_tune(self, style: Style, *, name: str, seed: str, echo: bool = False) -> None:
        """Queue a tune's bytes to render into the cache without playing it, off the UI thread.

        ``end_run`` used to hit this render cold, synchronously, in the same call that arms the
        timer that switches to ``OutcomeScreen`` — and that combination hung the switch's screen
        mount every time (reproduced outside pytest: a `faulthandler` + `asyncio.all_tasks` dump
        caught `switch_screen`'s own mount-await stuck forever, never the render itself). Calling
        this early, well before that switch, gives the render worker room to finish before anyone
        needs the result — a duel is never won or lost in the first few seconds of a run. Worst
        case, it hasn't finished by the time `play_tune` wants it: `apply_music_setting` already
        renders synchronously when a tune isn't in the cache, so a still-queued prerender just
        costs that same fallback, not a hang.
        """
        if name in self._tunes or name in self._prerendering:
            return
        self._prerendering.add(name)

        def render() -> None:
            rendered, step_seconds = music.theme_track(seed, style, echo=echo)
            self._tunes[name] = rendered
            self._tune_step_seconds[name] = step_seconds
            self._prerendering.discard(name)

        self._render_jobs.put(render)

    def _start_theme(self) -> None:
        """Synthesize and start the soundtrack off the UI thread — rendering it takes long enough
        to be seen as a stutter on the first frame. Only ever runs once; the toggle replays the
        bytes it left behind.

        Stays synchronous, unlike `prerender_tune`: this fires from `TempleScreen.on_mount` right
        alongside the (now backgrounded) outcome-jingle prerenders, and threading it too stacked a
        THIRD CPU-bound render thread against Textual's first paint of that screen's own multi-panel
        layout — real terminal contention a headless Pilot test never renders enough to catch,
        confirmed only by actually playing it (garbled/duplicated border glyphs on first paint).

        Seeded by ``game_id`` so a cartridge always sounds like itself, and *not* from ``ctx.rng``:
        pulling decoration off the play stream is exactly the mistake ``Rng.spawn`` exists to
        prevent, and a fixed string can't make it in the first place. The seed picks the tune; the
        cartridge's ``music_style`` decides what kind of music it is a tune of.
        """
        # The seed stays the cartridge's by default, so a switched tune is the same melody under
        # different rules — the faster cousin of what was playing, not an unrelated piece. A tune
        # that asked for its own seed (see `play_tune`) is the deliberate exception.
        seed = self._tune_seed or (self._game.game_id if self._game is not None else "termcade")
        name = self._tune
        style = self._tune_style or (self._game.music_style if self._game is not None else music.ARCADE)
        # Unset (None) means this is the cartridge's own default tune, never routed through
        # `play_tune` — defer to its own `music_echo` rather than silently going echo-less.
        echo = self._tune_echo if self._tune_echo is not None else (
            self._game.music_echo if self._game is not None else False
        )
        rendered, step_seconds = music.theme_track(seed, style, echo=echo)
        self._tunes[name] = rendered
        self._tune_step_seconds[name] = step_seconds
        # The render outlives a fast quit, and a player who muted while it ran wants silence, not a
        # late start — both would otherwise leave the OS looping a sound nobody asked for. It also
        # outlives a switch: by the time it lands the player may already be on another tune.
        if not self.closing and self.music_on and self._tune == name:
            self.player.play_loop(
                rendered, crossfade=self._crossfade, step_seconds=step_seconds, sync=self._tune_sync
            )
        self._crossfade = 0.0
