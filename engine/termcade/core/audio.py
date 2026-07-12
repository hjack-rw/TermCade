"""Playback: the only place in the engine that touches a sound device.

A ``Protocol`` with a do-nothing implementation, because silence is the normal
case, not the error case. Tests have no sound card, CI has no sound card, a player
who turned sound off wants none, and a game served over ``textual-serve`` would
play out of the *server*, which is worse than silence. Every one of those resolves
to :class:`NullPlayer` and nothing upstream has to know.

The Windows backend is ``winsound`` — stdlib, so the engine still has no audio
dependency. It plays one sound at a time, which is the whole reason there are no
sound effects yet: an effect would have to interrupt the music. Adding them means
mixing in :mod:`termcade.core.music` (the samples are already ours) or taking a
real mixer dependency. Deferred until a cartridge asks.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Protocol

# Set to anything to force silence, whatever the settings say. The test suite sets it: a Windows
# test run would otherwise start the theme for real, once per app test.
MUTE_ENV = "TERMCADE_MUTE"

# The key in ``Settings.options`` a player toggles. Absent means on — a game that never mentions
# music still gets a soundtrack. Named for what it actually governs: there are no sound effects,
# so a broader "sound" would promise a switch that doesn't exist.
MUSIC_OPTION = "music"


class AudioPlayer(Protocol):
    def play_loop(self, wav: bytes) -> None:
        """Start ``wav`` looping. Replaces whatever was playing."""

    def stop(self) -> None: ...


class NullPlayer:
    """Silence. The fallback whenever real audio is off, absent, or unwanted."""

    def play_loop(self, wav: bytes) -> None:
        return None

    def stop(self) -> None:
        return None


class WinSoundPlayer:
    """``winsound``, which loops natively but only from a file on disk."""

    def __init__(self, cache_dir: Path | None = None) -> None:
        import winsound  # noqa: PLC0415 — Windows-only; importing at module scope breaks POSIX

        self._winsound = winsound
        self._dir = cache_dir or Path(tempfile.gettempdir())
        self._path = self._dir / "termcade-theme.wav"

    def play_loop(self, wav: bytes) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path.write_bytes(wav)
        self._winsound.PlaySound(
            str(self._path),
            self._winsound.SND_FILENAME | self._winsound.SND_ASYNC | self._winsound.SND_LOOP,
        )

    def stop(self) -> None:
        self._winsound.PlaySound(None, self._winsound.SND_PURGE)


def make_player(*, enabled: bool = True, cache_dir: Path | None = None) -> AudioPlayer:
    """The real backend where one exists and sound is wanted; silence otherwise.

    A missing backend is not an error — the game plays fine without a soundtrack, so
    this never raises.
    """
    if not enabled or os.environ.get(MUTE_ENV) or sys.platform != "win32":
        return NullPlayer()
    try:
        return WinSoundPlayer(cache_dir)
    except (ImportError, OSError):
        return NullPlayer()
