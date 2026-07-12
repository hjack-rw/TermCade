"""Procedural chiptune: a seed in, a playable WAV out. No audio assets on disk.

The generator is a coprime-notch ensemble. Four voices tick on pairwise-coprime
periods, so the ensemble's pattern only repeats at the product of those periods —
minutes of melody out of four tiny counters.

The rule that makes it music rather than drift: **the rotors never decide when a
note fires, only which note fires.** The pulse grid is a power of two, so a
downbeat always lands; bass and kick are nailed to it and no rotor touches them.
A rotor's number is an index into an already-legal set (the current chord, or the
scale), which is why an unheard seed cannot produce a wrong note — only a
different one. Drop that constraint and coprime periods give you ambient wash:
nothing ever lands together, and there is no beat to hold on to.

Pure and TTY-free: composition is a list of ``Note``, rendering is bytes. Playing
them is :mod:`termcade.core.audio`'s problem.
"""

from __future__ import annotations

import io
import math
import wave
from array import array
from dataclasses import dataclass, field

from termcade.core.rng import Rng

# Pairwise coprime -> the melody repeats only at their product (1155 eighths, ~4 min).
ROTORS = (3, 5, 7, 11)

STEPS_PER_BAR = 16  # 16th-note grid. A power of two: the downbeat never drifts.
BARS = 8
SAMPLE_RATE = 22050


@dataclass(frozen=True)
class Style:
    """The musical rules a track is composed under. The seed picks *within* a style; it can
    never leave one. Swapping the style is how a cartridge changes what its music *is* — a
    different scale and harmony — as opposed to a seed, which only picks a different tune
    inside the rules it was already given.
    """

    scale: tuple[int, ...]  # semitone offsets from the root
    progressions: tuple[tuple[tuple[int, ...], ...], ...]  # chord cycles the seed chooses between
    roots_hz: tuple[float, ...]  # where the whole track sits
    bpm_range: tuple[int, int]


# The cabinet's own voice, and the fallback for a cartridge that names no style: natural minor,
# triads, brisk. Triads are what make harmony read as major/minor, and therefore as Western.
ARCADE = Style(
    scale=(0, 2, 3, 5, 7, 8, 10),
    progressions=(
        ((0, 3, 7), (8, 12, 15), (3, 7, 10), (10, 14, 17)),  # i - VI - III - VII
        ((0, 3, 7), (5, 8, 12), (10, 14, 17), (0, 3, 7)),    # i - iv - VII - i
        ((0, 3, 7), (10, 14, 17), (8, 12, 15), (5, 8, 12)),  # i - VII - VI - iv
    ),
    roots_hz=(196.0, 220.0, 246.9),  # G3, A3, B3
    bpm_range=(120, 152),
)

# Voice names double as waveform selectors in `_render_voice`.
BASS = "bass"
ARP = "arp"
LEAD = "lead"
KICK = "kick"
SNARE = "snare"
HAT = "hat"


@dataclass(frozen=True)
class Note:
    step: int  # position on the 16th grid
    voice: str
    semitone: int  # offset from the track's root; ignored by the drum voices
    steps: int  # duration, in grid steps
    amp: float


@dataclass(frozen=True)
class Track:
    """Everything the seed decided. The rules themselves are not up for grabs."""

    seed: int
    bpm: int
    root_hz: float
    progression: tuple[tuple[int, ...], ...]
    phases: tuple[int, ...]
    style: Style = ARCADE
    notes: list[Note] = field(default_factory=list)

    @property
    def step_seconds(self) -> float:
        return 60.0 / self.bpm / 4

    @property
    def total_steps(self) -> int:
        return BARS * STEPS_PER_BAR

    @property
    def loop_seconds(self) -> float:
        return self.total_steps * self.step_seconds


def compose(seed: int | str | None = None, style: Style = ARCADE) -> Track:
    """Pick a key from the seed, then fill the grid by rule."""
    rng = Rng(seed)
    bpm = rng.randint(*style.bpm_range)
    root_hz = rng.choice(style.roots_hz)
    progression = rng.choice(style.progressions)
    # The rotors' starting offsets — the seed's only say over the melody itself.
    phases = tuple(rng.randint(0, p - 1) for p in ROTORS)

    track = Track(
        seed=rng.seed,
        bpm=bpm,
        root_hz=root_hz,
        progression=progression,
        phases=phases,
        style=style,
    )
    track.notes.extend(_fill(track))
    return track


