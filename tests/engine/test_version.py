"""One version, held in one place.

``__version__`` used to be written out in ``termcade/__init__.py`` as well as in ``pyproject.toml``
— two answers to one question, with nothing to notice when they stopped agreeing. They had already
stopped: the module said 0.1.0 while the cartridge shipped as 1.3, and neither matched what was
actually installed.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import termcade

_PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"


def _declared() -> str:
    return tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))["project"]["version"]


def test_the_engine_reports_the_version_the_project_declares() -> None:
    """Also catches a stale editable install, which is the same class of lie: the metadata is
    written when the package is installed, so a checkout that moved on without reinstalling reports
    a version nothing in the tree claims."""
    assert termcade.__version__ == _declared()


def test_the_version_is_not_written_down_twice() -> None:
    """The point of deriving it. A literal here is the duplicate coming back."""
    source = (Path(termcade.__file__)).read_text(encoding="utf-8")
    assert f'"{_declared()}"' not in source
    assert "importlib.metadata" in source


def test_a_cartridge_keeps_its_own_version() -> None:
    """Not the same fact. The engine is the cabinet and a game is what plugs into it; they do not
    ship on one clock, so the cartridge naming its own version is correct rather than a third copy."""
    from xiaolin_showdown.game import build_game

    assert build_game().version
    assert build_game().version != termcade.__version__
