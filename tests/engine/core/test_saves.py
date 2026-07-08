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
    SaveCorrupt,
    SaveManager,
    SavesDisabled,
    SlotEmpty,
    SlotOutOfRange,
    SqliteBackend,
)
from termcade.core.settings import Difficulty, Settings


@pytest.fixture(params=["json", "sqlite"])
def backend(request, tmp_path):
    if request.param == "json":
        return JsonFileBackend(tmp_path / "saves")
    return SqliteBackend(tmp_path / "saves.db")


def _manager(backend, **kwargs):
    return SaveManager("demo", backend, **kwargs)


def test_save_load_round_trip(backend, fake_state_cls):
    mgr = _manager(backend)
    state = fake_state_cls(schema_version=2, points=42, hand=["one", "two"])

    meta = mgr.save(0, state, Rng("alpha"), title="round one")
    assert meta.slot == 0
    assert meta.game_id == "demo"

    loaded, _rng, loaded_meta, _settings = mgr.load(0, fake_state_cls, ctx=None)
    assert loaded.points == 42
    assert loaded.hand == ["one", "two"]
    assert loaded_meta.title == "round one"
    assert loaded_meta.schema_version == 2


def test_rng_stream_resumes_after_load(backend, fake_state_cls):
    mgr = _manager(backend)
    rng = Rng("alpha")
    rng.randint(1, 100)  # advance so the saved RNG state is non-trivial

    mgr.save(0, fake_state_cls(), rng, title="x")
    _state, loaded_rng, _meta, _settings = mgr.load(0, fake_state_cls, ctx=None)

    assert loaded_rng.get_state() == rng.get_state()
    assert loaded_rng.randint(1, 100) == rng.randint(1, 100)  # same next draw


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

    loaded, _, meta, _settings = mgr.load(0, fake_state_cls, ctx=None)
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


def test_read_meta_returns_meta_without_the_payload(backend, fake_state_cls):
    mgr = _manager(backend)
    mgr.save(0, fake_state_cls(points=7, hand=["a"]), Rng("seed"), title="meta only")

    meta = backend.read_meta(0)
    assert meta["title"] == "meta only"
    assert meta["slot"] == 0
    assert {"state", "rng", "settings"}.isdisjoint(meta)  # listing never pulls the state blob


def test_read_meta_missing_slot_raises_slot_empty(backend):
    with pytest.raises(SlotEmpty):
        backend.read_meta(0)


def test_settings_are_frozen_into_the_save(backend, fake_state_cls):
    mgr = _manager(backend)
    frozen = Settings(difficulty=Difficulty.HARD, options={"point_limit": 20})
    mgr.save(0, fake_state_cls(), Rng(1), title="ruled", settings=frozen)

    _state, _rng, _meta, loaded = mgr.load(0, fake_state_cls, ctx=None)
    assert loaded.difficulty is Difficulty.HARD
    assert loaded.options["point_limit"] == 20


def test_load_fills_new_defaults_over_frozen_settings(backend, fake_state_cls):
    """A save made before a new option existed still loads, with the new default filled in."""
    mgr = _manager(backend)
    mgr.save(0, fake_state_cls(), Rng(1), title="old", settings=Settings(options={"point_limit": 20}))

    # A later version's defaults carry a knob the save never had.
    class Game:
        default_settings = Settings(options={"point_limit": 13, "hand_size": 6})

    class Ctx:
        game = Game()

    _state, _rng, _meta, loaded = mgr.load(0, fake_state_cls, ctx=Ctx())
    assert loaded.options["point_limit"] == 20  # the save wins where it had a value
    assert loaded.options["hand_size"] == 6  # the new default fills the gap


def test_sqlite_read_raises_save_corrupt_on_bad_payload(tmp_path, fake_state_cls):
    """A row whose payload JSON is garbage surfaces as SaveCorrupt, not a raw JSONDecodeError."""
    db = tmp_path / "saves.db"
    mgr = _manager(SqliteBackend(db))
    mgr.save(0, fake_state_cls(), Rng(1), title="x")
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE saves SET payload = 'not json' WHERE slot = 0")

    with pytest.raises(SaveCorrupt):
        SqliteBackend(db).read(0)


def test_list_skips_a_corrupt_slot_instead_of_crashing(tmp_path, fake_state_cls):
    """One unreadable save must not blank the picker — the good slots still list."""
    root = tmp_path / "saves"
    backend = JsonFileBackend(root)
    mgr = _manager(backend, max_slots=3)
    mgr.save(0, fake_state_cls(points=1), Rng(1), title="good")
    mgr.save(1, fake_state_cls(points=2), Rng(2), title="doomed")
    (root / "slot_1.json").write_text("{ broken", encoding="utf-8")

    listing = mgr.list()
    assert listing[0].title == "good"  # survivor still listed
    assert listing[1] is None  # corrupt slot shows as a hole, no exception
    """The DB's edge over files: metadata is real SQL, not an opaque blob."""
    db = tmp_path / "saves.db"
    mgr = _manager(SqliteBackend(db))
    mgr.save(0, fake_state_cls(points=7), Rng("seed"), title="queryable")

    with sqlite3.connect(db) as conn:
        title = conn.execute("SELECT title FROM saves WHERE slot = 0").fetchone()[0]
    assert title == "queryable"
