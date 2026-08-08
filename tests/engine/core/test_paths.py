"""Writable data-dir resolution: the ``TERMCADE_DATA_DIR`` override, and the OS-convention fallback
for Windows and POSIX. This is the function that decides where the real installed app writes user
data — untested until now, and a regression here is invisible to a test suite that only ever points
saves/settings at ``tmp_path`` directly.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from termcade.core.paths import ENV_VAR, _os_data_home, app_dir

# The "falls back to Path.home()" branches join onto a real Path object, and pathlib refuses to
# build the other OS's concrete Path type on a host it doesn't match (`NotImplementedError: cannot
# instantiate 'WindowsPath'/'PosixPath' on your system`) — each of those two is only safe to run for
# real on its own OS. CI runs on Linux, so the POSIX one is what actually gets exercised there.


def test_the_env_override_wins_and_is_created(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_VAR, str(tmp_path / "mounted"))

    result = app_dir("xiaolin")

    assert result == tmp_path / "mounted" / "termcade" / "xiaolin"
    assert result.is_dir()


def test_windows_falls_back_to_local_app_data_when_set(monkeypatch):
    monkeypatch.delenv(ENV_VAR, raising=False)
    monkeypatch.setattr("termcade.core.paths.os.name", "nt")
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\probe\AppData\Local")

    assert _os_data_home() == Path(r"C:\Users\probe\AppData\Local")


@pytest.mark.skipif(os.name != "nt", reason="joins a WindowsPath — only safe to build on Windows")
def test_windows_falls_back_to_home_when_local_app_data_is_unset(monkeypatch):
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.setattr(Path, "home", lambda: Path(r"C:\probe-home"))

    assert _os_data_home() == Path(r"C:\probe-home") / "AppData" / "Local"


def test_posix_uses_xdg_data_home_when_set(monkeypatch):
    monkeypatch.setattr("termcade.core.paths.os.name", "posix")
    monkeypatch.setenv("XDG_DATA_HOME", "/probe/xdg")

    assert _os_data_home() == Path("/probe/xdg")


@pytest.mark.skipif(os.name != "posix", reason="joins a PosixPath — only safe to build on POSIX")
def test_posix_falls_back_to_home_when_xdg_is_unset(monkeypatch):
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setattr(Path, "home", lambda: Path("/probe-home"))

    assert _os_data_home() == Path("/probe-home") / ".local" / "share"


def test_app_dir_namespaces_under_termcade_and_the_game_id(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_VAR, str(tmp_path))

    assert app_dir("xiaolin") == tmp_path / "termcade" / "xiaolin"
    assert app_dir("another_game") == tmp_path / "termcade" / "another_game"
