"""Base screen ("scene") shared by engine and game screens."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar, cast

from textual.screen import Screen

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

    async def choose(self, prompt: str, options: list[tuple[str, _T]], *, title: str | None = None) -> _T:
        """Ask the player to pick one option; resolves with the value behind their choice."""
        return await self.app.push_screen_wait(ChoiceModal(prompt, options, title=title))

    async def confirm(
        self, prompt: str, *, title: str | None = None, yes: str = "Yes", no: str = "No"
    ) -> bool:
        """A yes/no dialog; resolves ``True`` if the player takes the ``yes`` option."""
        return await self.app.push_screen_wait(
            ChoiceModal(prompt, [(yes, True), (no, False)], title=title)
        )

    async def show_message(self, message: str, *, title: str | None = None, ok: str = "Continue") -> None:
        """A single-button acknowledgement; resolves once the player dismisses it."""
        await self.app.push_screen_wait(ChoiceModal(message, [(ok, None)], title=title))
