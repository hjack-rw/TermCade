"""Playback: the only place in the engine that touches a sound device.

A ``Protocol`` with a do-nothing implementation, because silence is the normal case, not the error
case. Tests have no sound card, CI has no sound card, a player who turned sound off wants none, and
a game served over ``textual-serve`` would play out of the *server*, which is worse than silence.
Every one of those resolves to :class:`NullPlayer` and nothing upstream has to know.

Where there is a device, :class:`StreamPlayer` holds one open output stream and feeds it from a
:class:`~termcade.core.mixer.Mixer`. This is what buys sound effects: the previous backend handed a
WAV file to ``winsound``, which plays exactly one sound at a time, so an effect would have cut the
music off rather than sounding over it. Mixing in our own process means the samples — which we
generate anyway — are summed before the device ever sees them.

``sounddevice`` is the one runtime dependency beyond Textual. It is used through
``RawOutputStream``, which hands the callback a plain writable buffer, so NumPy is not pulled in.
"""

from __future__ import annotations

import os
import sys
from array import array
from typing import Any, Protocol

from termcade.core.mixer import Mixer, Voice, pcm_of
from termcade.core.music import SAMPLE_RATE

# Set to anything to force silence, whatever the settings say. The test suite sets it: a test run
# would otherwise open a real stream and start the theme for real, once per app test.
MUTE_ENV = "TERMCADE_MUTE"

# Keys in ``Settings.options`` a player toggles. Absent means on — a game that never mentions sound
# still gets a soundtrack. Music and effects are separate switches because they annoy separately:
# a player may want the clicks while working, or the theme without them.
MUSIC_OPTION = "music"
SFX_OPTION = "sfx"

# The mix is a plain sum, so the voices have to leave each other room. The theme is already
# normalized to near full scale on its own, so it gets pushed down to make space for an effect
# landing on top of it; without this, a click during a loud bar would clip the music, not itself.
MUSIC_GAIN = 0.55
SFX_GAIN = 0.85

# Frames per callback. Small enough that a click feels immediate (a block is ~23ms at 22050),
# large enough that a Python callback comfortably finishes before the device wants the next one.
BLOCKSIZE = 512


class AudioPlayer(Protocol):
    def play_loop(self, wav: bytes) -> None:
        """Start ``wav`` looping. Replaces whatever was looping before."""

    def play_once(self, pcm: array) -> None:
        """Sound ``pcm`` once, over anything already playing."""

    def stop(self) -> None:
        """Silence the loop. Effects are too short to be worth chasing."""

    def close(self) -> None:
        """Release the device. Safe to call more than once."""


class NullPlayer:
    """Silence. The fallback whenever real audio is off, absent, or unwanted."""

    def play_loop(self, wav: bytes) -> None:
        return None

    def play_once(self, pcm: array) -> None:
        return None

    def stop(self) -> None:
        return None

    def close(self) -> None:
        return None


class StreamPlayer:
    """One open output stream, fed from a mixer. Many sounds at once."""

    def __init__(self) -> None:
        # noqa: PLC0415 — optional at import time; a missing wheel is silence, not a crash.
        import sounddevice  # type: ignore[import-untyped]

        self._mixer = Mixer()
        self._music: Voice | None = None
        self._stream = sounddevice.RawOutputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="int16",
            blocksize=BLOCKSIZE,
            callback=self._serve,
        )
        self._stream.start()

    def _serve(self, outdata: Any, frames: int, _time: Any, _status: Any) -> None:
        """The audio thread's only entry point. Runs every ~23ms and must never block: no I/O, no
        allocation it can avoid, and no waiting on the UI thread — a late block is an audible gap.
        """
        outdata[:] = self._mixer.fill(frames)

    def play_loop(self, wav: bytes) -> None:
        if self._music is not None:
            self._mixer.stop(self._music)
        self._music = self._mixer.play(pcm_of(wav), loop=True, gain=MUSIC_GAIN)

    def play_once(self, pcm: array) -> None:
        self._mixer.play(pcm, gain=SFX_GAIN)

    def stop(self) -> None:
        if self._music is not None:
            self._mixer.stop(self._music)
            self._music = None

    def close(self) -> None:
        self._mixer.stop()
        self._stream.stop()
        self._stream.close()


def make_player(*, enabled: bool = True) -> AudioPlayer:
    """The real backend where one exists and sound is wanted; silence otherwise.

    A missing device, a missing wheel, or a machine with no audio at all is not an error — the game
    plays fine without a soundtrack, so this never raises.
    """
    if not enabled or os.environ.get(MUTE_ENV) or sys.platform == "emscripten":
        return NullPlayer()
    try:
        return StreamPlayer()
    except Exception:  # noqa: BLE001 — PortAudio raises its own family; any of them means silence
        return NullPlayer()
