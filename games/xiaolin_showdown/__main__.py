"""``xiaolin`` / ``python -m xiaolin_showdown`` entry point — boots the game on the engine."""

from __future__ import annotations


def main() -> None:
    # `--debug` turns the dev console on for this run, the same as `TERMCADE_DEBUG=1` — because the way
    # the game is actually played is by launching a binary, and a double-click has no shell to export
    # an environment variable from.
    import os
    import sys

    if "--debug" in sys.argv:
        os.environ["TERMCADE_DEBUG"] = "1"

    # Imported lazily so the console script stays importable without a terminal present.
    from termcade.ui.app import EngineApp

    from .game import build_game

    EngineApp(build_game()).run()


if __name__ == "__main__":
    main()