def _rotor(track: Track, step: int) -> int:
    """The rotors' entire contribution: a number. What it indexes is decided elsewhere."""
    return sum((step + ph) % p for p, ph in zip(ROTORS, track.phases))


def _chord_at(track: Track, step: int) -> tuple[int, ...]:
    bars_per_chord = BARS // len(track.progression)
    index = step // (STEPS_PER_BAR * bars_per_chord)
    return track.progression[index % len(track.progression)]


def _fill(track: Track) -> list[Note]:
    notes: list[Note] = []
    previous_lead = 12

    for step in range(track.total_steps):
        chord = _chord_at(track, step)
        beat = step % STEPS_PER_BAR

        # Bass — the chord's root on beats 1 and 3. Rotor-free, so the floor never moves.
        if beat in (0, 8):
            notes.append(Note(step, BASS, chord[0] - 24, 7, 0.34))

        # Arp — chord tones on every 16th. A pure function of the step; no rotor either.
        notes.append(Note(step, ARP, chord[step % len(chord)], 1, 0.10))

        # Lead — eighths. Constrain to a legal set first, then let the rotor pick from it.
        if beat % 2 == 0:
            strong = beat % 4 == 0
            allowed = chord if strong else track.style.scale
            pick = _rotor(track, step)
            if strong or pick % 7 != 6:  # the odd residue is a rest — it phrases the line
                semitone = allowed[pick % len(allowed)] + 12
                # Take whichever octave sits nearest the last note, so the line stays singable
                # instead of leaping an octave every time the rotor wraps.
                semitone = min(
                    (semitone + octave for octave in (-12, 0, 12)),
                    key=lambda candidate: abs(candidate - previous_lead),
                )
                previous_lead = semitone
                notes.append(Note(step, LEAD, semitone, 2, 0.20))

        # Drums — the groove is fixed. A rotor may add a hat, never move the kick or snare.
        if beat in (0, 8):
            notes.append(Note(step, KICK, 0, 2, 0.55))
        elif beat in (4, 12):
            notes.append(Note(step, SNARE, 0, 2, 0.35))
        elif beat % 2 == 0 or _rotor(track, step) % 5 == 0:
            notes.append(Note(step, HAT, 0, 1, 0.12))

    return notes


def _noise(index: int) -> float:
    """A deterministic hiss. Cheap and periodic, but at drum lengths it reads as noise."""
    return ((index * 1103515245 + 12345) >> 16 & 0x7FFF) / 16383.5 - 1.0


def _render_voice(
    voice: str, hz: float, samples: int, amp: float, out: array, *, hz_end: float | None = None
) -> None:
    """Add one note into ``out``, in place.

    ``hz_end`` glides the pitch across the note instead of holding it. A held pitch is what a
    *melody* wants; a falling one is what a *press* wants — the drop is the whole reason an arcade
    blip feels like something landed rather than merely beeped. The music never passes it.

    The glide is why phase is accumulated rather than computed as ``hz * i``: with a moving
    frequency that closed form tears the waveform apart, because each sample would be placed as if
    its own pitch had been running since the start of the note.
    """
    phase = 0.0
    for i in range(samples):
        decay = i / samples
        f = hz if hz_end is None else hz + (hz_end - hz) * decay
        phase = (phase + f / SAMPLE_RATE) % 1.0
        if voice == KICK:
            # A pitch sweep down into a thud — the whole kick drum, basically.
            swept = 110.0 * math.exp(-8.0 * decay)
            value = math.sin(2 * math.pi * swept * i / SAMPLE_RATE) * math.exp(-16.0 * decay)
        elif voice in (SNARE, HAT):
            fall = 9.0 if voice == SNARE else 40.0
            value = _noise(i) * math.exp(-fall * decay)
        elif voice == BASS:
            value = (4 * abs(phase - 0.5) - 1) * math.exp(-1.4 * decay)  # triangle
        else:
            duty = 0.5 if voice == LEAD else 0.25  # two pulse widths -> two timbres
            value = (1.0 if phase < duty else -1.0) * math.exp(-4.5 * decay)  # square
        out[i] += value * amp


