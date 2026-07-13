"""Save-slot manager and its storage backends.

Menu-only by design: saving happens between runs, never mid-duel. A game can
disable saving entirely or cap the slot count. The on-disk envelope is
``{meta, rng, settings, state}``: the run's settings are frozen into the save so it
remembers the ruleset it was created with. The engine never inspects the ``state`` payload.

``SaveManager`` depends on the ``SaveBackend`` protocol, not a concrete store, so
the storage medium is swappable: ``JsonFileBackend`` (one file per slot) and
``SqliteBackend`` (one indexed row per slot) both satisfy it.
"""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import closing
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from .rng import Rng
from .settings import Settings
from .state import GameState, SaveMeta

if TYPE_CHECKING:
    from termcade.app.game import GameContext


class SaveError(Exception):
    pass


class SavesDisabled(SaveError):
    pass


class SlotOutOfRange(SaveError):
    pass


class SlotEmpty(SaveError):
    """Raised when reading a slot that holds no save. Same across all backends."""


class SaveCorrupt(SaveError):
    """A slot holds data that can't be parsed (bad JSON, malformed meta). The row exists but is
    unreadable — distinct from :class:`SlotEmpty`. Backends raise this instead of leaking a raw
    ``JSONDecodeError``/``ValueError``, so callers catch one save-domain type."""


@runtime_checkable
class SaveBackend(Protocol):
    """Storage seam for save slots.

    Moves the ``{meta, rng, settings, state}`` envelope in and out, keyed by slot. The
    implementation owns the medium (files, SQLite, …); none of them inspect the
    ``state`` payload. ``SaveManager`` depends on this, never on a concrete store.
    """

    def write(self, slot: int, envelope: dict[str, Any]) -> None: ...

    def read(self, slot: int) -> dict[str, Any]: ...

    def read_meta(self, slot: int) -> dict[str, Any]:
        """Return just the ``meta`` block for a slot — no payload. Lets listing skip the state blob."""
        ...

    def delete(self, slot: int) -> None: ...

    def exists(self, slot: int) -> bool: ...

    def list_slots(self) -> list[int]: ...


class JsonFileBackend:
    """One JSON file per slot: ``<root>/slot_<n>.json``.

    Human-readable and dependency-free — kept for inspecting/debugging saves.
    ``SqliteBackend`` is the default store; this satisfies the same protocol.
    """

    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, slot: int) -> Path:
        return self._root / f"slot_{slot}.json"

    def write(self, slot: int, envelope: dict[str, Any]) -> None:
        # Atomic: fill a sibling temp file, then os.replace it into place, so an
        # interrupted write can never truncate an existing save.
        path = self._path(slot)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(envelope, indent=2), encoding="utf-8")
        os.replace(tmp, path)

    def read(self, slot: int) -> dict[str, Any]:
        path = self._path(slot)
        if not path.exists():
            raise SlotEmpty(f"no save in slot {slot}")
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise SaveCorrupt(f"save in slot {slot} is unreadable: {e}") from e

    def read_meta(self, slot: int) -> dict[str, Any]:
        # The file is one blob — meta lives inside it, so there's no cheaper path than a full read.
        try:
            return self.read(slot)["meta"]
        except KeyError as e:
            raise SaveCorrupt(f"save in slot {slot} has no meta block") from e

    def delete(self, slot: int) -> None:
        self._path(slot).unlink(missing_ok=True)

    def exists(self, slot: int) -> bool:
        return self._path(slot).exists()

    def list_slots(self) -> list[int]:
        return sorted(int(p.stem.removeprefix("slot_")) for p in self._root.glob("slot_*.json"))


