"""``SaveSlotScreen`` — the engine's reusable save/load slot picker (menu-only saves).

Driven entirely by the ``SaveManager`` on the context, so any game reuses it. It performs the
save or load against the context (generic) and hands navigation back to the caller: on load it
switches to an injected ``next_screen`` factory (the game's play screen), staying UI-neutral so
this module never imports a game.

Loading also offers a per-slot ``✕`` that deletes that save (after confirming) — deleting is a thing
you do *to* a slot you can see, so it needs no screen of its own.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from termcade.app.game import SaveNote
from termcade.ui.work import work
from textual.screen import Screen

from termcade.core.saves import SaveError
from termcade.core.state import GameState

from .menu import MenuItem, MenuScreen

Mode = Literal["save", "load"]

DELETE_GLYPH = "✕"  # text-presentation, so it stays monochrome like the rest of the icons


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

    def _note_for(self, slot: int) -> SaveNote | None:
        """What the cartridge wants said about this save, if anything."""
        note = self.game.save_note
        if note is None:
            return None
        frozen = self.ctx.saves.settings_of(slot)
        return note(frozen) if frozen is not None else None

    def menu_items(self) -> list[MenuItem]:
        items = []
        for slot, meta in enumerate(self.ctx.saves.list()):
            tooltip: str | None = None
            # `list()` hides an unreadable save as a hole, so ask the store whether the slot is
            # really free — otherwise a corrupt save could never be seen, let alone deleted.
            occupied = meta is not None or self.ctx.saves.exists(slot)
            if meta is not None:
                label = f"{slot + 1}.  {meta.title}"
                note = self._note_for(slot)
                if note:
                    # A save keeps the rules it was frozen with, and nothing else on this screen would
                    # tell a player those are not the rules a new run gets. The mark is small enough to
                    # ignore and the tooltip says what it means — the cartridge writes both.
                    label = f"{label}  {note.mark}"
                    tooltip = note.explanation
            elif occupied:
                label = f"{slot + 1}.  — unreadable save —"
            else:
                label = f"{slot + 1}.  — empty —"
            items.append(
                MenuItem(
                    f"slot-{slot}",
                    label,
                    # An empty slot is a valid save target, but there's nothing there to load.
                    disabled=not occupied and self._mode == "load",
                    # Only an occupied slot can be cleared, and only while loading — the save picker
                    # is reached mid-game, where a stray click shouldn't destroy a run.
                    action_id=f"del-{slot}" if occupied and self._mode == "load" else None,
                    action_label=DELETE_GLYPH,
                    tooltip=tooltip,
                )
            )
        return items

    def on_select(self, item_id: str) -> None:
        if item_id.startswith("del-"):
            self._delete(int(item_id.removeprefix("del-")))
            return
        slot = int(item_id.removeprefix("slot-"))
        if self._mode == "save":
            self._save(slot)
        else:
            self._load(slot)

    @work
    async def _delete(self, slot: int) -> None:
        if not await self.confirm(
            f"Delete the save in slot {slot + 1}? This cannot be undone.",
            title="DELETE SAVE",
            yes="Yes, delete it",
            no="Keep it",
        ):
            return
        self.ctx.saves.delete(slot)
        self.app.notify(f"Slot {slot + 1} deleted.")
        self.rebuild()  # the freed slot shows as empty at once (and the footer survives it)

    def _save(self, slot: int) -> None:
        state = self.ctx.state
        assert state is not None, "nothing to save — no active game state"
        self.ctx.saves.save(
            slot,
            state,
            self.ctx.rng,
            title=self._title,
            settings=self.ctx.settings.current,
            journal=self.ctx.journal,
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
        self.ctx.state = state  # empties the journal — a new state is a new run
        self.ctx.rng = rng
        # ...then refill the log from the save, so the loaded run opens on what happened, not a blank.
        saved_journal = self.ctx.saves.journal_of(slot)
        if saved_journal is not None:
            self.ctx.journal.restore(saved_journal)
        if self._next_screen is not None:
            self.app.switch_screen(self._next_screen())
        else:
            self.app.pop_screen()
