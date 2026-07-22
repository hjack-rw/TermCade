"""Playback: the only place in the engine that decides where a sound comes out.

A ``Protocol`` with three implementations, because where the player is sitting is not the game's
business. Tests have no sound card, CI has no sound card, and a player who turned sound off wants
none — every one of those is :class:`NullPlayer`, and silence is the normal case, not the error
case.

At a real terminal, :class:`StreamPlayer` holds one open output stream and feeds it from a
:class:`~termcade.core.mixer.Mixer`. This is what buys sound effects: mixing in our own process sums
the samples — which we generate anyway — before the device sees them, so an effect sounds *over* the
music instead of cutting it off.

In a browser, the device is on the wrong machine: a served game playing through ``sounddevice``
sounds out of the *server*, to nobody. :class:`BrowserPlayer` sends the samples to the page instead
and lets WebAudio do the mixing, which it does natively. Same Protocol, so nothing upstream knows
which of the three it is holding.

``sounddevice`` is the one runtime dependency beyond Textual. It is used through
``RawOutputStream``, which hands the callback a plain writable buffer, so NumPy is not pulled in.
"""

from __future__ import annotations

import base64
import hashlib
import os
import sys
from array import array
from collections.abc import Callable
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

# The meta type the page listens for. Namespaced, because that prefix is what tells the session
# layer a packet is ours to forward rather than upstream's to interpret.
AUDIO_META = "termcade_audio"

# Base64 characters per meta packet. Samples go to the browser down the subprocess's stdout, which
# is a pipe the terminal's own output shares — a tune sent as one 900KB write would hold the game's
# drawing behind it. Chunked, the transfer interleaves with the frames and nobody sees a pause.
CHUNK = 48 * 1024


class AudioPlayer(Protocol):
    def play_loop(self, wav: bytes, *, crossfade: float = 0.0) -> None:
        """Start ``wav`` looping. Replaces whatever was looping before.

        ``crossfade`` seconds fades the outgoing loop down while the new one comes up, instead of
        cutting. A cut is right when the music was silent (starting, unmuting); a fade is right when
        one tune is replacing another mid-run.
        """

    def play_once(self, pcm: array) -> None:
        """Sound ``pcm`` once, over anything already playing."""

    def stop(self) -> None:
        """Silence the loop. Effects are too short to be worth chasing."""

    def close(self) -> None:
        """Release the device. Safe to call more than once."""


class NullPlayer:
    """Silence. The fallback whenever real audio is off, absent, or unwanted."""

    def play_loop(self, wav: bytes, *, crossfade: float = 0.0) -> None:
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

    def play_loop(self, wav: bytes, *, crossfade: float = 0.0) -> None:
        samples = int(crossfade * SAMPLE_RATE)
        if self._music is not None and samples > 0:
            # Both loops run together for the length of the fade. The outgoing one drops itself once
            # it reaches silence — it loops, so it would otherwise play under the new tune forever.
            self._mixer.fade(self._music, 0.0, samples=samples, drop=True)
            self._music = self._mixer.play(pcm_of(wav), loop=True, gain=0.0)
            self._mixer.fade(self._music, MUSIC_GAIN, samples=samples)
            return
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


class BrowserPlayer:
    """Sound for a game being served: the samples go to the page, WebAudio does the rest.

    ``write_meta`` is the app driver's channel to the browser — the same one the Back button uses.
    Only raw PCM travels: the page builds an ``AudioBuffer`` from it directly, so neither side has
    to agree on a container format, and the sample rate is the engine's own.

    Every sound is keyed by the digest of its samples and sent **once**. A tune costs its transfer
    on the first play and nothing on every play after, which is what makes a music toggle or a
    return to a tune already heard instant rather than another 600KB. The cache lives in the page,
    so this only has to remember what it already sent.
    """

    def __init__(self, write_meta: Callable[[dict[str, object]], None]) -> None:
        self._write_meta = write_meta
        self._sent: set[str] = set()
        self._alive = True

    def _send(self, message: dict[str, object]) -> None:
        """Never raises, because this module's whole contract is that sound is not an error path.

        The channel dies before the app does — a closed tab, a dropped socket, a session being torn
        down — and `close()` runs during exactly that teardown. A click sounding into a dead pipe
        must be silence, not an exception surfacing in the UI of a game that is already leaving.
        """
        if not self._alive:
            return
        message["type"] = AUDIO_META
        try:
            self._write_meta(message)
        except Exception:  # noqa: BLE001 — a dead channel is silence, like a missing sound card
            # Latched, not retried per sound: once the page is gone every later call would raise
            # too, and a chunked tune is hundreds of them.
            self._alive = False

    def _ensure(self, pcm: bytes) -> str:
        """The page's key for these samples, transferring them first if it has not seen them."""
        key = hashlib.sha256(pcm).hexdigest()[:16]
        if key in self._sent:
            return key
        encoded = base64.b64encode(pcm).decode("ascii")
        chunks = [encoded[at : at + CHUNK] for at in range(0, len(encoded), CHUNK)]
        for index, chunk in enumerate(chunks):
            self._send({
                "action": "chunk", "id": key, "seq": index, "total": len(chunks),
                "rate": SAMPLE_RATE, "data": chunk,
            })
        self._sent.add(key)
        return key

    def play_loop(self, wav: bytes, *, crossfade: float = 0.0) -> None:
        self._send({
            "action": "loop", "id": self._ensure(pcm_of(wav).tobytes()),
            "gain": MUSIC_GAIN, "crossfade": crossfade,
        })

    def play_once(self, pcm: array) -> None:
        self._send({"action": "once", "id": self._ensure(pcm.tobytes()), "gain": SFX_GAIN})

    def stop(self) -> None:
        self._send({"action": "stop"})

    def close(self) -> None:
        self.stop()


def browser_player(app: object) -> AudioPlayer | None:
    """A :class:`BrowserPlayer` for ``app`` if it is being served, else ``None``.

    The driver having a meta channel *is* the question — a real terminal has no such thing, and
    nothing else distinguishes a served session from a local one as reliably. ``TERMCADE_MUTE``
    still wins, so the test suite does not start narrating over the browser either.
    """
    if os.environ.get(MUTE_ENV):
        return None
    write_meta = getattr(getattr(app, "_driver", None), "write_meta", None)
    return BrowserPlayer(write_meta) if callable(write_meta) else None


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
