"""Per-game writable data directory resolution (saves, settings).

Honors ``TERMCADE_DATA_DIR`` first (set by the Docker image to a mounted volume),
else falls back to the OS convention. The directory is created if missing.
"""

from __future__ import annotations

import os
from pathlib import Path

ENV_VAR = "TERMCADE_DATA_DIR"


def app_dir(game_id: str) -> Path:
    """Return (creating if needed) the writable data dir for ``game_id``."""
    override = os.environ.get(ENV_VAR)
    base = Path(override) if override else _os_data_home()
    path = base / "termcade" / game_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _os_data_home() -> Path:
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA")
        return Path(local) if local else Path.home() / "AppData" / "Local"
    xdg = os.environ.get("XDG_DATA_HOME")
    return Path(xdg) if xdg else Path.home() / ".local" / "share"