class SqliteBackend:
    """One indexed row per slot in a single SQLite database (``saves.db``).

    Save *metadata* lands in real columns, so listing and lookups are SQL rather
    than a directory scan. Everything else in the envelope (``rng``, ``settings``,
    ``state``, and any future key) rides in one opaque JSON ``payload`` column, so
    the envelope can grow without a schema change. Uses only the stdlib ``sqlite3``.
    """

    _META_COLUMNS = "slot, game_id, title, schema_version, seed, saved_at"
    _COLUMNS = f"{_META_COLUMNS}, payload"

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS saves (
                    slot           INTEGER PRIMARY KEY,
                    game_id        TEXT    NOT NULL,
                    title          TEXT    NOT NULL,
                    schema_version INTEGER NOT NULL,
                    seed           TEXT    NOT NULL,  -- 64-bit unsigned; TEXT dodges SQLite's signed cap
                    saved_at       TEXT    NOT NULL,
                    payload        TEXT    NOT NULL  -- {rng, settings, state, …} as JSON
                )
                """
            )
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path)

    def write(self, slot: int, envelope: dict[str, Any]) -> None:
        meta = envelope["meta"]
        # Meta lands in indexed columns; everything else rides in one JSON payload,
        # so a new envelope key needs no schema change.
        payload = {key: value for key, value in envelope.items() if key != "meta"}
        row = (
            slot,
            meta["game_id"],
            meta["title"],
            meta["schema_version"],
            str(meta["seed"]),
            meta["saved_at"],
            json.dumps(payload),
        )
        with closing(self._connect()) as conn:
            conn.execute(
                f"INSERT INTO saves ({self._COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(slot) DO UPDATE SET "
                "game_id=excluded.game_id, title=excluded.title, "
                "schema_version=excluded.schema_version, seed=excluded.seed, "
                "saved_at=excluded.saved_at, payload=excluded.payload",
                row,
            )
            conn.commit()

    @staticmethod
    def _meta_from_row(row: tuple[Any, ...]) -> dict[str, Any]:
        # Row shape is the _META_COLUMNS order, which _COLUMNS extends — so this reads both.
        return {
            "slot": row[0],
            "game_id": row[1],
            "title": row[2],
            "schema_version": row[3],
            "seed": int(row[4]),  # stored as TEXT (64-bit unsigned); back to int here
            "saved_at": row[5],
        }

    def read(self, slot: int) -> dict[str, Any]:
        with closing(self._connect()) as conn:
            row = conn.execute(
                f"SELECT {self._COLUMNS} FROM saves WHERE slot = ?", (slot,)
            ).fetchone()
        if row is None:
            raise SlotEmpty(f"no save in slot {slot}")
        try:
            envelope: dict[str, Any] = json.loads(row[6])
            envelope["meta"] = self._meta_from_row(row)
        except (json.JSONDecodeError, ValueError) as e:
            raise SaveCorrupt(f"save in slot {slot} is unreadable: {e}") from e
        return envelope

    def read_meta(self, slot: int) -> dict[str, Any]:
        # Meta-only: select the indexed columns and never touch the payload blob.
        with closing(self._connect()) as conn:
            row = conn.execute(
                f"SELECT {self._META_COLUMNS} FROM saves WHERE slot = ?", (slot,)
            ).fetchone()
        if row is None:
            raise SlotEmpty(f"no save in slot {slot}")
        try:
            return self._meta_from_row(row)
        except ValueError as e:
            raise SaveCorrupt(f"save in slot {slot} has malformed meta: {e}") from e

    def delete(self, slot: int) -> None:
        with closing(self._connect()) as conn:
            conn.execute("DELETE FROM saves WHERE slot = ?", (slot,))
            conn.commit()

    def exists(self, slot: int) -> bool:
        with closing(self._connect()) as conn:
            found = conn.execute("SELECT 1 FROM saves WHERE slot = ?", (slot,)).fetchone()
        return found is not None

    def list_slots(self) -> list[int]:
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT slot FROM saves ORDER BY slot").fetchall()
        return [int(r[0]) for r in rows]


class SaveManager:
    def __init__(
        self,
        game_id: str,
        backend: SaveBackend,
        *,
        saves_enabled: bool = True,
        max_slots: int = 6,
    ) -> None:
        self.game_id = game_id
        self._backend = backend
        self._enabled = saves_enabled
        self._max_slots = max_slots

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def max_slots(self) -> int:
        return self._max_slots

    def _guard(self, slot: int) -> None:
        if not self._enabled:
            raise SavesDisabled(f"saving is disabled for {self.game_id}")
        if not 0 <= slot < self._max_slots:
            raise SlotOutOfRange(f"slot {slot} outside 0..{self._max_slots - 1}")

    def save(
        self,
        slot: int,
        state: GameState,
        rng: Rng,
        *,
        title: str,
        settings: Settings | None = None,
    ) -> SaveMeta:
        self._guard(slot)
        meta = SaveMeta(
            slot=slot,
            game_id=self.game_id,
            title=title,
            schema_version=state.schema_version,
            seed=rng.seed,
            saved_at=datetime.now(timezone.utc).isoformat(),
        )
        envelope = {
            "meta": asdict(meta),
            "rng": rng.get_state(),
            "settings": settings.to_dict() if settings is not None else {},
            "state": state.snapshot(),
        }
        self._backend.write(slot, envelope)
        return meta

    def load(
        self, slot: int, state_cls: type[GameState], ctx: "GameContext"
    ) -> tuple[GameState, Rng, SaveMeta, Settings]:
        self._guard(slot)
        envelope = self._backend.read(slot)
        meta = SaveMeta(**envelope["meta"])
        rng = Rng(meta.seed)
        rng.set_state(envelope["rng"])
        # The save's frozen settings win, merged over the game's current defaults so an
        # option added since the save is filled in (forward-compatible).
        defaults = ctx.game.default_settings if ctx is not None else Settings()
        settings = Settings.from_dict(envelope.get("settings", {}), defaults)
        state = state_cls.restore(envelope["state"], ctx)
        return state, rng, meta, settings

    def settings_of(self, slot: int) -> Settings | None:
        """The rules a saved run was dealt under — read without restoring the run itself.

        A save freezes its settings on purpose: that run *is* that game, and loading it must not
        retro-fit rules it was never played by. But then nothing tells a player their old save is a
        different game from the one a new run would deal — the pile was smaller, the target was lower,
        and the run will feel wrong for a reason they cannot see. This is what lets the slot say so.
        """
        if not self._enabled or not self._backend.exists(slot):
            return None
        envelope = self._backend.read(slot)
        frozen = envelope.get("settings")
        if not frozen:
            return None
        return Settings.from_dict(frozen, Settings())

    def list(self) -> list[SaveMeta | None]:
        """One entry per slot; ``None`` for an empty slot. Length == ``max_slots``."""
        slots: list[SaveMeta | None] = [None] * self._max_slots
        if not self._enabled:
            return slots
        for slot in self._backend.list_slots():
            if 0 <= slot < self._max_slots:
                try:
                    slots[slot] = SaveMeta(**self._backend.read_meta(slot))
                except SaveError:
                    # A single unreadable slot must not blank the whole picker — leave it as a
                    # hole so the other saves still list (and the slot can be overwritten).
                    slots[slot] = None
        return slots

    def exists(self, slot: int) -> bool:
        """Does the slot hold anything at all — even something unreadable?

        ``list()`` reports a corrupt slot as a hole, so a delete screen that trusted it could never
        clear the one save the player most wants gone. This asks the backend directly.
        """
        if not self._enabled or not 0 <= slot < self._max_slots:
            return False
        return self._backend.exists(slot)

    def delete(self, slot: int) -> None:
        self._guard(slot)
        self._backend.delete(slot)