def render(track: Track) -> bytes:
    """Synthesize the track to 16-bit mono PCM, exactly one loop long.

    The last notes of the bar are still ringing when the loop ends, so they are rendered past
    it and then folded back onto the start. That tail is the seam: leave it on the end and the
    loop restarts into a second of decay (an audible gap every time round); cut it off and the
    final notes are chopped mid-decay. Wrapping it means the ring-out lands under the downbeat
    it would have run into anyway, which is what it does on the second pass through.
    """
    loop = int(track.loop_seconds * SAMPLE_RATE)
    mix = array("d", bytes(8 * (loop + SAMPLE_RATE)))

    for note in track.notes:
        start = int(note.step * track.step_seconds * SAMPLE_RATE)
        samples = max(int(note.steps * track.step_seconds * SAMPLE_RATE), 64)
        hz = track.root_hz * 2 ** (note.semitone / 12)
        scratch = array("d", bytes(8 * samples))
        _render_voice(note.voice, hz, samples, note.amp, scratch)
        for i in range(samples):
            mix[start + i] += scratch[i]

    for i in range(loop, len(mix)):
        mix[i - loop] += mix[i]
    del mix[loop:]

    peak = max((abs(v) for v in mix), default=0.0)
    gain = (0.92 / peak) if peak > 1e-9 else 0.0
    return array("h", (int(v * gain * 32767) for v in mix)).tobytes()


def wav_bytes(pcm: bytes) -> bytes:
    """Wrap raw PCM in a RIFF container, ready for a player to hand to the OS."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(SAMPLE_RATE)
        out.writeframes(pcm)
    return buffer.getvalue()


def theme(seed: int | str | None = None, style: Style = ARCADE) -> bytes:
    """The one call a game needs: seed in, loopable WAV out."""
    return wav_bytes(render(compose(seed, style)))


CLICK = "click"
CONFIRM = "confirm"
BACK = "back"
ERROR = "error"

# Each effect is a run of notes on the music's own voices, so an effect sits in the same timbre as
# the track it lands on — and, like the theme, ships as no file at all. Pitches are absolute Hz
# rather than scale degrees: an effect answers a keypress, not the bar it happens to fall in, and
# tying it to the current chord would make the same button sound different every time.
#
# Every one of them *moves* — that is what separates a press from a beep. A pitch falling through
# the sound reads as something landing; a held pitch reads as a tone being sounded at you. They are
# on ARP (a 25% pulse) rather than LEAD (a 50% square) because the thinner wave cuts through the
# music instead of sinking into it, which is the whole job of an interface sound.
_SFX: dict[str, tuple[tuple[str, float, float, float, float], ...]] = {
    # voice, Hz start, Hz end, seconds, amplitude — played back to back
    # The press: a bright blip snapping down, with a low body under it. The body is what gives it
    # weight — without it the blip is audible but weightless, and the button feels like it beeped
    # rather than went down.
    CLICK: ((ARP, 900.0, 300.0, 0.035, 0.60), (BASS, 160.0, 90.0, 0.05, 0.35)),
    CONFIRM: ((ARP, 880.0, 880.0, 0.04, 0.45), (ARP, 1320.0, 1500.0, 0.10, 0.45)),  # rising
    BACK: ((ARP, 740.0, 370.0, 0.09, 0.40),),                                       # falling
    ERROR: ((LEAD, 170.0, 60.0, 0.22, 0.55),),                                      # a low growl
}


def sfx(name: str) -> array:
    """A short burst of PCM, synthesized on the spot. Ready to hand straight to the mixer."""
    out = array("h")
    for voice, hz, hz_end, seconds, amp in _SFX[name]:
        samples = int(seconds * SAMPLE_RATE)
        scratch = array("d", bytes(8 * samples))
        _render_voice(voice, hz, samples, amp, scratch, hz_end=hz_end)
        out.extend(int(max(-1.0, min(1.0, value)) * 32767) for value in scratch)
    return out
