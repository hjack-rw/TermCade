"""Software mixing: many sounds at once, summed into one stream of samples.

A ``Mixer`` is a list of playheads and an adder. It never touches a device — ``fill`` is the only
thing the audio thread calls, and it takes a frame count and returns bytes. That is what makes it
testable with no sound card, and it is also the whole reason the engine could not have sound
effects before: the old backend handed a *file* to the OS, and the OS plays one at a time, so an
effect could only ever replace the music rather than land on top of it.

The mix is a plain sum, so voices must leave each other headroom (see the gains in
:mod:`termcade.core.audio`). Anything over the limit is clipped, not wrapped — a wrap turns a loud
moment into a crack, which is far more audible than the squash.
"""

from __future__ import annotations

import io
import wave
from array import array
from dataclasses import dataclass
from threading import Lock

PEAK = 32767  # the loudest an int16 sample can be


@dataclass
class Voice:
    """One sound in flight. ``pos`` is its playhead, in samples."""

    pcm: array
    loop: bool = False
    gain: float = 1.0
    pos: int = 0
    # A gain ramp, stepped per sample on the audio thread (see `Mixer.fade`). ``fade_step`` of 0.0
    # means "not fading", and that is the common case — `fill` keeps a separate fast path for it.
    fade_to: float = 0.0
    fade_step: float = 0.0
    drop_when_faded: bool = False


def pcm_of(wav: bytes) -> array:
    """Unwrap a RIFF container back into the samples inside it.

    The music is generated as a WAV because that is the shape a file-playing backend needed. The
    mixer wants samples, not a container, and re-parsing here keeps ``music.theme()`` unchanged.
    """
    with wave.open(io.BytesIO(wav), "rb") as riff:
        frames = riff.readframes(riff.getnframes())
    samples = array("h")
    samples.frombytes(frames)
    return samples


class Mixer:
    """Voices in, one block of samples out.

    Every method may be called from the UI thread while ``fill`` runs on the audio thread, so the
    voice list is held under a lock. The lock is only ever held for the length of one block — the
    audio callback must not wait on anything, or the stream underruns and the player hears a gap.
    """

    def __init__(self) -> None:
        self._voices: list[Voice] = []
        self._lock = Lock()

    def play(self, pcm: array, *, loop: bool = False, gain: float = 1.0) -> Voice:
        voice = Voice(pcm=pcm, loop=loop, gain=gain)
        with self._lock:
            self._voices.append(voice)
        return voice

    def fade(self, voice: Voice, to: float, *, samples: int, drop: bool = False) -> None:
        """Ramp ``voice`` toward gain ``to`` over ``samples``, and optionally drop it when it lands.

        The ramp is stepped on the AUDIO thread, per sample, because only that thread knows where the
        playhead is. Driven from a UI timer instead it would move in ~23ms chunks and zipper audibly.
        ``samples`` rather than seconds keeps the mixer ignorant of the sample rate, which is the
        player's business.
        """
        if samples <= 0:
            voice.gain, voice.fade_step = to, 0.0
            return
        with self._lock:
            voice.fade_to = to
            voice.fade_step = (to - voice.gain) / samples
            voice.drop_when_faded = drop

    def stop(self, voice: Voice | None = None) -> None:
        """Drop one voice, or every voice when given none."""
        with self._lock:
            if voice is None:
                self._voices.clear()
            elif voice in self._voices:
                self._voices.remove(voice)

    @property
    def voices(self) -> int:
        with self._lock:
            return len(self._voices)

    def fill(self, frames: int) -> bytes:
        """Sum every live voice into one block of ``frames`` samples.

        A one-shot that runs out drops itself here — the only place a voice leaves without being
        asked to. A looping one wraps to the start instead, which is why the theme has to be
        rendered seamlessly: the wrap happens mid-block, with no gap to hide a click in.
        """
        out = [0] * frames
        with self._lock:
            spent: list[Voice] = []
            for voice in self._voices:
                length = len(voice.pcm)
                if length == 0:  # nothing to play, and a looping empty voice would spin forever
                    spent.append(voice)
                    continue
                pos = voice.pos
                if voice.fade_step:  # the ramping path — see `fade`; gains move per sample
                    gain, step, target = voice.gain, voice.fade_step, voice.fade_to
                    for i in range(frames):
                        if pos >= length:
                            if not voice.loop:
                                break
                            pos = 0
                        out[i] += int(voice.pcm[pos] * gain)
                        pos += 1
                        if step:
                            gain += step
                            if (step > 0 and gain >= target) or (step < 0 and gain <= target):
                                gain, step = target, 0.0
                    voice.gain, voice.fade_step = gain, step
                    # Faded to nothing and asked to leave: a looping voice never runs out on its own,
                    # so this is the only way the tune being crossfaded OUT of is ever collected.
                    if not step and voice.drop_when_faded and gain <= 0.0:
                        spent.append(voice)
                else:
                    for i in range(frames):
                        if pos >= length:
                            if not voice.loop:
                                break
                            pos = 0
                        out[i] += int(voice.pcm[pos] * voice.gain)
                        pos += 1
                voice.pos = pos
                if pos >= length and not voice.loop:
                    spent.append(voice)
            for voice in spent:
                if voice in self._voices:  # a voice can be flagged twice: faded out AND run out
                    self._voices.remove(voice)
        return array("h", (max(-PEAK, min(PEAK, sample)) for sample in out)).tobytes()
