"""``SaveSlotScreen`` — the engine's reusable save/load slot picker (menu-only saves).

Driven entirely by the ``SaveManager`` on the context, so any game reuses it. It performs the
save or load against the context (generic) and hands navigation back to the caller: on load it
switches to an injected ``next_screen`` factory (the game's play screen), staying UI-neutral so
this module never imports a game.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Static

from termcade.core.state import GameState
from termcade.ui.widgets import BoxedPanel

from .base import EngineScreen

Mode = Literal["save", "load"]


class SaveSlotScreen(EngineScreen):
    BINDINGS = [("escape", "app.pop_screen", "Cancel")]

    def __init__(
        self,
        mode: Mode,
        *,
        title: str = "Save",
        next_screen: Callable[[], Screen] | None = None,
    ) -> None:
        super().__init__()
        self._mode = mode
        self._title = title
        self._next_screen = next_screen

    def compose(self) -> ComposeResult:
        heading = "SAVE" if self._mode == "save" else "LOAD"
        yield Header()
        with BoxedPanel(title=heading):
            yield Static("Select a slot", classes="panel-desc")
            for slot, meta in enumerate(self.ctx.saves.list()):
                if meta is None:
                    label = f"{slot + 1}.  — empty —"
                    disabled = self._mode == "load"  # nothing to restore
                else:
                    label = f"{slot + 1}.  {meta.title}"
                    disabled = False
                yield Button(label, id=f"slot-{slot}", disabled=disabled)
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        assert event.button.id is not None
        slot = int(event.button.id.removeprefix("slot-"))
        if self._mode == "save":
            self._save(slot)
        else:
            self._load(slot)

    def _save(self, slot: int) -> None:
        state = self.ctx.state
        assert state is not None, "nothing to save — no active game state"
        self.ctx.saves.save(
            slot, state, self.ctx.rng, title=self._title, settings=self.ctx.settings.current
        )
        self.app.pop_screen()

    def _load(self, slot: int) -> None:
        state_cls: type[GameState] = self.ctx.game.state_cls
        state, rng, _meta, _settings = self.ctx.saves.load(slot, state_cls, self.ctx)
        self.ctx.state = state
        self.ctx.rng = rng
        if self._next_screen is not None:
            self.app.switch_screen(self._next_screen())
        else:
            self.app.pop_screen()
