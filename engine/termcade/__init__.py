"""termcade — a reusable Textual TUI engine for terminal games.

The engine is the long-lived cabinet; games are finite cartridges that plug in.
Layers:

- ``termcade.core`` — TUI-agnostic services (saves, settings, rng, state). Never imports textual.
- ``termcade.app``  — the wiring seam (``Game`` descriptor + ``GameContext``).
- ``termcade.ui``   — the Textual layer (``EngineApp``, screens, widgets, theme).
"""

from importlib.metadata import PackageNotFoundError, version as _installed_version

try:
    __version__ = _installed_version("termcade")
except PackageNotFoundError:  # running from a source tree that was never installed
    __version__ = "0.0.0+source"

# One version, and `pyproject.toml` holds it. It used to be written out here as well, which is two
# answers to one question and no way to notice when they stop agreeing — the copy here had already
# gone stale. The CARTRIDGE version is a different fact and stays with the cartridge: the engine is
# the cabinet, a game is what you plug into it, and they do not ship on the same clock.
