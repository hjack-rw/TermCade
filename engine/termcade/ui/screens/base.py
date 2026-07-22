"""Base screen ("scene") shared by engine and game screens."""

from __future__ import annotations

import os
from collections.abc import Sequence

from typing import TYPE_CHECKING, TypeVar, cast

from rich.text import Text
from textual import events
from textual.content import ContentText
from textual.screen import Screen
from textual.widgets import Footer
from textual.worker import Worker, WorkerState

from termcade.app.game import Game, GameContext

from .dialog import ChoiceModal
from ..widgets.button import Button

if TYPE_CHECKING:
    from ..app import EngineApp

_T = TypeVar("_T")

# Set per session by the browser gateway when the player is on a touch device (see `termcade.beta`).
# Every way out of a screen is a key — Escape, mostly — and a phone has no keys, so a touch player
# can reach a screen and then be stuck on it. Unset everywhere else: a terminal has the keys.
TOUCH_ENV = "TERMCADE_TOUCH"


class EngineScreen(Screen[None]):
    """Common base for every termcade screen.

    Exposes the running :class:`GameContext` as ``self.ctx`` (settings, saves, rng, and the
    game's current state). The dialog helpers (``choose`` / ``confirm`` / ``show_message``) raise
    a :class:`ChoiceModal` and resolve with the player's answer; ``await`` them from a worker
    (e.g. a ``@work`` method), since they suspend until the modal is dismissed.
    """

    # Don't auto-focus the first widget — no option should look pre-selected on a fresh screen. This
    # must be "" (not None): Textual reads AUTO_FOCUS=None as "inherit the app default", which is "*"
    # (focus the first focusable); only the empty string truly disables auto-focus.
    AUTO_FOCUS = ""

    # The focus key (Tab) is advertised by `EngineApp`, not here: the app binds it with `priority=True`,
    # which beats any screen binding, so a copy on this class would be dead code pretending to work.

    # A touch player's only way off a screen. It does one thing everywhere: go back one screen.
    # It did send Escape, so that each screen could keep its own meaning for leaving — but that gave
    # one button several behaviours, and a menu read it as one of its own items.
    BACK_ID = "tc-back"

    # What the page's Back button actually sends (see `serve._back_overlay`). NOT Escape: Escape is
    # a key each screen gives its own meaning, and on the temple that meaning is "leave the run for
    # the main menu". A button whose only guard was hiding itself therefore abandoned a live run
    # whenever a tap beat the hide — the announcement is a round trip behind the finger.
    #
    # This key has one meaning everywhere, and `on_key` re-checks the guard at the moment it
    # arrives, so the authority is here and not in a copy the page holds.
    #
    # Shift+F5 is not an aesthetic choice. The obvious pick was F24 — no keyboard has one, so no
    # player could press it — but xterm.js does not encode F13 and up AT ALL: the button went dead
    # silently, hiding itself on a tap that never reached the app. Measured, not assumed. Of the
    # keys that do survive the terminal, this one is unreachable in practice: a browser eats Shift+F5
    # as a reload before the page ever sees it, so only the button can send it.
    BACK_KEY = "shift+f5"

    # A screen sets this False when going back from it would abandon something — the game's hub, where
    # Back would drop a live run at the main menu. Depth alone cannot tell that apart from the Lore
    # book, which sits at the same depth and *should* go back.
    BACK_ALLOWED = True

    # Put the button at the bottom-RIGHT instead of following the panel's left edge. For a screen
    # whose panel ends in a line of its own — the Lore book's page counter — the left corner is
    # already spoken for, and the button sat on top of it.
    BACK_RIGHT = False

    # Wide enough for "◀ Back" and its padding. Fixed, because the right-hand placement has to be
    # computed before Textual has measured the button.
    BACK_WIDTH = 20

    def announce_back(self) -> None:
        """Tell the PAGE whether this screen has a way back, so its Back button can hide itself.

        The button lives in the browser (see `serve._back_overlay`) and cannot know which screen is
        showing — it appeared on the main menu, where there is nothing to leave, and mid-duel, where
        Escape means Retreat and a committed showdown refuses. This is the same meta channel Textual
        already uses for `open_url`: app -> textual-serve -> browser.
        """
        driver = getattr(self.app, "_driver", None)
        write_meta = getattr(driver, "write_meta", None)
        if write_meta is None:  # a real terminal: it has an Escape key and needs none of this
            return
        allowed = self.BACK_ALLOWED and len(self.app.screen_stack) > 2
        write_meta({"type": "termcade_back", "allowed": bool(allowed)})

    def hide_back(self) -> None:
        """Take the way back away for good, for a screen that stops offering one partway through —
        a duel, once the showdown is committed and Retreat starts refusing. The page's button hides
        on the next announcement."""
        self.BACK_ALLOWED = False
        self.announce_back()

    def on_screen_resume(self) -> None:
        self.announce_back()

    def on_key(self, event: events.Key) -> None:
        """Answer the page's Back button — and only if going back is allowed *now*.

        Dispatch walks the MRO, so this runs on screens that define their own ``on_key`` too. The
        guard is deliberately the same expression `announce_back` sends to the page: the page's copy
        decides whether the button is *drawn*, this one decides whether it *acts*, and a burst of
        taps arriving before the page has caught up is refused here rather than obeyed.
        """
        if event.key != self.BACK_KEY:
            return
        event.stop()
        event.prevent_default()
        if self.BACK_ALLOWED and len(self.app.screen_stack) > 2:
            self.page_back()

    def page_back(self) -> None:
        """What this screen does when the page's Back button is pressed. Popping, by default.

        Overridable because popping is not always what going back MEANS. A duel *replaces* the
        temple rather than stacking on it, so popping one lands on the main menu and throws the run
        away — there, back means Retreat. That distinction used to live in a handler for the Back
        *widget*, which no longer exists, so the page button walked straight past it.
        """
        self.app.pop_screen()

    def on_mount(self) -> None:
        # Dispatch walks the MRO, so this runs even on a screen that defines its own `on_mount`.
        #
        # `-touch` says the player is on a phone. The width breakpoints cannot: a phone in landscape
        # reports 154 columns — wider than a laptop — while having only 36 rows, so `-narrow` never
        # fires there and the desktop layout lands on a 6cm screen. The device tells us instead.
        if os.environ.get(TOUCH_ENV):
            self.add_class("-touch")
        self._mount_back()
        self.call_after_refresh(self.announce_back)

    def _mount_back(self) -> None:
        # The touch Back button lives in the PAGE now (see `serve._back_overlay`), fixed to the
        # viewport. Inside the grid it scrolled away with the terminal whenever the font was large
        # enough to read. Kept as a no-op rather than torn out: `hide_back` and `BACK_ALLOWED` are
        # still the contract a screen uses to say it has no way back.
        return
        if not os.environ.get(TOUCH_ENV) or self.query(f"#{self.BACK_ID}"):  # noqa: F841
            return
        # Nothing underneath to return to on the game's own root screen ([default, root]).
        if len(self.app.screen_stack) <= 2 or not self.BACK_ALLOWED:
            return
        # Before the Footer, not after it: both dock to the bottom and docked widgets stack in DOM
        # order, so mounting last put the button *on* the footer's row instead of above it.
        # Mounting rather than composing keeps every screen's own `compose` untouched — this has to
        # hold for screens the cartridge defines too.
        back = Button("◀ Back", id=self.BACK_ID, classes="tc-back")
        footer = self.query(Footer)
        if footer:
            self.mount(back, before=footer.first())
        else:
            self.mount(back)
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == self.BACK_ID:
            event.stop()
            self.app.pop_screen()

    def rebuild(self) -> None:
        """Recompose the screen — and put its footer back.

        **Never call `refresh(recompose=True)` directly on a screen with a `Footer`.** Recomposing
        tears the Footer down and builds a new one, and the new one comes up *empty*: it fills itself
        from the screen's bindings when it mounts, and at that moment there are none to read. Every key
        the screen offers silently vanishes from the bottom of the terminal — the screen still works,
        it just stops telling anyone how.

        `refresh_bindings` after the recompose is what refills it. Deferred, because the new Footer does
        not exist yet at the moment we ask.
        """
        self.refresh(recompose=True)
        self.call_after_refresh(self.refresh_bindings)
        # A recompose builds the screen from its own `compose`, which knows nothing about the Back
        # button — so it has to be put back, or a touch player loses the way out on the first rebuild.
        self.call_after_refresh(self._mount_back)

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        """A worker that died takes its error to the player, not to the void.

        This lives on the *screen* and not on the app because `Worker.StateChanged` **does not bubble**
        — it is delivered only to the node that started the worker. An app-level handler looks right,
        compiles, and never fires; that is exactly the trap this base class exists to close, since every
        screen in the engine and in every cartridge inherits it.
        """
        if event.state is not WorkerState.ERROR:
            return
        error = event.worker.error
        if error is None:  # cancelled, not crashed
            return
        cast("EngineApp", self.app).report_crash(error, where=event.worker.name)

    @property
    def engine_app(self) -> "EngineApp":
        """`self.app` narrowed to the engine's App, for its extras — the journalling
        ``notify(log=...)``, ``report_crash``. Textual types `app` as the base `App`."""
        return cast("EngineApp", self.app)

    @property
    def ctx(self) -> GameContext:
        ctx = cast("EngineApp", self.app).ctx
        assert ctx is not None, "screen has no GameContext (running without a Game)"
        return ctx

    @property
    def game(self) -> Game:
        game = cast("EngineApp", self.app).game
        assert game is not None, "screen has no Game"
        return game

    async def choose(
        self,
        prompt: "ContentText | Text",
        options: Sequence[tuple[ContentText, _T]],
        *,
        title: str | None = None,
    ) -> _T:
        """Ask the player to pick one option; resolves with the value behind their choice."""
        return await self.app.push_screen_wait(ChoiceModal(prompt, options, title=title))

    async def confirm(
        self,
        prompt: "ContentText | Text",
        *,
        title: str | None = None,
        yes: str = "Yes",
        no: str = "No",
    ) -> bool:
        """A yes/no dialog; resolves ``True`` if the player takes the ``yes`` option.

        A **rich** prompt, not only a string: a game asking about a *card* has to be able to show it —
        coloured by its element and carrying its stats — rather than flattening it into a sentence.
        """
        return await self.app.push_screen_wait(
            ChoiceModal(prompt, [(yes, True), (no, False)], title=title)
        )

    async def show_message(
        self, message: "ContentText | Text", *, title: str | None = None, ok: str = "Continue"
    ) -> None:
        """A single-button acknowledgement; resolves once the player dismisses it."""
        await self.app.push_screen_wait(ChoiceModal(message, [(ok, None)], title=title))
