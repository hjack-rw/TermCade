"""Save round-trips through each SaveBackend, plus SaveManager guards.

Every behavioural test runs against both backends (parametrized ``backend``
fixture), so the JSON and SQLite stores are proven interchangeable. The final
test pins the DB-only property: metadata lives in queryable columns.
"""

from __future__ import annotations

import sqlite3

import pytest

from termcade.core.rng import Rng
from termcade.core.saves import (
    JsonFileBackend,
    SaveManager,
    SavesDisabled,
    SlotEmpty,
    SlotOutOfRange,
    SqliteBackend,
)


@pytest.fixture(params=["json", "sqlite"])
def backend(request, tmp_path):
    if request.param == "json":
        return JsonFileBackend(tmp_path / "saves")
    return SqliteBackend(tmp_path / "saves.db")


def _manager(backend, **kwargs):
    return SaveManager("demo", backend, **kwargs)


def test_save_load_round_trip(backend, fake_state_cls):
    mgr = _manager(backend)
    rng = Rng("alpha")
    rng.randint(1, 100)  # advance the stream before it is snapshotted
    state = fake_state_cls(schema_version=2, points=42, hand=["one", "two"])

    meta = mgr.save(0, state, rng, title="round one")
    assert meta.slot == 0
    assert meta.game_id == "demo"

    loaded, loaded_rng, loaded_meta = mgr.load(0, fake_state_cls, ctx=None)
    assert loaded.points == 42
    assert loaded.hand == ["one", "two"]
    assert loaded_meta.title == "round one"
    assert loaded_meta.schema_version == 2
    # RNG resumes the exact stream across a JSON round-trip.
    assert loaded_rng.get_state() == rng.get_state()
    assert loaded_rng.randint(1, 100) == rng.randint(1, 100)


def test_list_reports_holes_as_none(backend, fake_state_cls):
    mgr = _manager(backend, max_slots=4)
    mgr.save(1, fake_state_cls(points=1), Rng(1), title="one")
    mgr.save(3, fake_state_cls(points=3), Rng(3), title="three")

    listing = mgr.list()
    assert len(listing) == 4
    assert listing[0] is None
    assert listing[2] is None
    assert listing[1].title == "one"
    assert listing[3].title == "three"


def test_overwrite_same_slot(backend, fake_state_cls):
    mgr = _manager(backend)
    mgr.save(0, fake_state_cls(points=1), Rng(1), title="first")
    mgr.save(0, fake_state_cls(points=2), Rng(2), title="second")

    loaded, _, meta = mgr.load(0, fake_state_cls, ctx=None)
    assert loaded.points == 2
    assert meta.title == "second"
    assert mgr.list().count(None) == mgr.max_slots - 1


def test_delete_frees_slot(backend, fake_state_cls):
    mgr = _manager(backend)
    mgr.save(0, fake_state_cls(points=1), Rng(1), title="x")
    mgr.delete(0)
    assert backend.exists(0) is False
    assert mgr.list()[0] is None


def test_disabled_saves_are_guarded(backend, fake_state_cls):
    mgr = _manager(backend, saves_enabled=False)
    with pytest.raises(SavesDisabled):
        mgr.save(0, fake_state_cls(), Rng(1), title="x")


def test_slot_out_of_range_is_guarded(backend, fake_state_cls):
    mgr = _manager(backend, max_slots=2)
    with pytest.raises(SlotOutOfRange):
        mgr.save(5, fake_state_cls(), Rng(1), title="x")


def test_read_missing_slot_raises_slot_empty(backend):
    with pytest.raises(SlotEmpty):
        backend.read(0)


def test_sqlite_stores_metadata_in_queryable_columns(tmp_path, fake_state_cls):
    """The DB's edge over files: metadata is real SQL, not an opaque blob."""
    db = tmp_path / "saves.db"
    mgr = _manager(SqliteBackend(db))
    mgr.save(0, fake_state_cls(points=7), Rng("seed"), title="queryable")

    with sqlite3.connect(db) as conn:
        title = conn.execute("SELECT title FROM saves WHERE slot = 0").fetchone()[0]
    assert title == "queryable"
