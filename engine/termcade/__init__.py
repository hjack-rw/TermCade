"""termcade — a reusable Textual TUI engine for terminal games.

The engine is the long-lived cabinet; games are finite cartridges that plug in.
Layers:

- ``termcade.core`` — TUI-agnostic services (saves, settings, rng, state). Never imports textual.
- ``termcade.app``  — the wiring seam (``Game`` descriptor + ``GameContext``).
- ``termcade.ui``   — the Textual layer (``EngineApp``, screens, widgets, theme).
"""

__version__ = "0.0.1"
