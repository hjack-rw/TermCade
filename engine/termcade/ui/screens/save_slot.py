"""``SaveSlotScreen`` — the engine's reusable save/load slot picker (menu-only saves).

Driven entirely by the ``SaveManager`` on the context, so any game reuses it. It performs the
save or load against the context (generic) and hands navigation back to the caller: on load it
switches to an injected ``next_screen`` factory (the game's play screen), staying UI-neutral so
this module never imports a game.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from textual.screen import Screen

from termcade.core.saves import SaveError
from termcade.core.state import GameState

from .menu import MenuItem, MenuScreen

Mode = Literal["save", "load"]


class SaveSlotScreen(MenuScreen):
    BINDINGS = [("escape", "app.pop_screen", "Cancel")]
    menu_description = "Select a slot"

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
        self.menu_title = "SAVE" if mode == "save" else "LOAD"

    def menu_items(self) -> list[MenuItem]:
        items = []
        for slot, meta in enumerate(self.ctx.saves.list()):
            if meta is None:
                # An empty slot can't be loaded from, but is a valid save target.
                items.append(MenuItem(f"slot-{slot}", f"{slot + 1}.  — empty —", disabled=self._mode == "load"))
            else:
                items.append(MenuItem(f"slot-{slot}", f"{slot + 1}.  {meta.title}"))
        return items

    def on_select(self, item_id: str) -> None:
        slot = int(item_id.removeprefix("slot-"))
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
        try:
            state, rng, _meta, _settings = self.ctx.saves.load(slot, state_cls, self.ctx)
        except SaveError as e:
            # A corrupt or unreadable save must not crash the picker — flag it and stay put.
            self.app.notify(str(e), title="Load failed", severity="error")
            return
        self.ctx.state = state
        self.ctx.rng = rng
        if self._next_screen is not None:
            self.app.switch_screen(self._next_screen())
        else:
            self.app.pop_screen()
