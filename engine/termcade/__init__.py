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

# `pyproject.toml` is the single source for this version. A cartridge's own version is a separate
# fact and stays with the cartridge.
