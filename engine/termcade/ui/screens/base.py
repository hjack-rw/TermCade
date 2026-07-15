"""Base screen ("scene") shared by engine and game screens."""

from __future__ import annotations

from collections.abc import Sequence

from typing import TYPE_CHECKING, TypeVar, cast

from rich.text import Text
from textual.content import ContentText
from textual.screen import Screen
from textual.worker import Worker, WorkerState

from termcade.app.game import Game, GameContext

from .dialog import ChoiceModal

if TYPE_CHECKING:
    from ..app import EngineApp

_T = TypeVar("_T")


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
