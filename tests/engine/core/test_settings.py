"""Settings persistence and the forward-compatible merge.

The invariant under test: a settings file written by an older version still loads
after the game adds a new option — the new default fills the gap, the file's own
values win where they exist.
"""

from __future__ import annotations

import json

from termcade.core.settings import Difficulty, Settings, SettingsStore


def test_from_dict_fills_new_default_absent_from_old_file():
    defaults = Settings(difficulty=Difficulty.NORMAL, options={"sound": True, "colorblind": False})
    old_file = {"difficulty": "hard", "options": {"sound": False}}  # no "colorblind" key yet

    merged = Settings.from_dict(old_file, defaults)

    assert merged.difficulty is Difficulty.HARD   # file wins where present
    assert merged.options["sound"] is False       # file wins where present
    assert merged.options["colorblind"] is False  # new default fills the gap


def test_from_dict_uses_default_difficulty_when_absent():
    merged = Settings.from_dict({"options": {}}, Settings(difficulty=Difficulty.EASY))
    assert merged.difficulty is Difficulty.EASY


def test_store_round_trip(tmp_path):
    path = tmp_path / "settings.json"
    SettingsStore(path, Settings()).save(
        Settings(difficulty=Difficulty.HARD, options={"sound": False})
    )

    reloaded = SettingsStore(path, Settings()).load()
    assert reloaded.difficulty is Difficulty.HARD
    assert reloaded.options == {"sound": False}


def test_load_missing_file_returns_defaults_without_aliasing(tmp_path):
    defaults = Settings(difficulty=Difficulty.HARD, options={"sound": True})
    loaded = SettingsStore(tmp_path / "nope.json", defaults).load()

    assert loaded.difficulty is Difficulty.HARD
    assert loaded.options == {"sound": True}
    # The loaded copy must not alias the defaults dict.
    loaded.options["sound"] = False
    assert defaults.options["sound"] is True


def test_load_corrupt_file_falls_back_to_defaults_instead_of_crashing(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("not json", encoding="utf-8")
    defaults = Settings(difficulty=Difficulty.EASY, options={"sound": True})

    loaded = SettingsStore(path, defaults).load()

    assert loaded.difficulty is Difficulty.EASY
    assert loaded.options == {"sound": True}


def test_load_corrupt_file_heals_itself_for_the_next_launch(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("not json", encoding="utf-8")

    SettingsStore(path, Settings()).load()

    assert Settings.from_dict(json.loads(path.read_text()), Settings()) == Settings()


def test_apply_sets_current_without_writing_to_disk(tmp_path):
    path = tmp_path / "settings.json"
    store = SettingsStore(path, Settings())
    store.load()

    store.apply(Settings(difficulty=Difficulty.BOSS))

    assert store.current.difficulty is Difficulty.BOSS
    assert not path.exists()
