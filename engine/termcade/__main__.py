"""``python -m termcade`` — boot the engine demo scene."""

from __future__ import annotations

from termcade.ui.app import EngineApp


def main() -> None:
    EngineApp().run()


if __name__ == "__main__":
    main()
