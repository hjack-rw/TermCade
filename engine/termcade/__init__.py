"""termcade — a reusable Textual TUI engine for terminal games.

The engine is the long-lived cabinet; games are finite cartridges that plug in.
Layers:

- ``termcade.core`` — TUI-agnostic services (saves, settings, rng, state). Never imports textual.
- ``termcade.app``  — the wiring seam (``Game`` descriptor + ``GameContext``).
- ``termcade.ui``   — the Textual layer (``EngineApp``, screens, widgets, theme).
"""

# `pyproject.toml` is the single source for this version. A cartridge's own version is a separate
# fact and stays with the cartridge.
#
# Computed lazily (PEP 562): `importlib.metadata` drags in zipfile/email/inspect/ssl behind it,
# ~75ms nothing on the serving path ever needs — every player session was paying to import it just
# in case something read `__version__`, which in practice only a test does.
def __getattr__(name: str) -> str:
    if name != "__version__":
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib.metadata import PackageNotFoundError, version as _installed_version

    try:
        value = _installed_version("termcade")
    except PackageNotFoundError:  # running from a source tree that was never installed
        value = "0.0.0+source"
    globals()["__version__"] = value  # cache: later lookups hit the module dict, not __getattr__
    return value
