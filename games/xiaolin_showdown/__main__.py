"""``xiaolin`` / ``python -m xiaolin_showdown`` entry point — boots the game on the engine."""

from __future__ import annotations


def main() -> None:
    # Imported lazily so the console script stays importable without a terminal present.
    from termcade.ui.app import EngineApp

    from .game import build_game

    EngineApp(build_game()).run()


if __name__ == "__main__":
    main()
