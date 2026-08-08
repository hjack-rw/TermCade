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
    # Scales the bass note's amplitude. A root dropped an octave puts the bass low enough that
    # peak normalization (see `render`) lets it eat the headroom the other voices need — this is
    # the knob a style pulls to hold the floor down without silencing it outright.
    bass_gain: float = 1.0


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
# A held instrument tone, not a press: eased in instead of snapping to full amplitude, and a
# square blended with its own fundamental sine to round off the harshness a bare square carries.
# LEAD and ARP jump straight to peak on purpose — that jolt is what makes a keypress feel pressed —
# but the same jolt on a note held for half a second reads as a click, not a horn.
BRASS = "brass"
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
            notes.append(Note(step, BASS, chord[0] - 24, 7, 0.34 * track.style.bass_gain))

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


def _brass_envelope(i: int, samples: int) -> float:
    """Attack in, hold, release out — a fixed shape rather than one continuous decay curve, so the
    note reaches true silence by its own end instead of being cut off mid-fade. That cut is what a
    decay-only envelope always risks: it approaches zero but never has to reach it by a fixed
    sample count, so short notes especially end on an audible step into whatever comes next.
    """
    attack_n = min(samples, int(0.015 * SAMPLE_RATE))
    release_n = min(samples - attack_n, int(0.12 * SAMPLE_RATE))
    if i < attack_n:
        return i / attack_n
    if i >= samples - release_n:
        return (samples - i) / release_n
    return 1.0


def _poly_blep(t: float, dt: float) -> float:
    """Band-limited correction for a discontinuity at phase ``t``, one sample-step ``dt`` wide.

    A naive square/pulse wave (``1.0 if phase < duty else -1.0``) jumps instantly at each edge,
    which spreads energy into harmonics above the Nyquist rate — they alias back down as a harsh,
    detuned buzz on the higher LEAD notes. This rounds each edge over a single sample so the
    wave stays band-limited instead.
    """
    if t < dt:
        t /= dt
        return t + t - t * t - 1.0
    if t > 1.0 - dt:
        t = (t - 1.0) / dt
        return t * t + t + t + 1.0
    return 0.0


def _pulse(phase: float, dt: float, duty: float) -> float:
    """A polyBLEP-corrected pulse wave: one rising edge at 0, one falling edge at ``duty``."""
    value = 1.0 if phase < duty else -1.0
    value += _poly_blep(phase, dt)
    value -= _poly_blep((phase - duty) % 1.0, dt)
    return value


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
        dt = f / SAMPLE_RATE
        phase = (phase + dt) % 1.0
        if voice == KICK:
            # A pitch sweep down into a thud — the whole kick drum, basically.
            swept = 110.0 * math.exp(-8.0 * decay)
            value = math.sin(2 * math.pi * swept * i / SAMPLE_RATE) * math.exp(-16.0 * decay)
        elif voice in (SNARE, HAT):
            fall = 9.0 if voice == SNARE else 40.0
            value = _noise(i) * math.exp(-fall * decay)
        elif voice == BASS:
            value = (4 * abs(phase - 0.5) - 1) * math.exp(-1.4 * decay)  # triangle
        elif voice == BRASS:
            square = _pulse(phase, dt, 0.5)
            fundamental = math.sin(2 * math.pi * phase)
            value = (0.6 * square + 0.4 * fundamental) * _brass_envelope(i, samples)
        else:
            duty = 0.5 if voice == LEAD else 0.25  # two pulse widths -> two timbres
            value = _pulse(phase, dt, duty) * math.exp(-4.5 * decay)
        out[i] += value * amp


# A tempo-synced echo on the LEAD line only: a dotted-eighth delay tap (3 steps on the 16th
# grid, so the interval scales with bpm for free) decaying over two repeats. A special-occasion
# effect, not house style — nothing composes it in by default, a caller opts in per render.
_ECHO_DELAY_STEPS = 3
_ECHO_REPEATS = 2
_ECHO_DECAY = 0.35


def _apply_echo(mix: array, lead: array, track: Track) -> None:
    delay_samples = int(_ECHO_DELAY_STEPS * track.step_seconds * SAMPLE_RATE)
    for r in range(1, _ECHO_REPEATS + 1):
        offset = delay_samples * r
        amp = _ECHO_DECAY**r
        for i in range(len(lead) - offset):
            mix[i + offset] += lead[i] * amp


def render(track: Track, *, echo: bool = False) -> bytes:
    """Synthesize the track to 16-bit mono PCM, exactly one loop long.

    The last notes of the bar are still ringing when the loop ends, so they are rendered past
    it and then folded back onto the start. That tail is the seam: leave it on the end and the
    loop restarts into a second of decay (an audible gap every time round); cut it off and the
    final notes are chopped mid-decay. Wrapping it means the ring-out lands under the downbeat
    it would have run into anyway, which is what it does on the second pass through.
    """
    loop = int(track.loop_seconds * SAMPLE_RATE)
    mix = array("d", bytes(8 * (loop + SAMPLE_RATE)))
    lead = array("d", bytes(8 * (loop + SAMPLE_RATE))) if echo else None

    for note in track.notes:
        start = int(note.step * track.step_seconds * SAMPLE_RATE)
        samples = max(int(note.steps * track.step_seconds * SAMPLE_RATE), 64)
        hz = track.root_hz * 2 ** (note.semitone / 12)
        scratch = array("d", bytes(8 * samples))
        _render_voice(note.voice, hz, samples, note.amp, scratch)
        for i in range(samples):
            mix[start + i] += scratch[i]
            if lead is not None and note.voice == LEAD:
                lead[start + i] += scratch[i]

    if lead is not None:
        _apply_echo(mix, lead, track)

    for i in range(loop, len(mix)):
        mix[i - loop] += mix[i]
    del mix[loop:]

    return _limit(mix)


# How close to full scale the limiter is allowed to drive the mix.
_CEILING = 0.92


def _limit(mix: array) -> bytes:
    """Bring the mix up near ``_CEILING`` and only pull gain back during the rare moments that
    would exceed it, instead of scaling the whole loop down to fit a single loud instant.

    A flat peak-normalize sets one static gain for the entire loop from whichever sample is
    loudest — typically a downbeat where bass, arp, lead and kick all land together — so every
    quieter bar sits under level just to leave room for that one moment. Driving off the 95th
    percentile instead (ignoring that handful of stacked-downbeat outliers) lets the rest of the
    track sit near the ceiling; the attack/release-smoothed gain then only engages for the
    outliers themselves, so it reads as louder and punchier rather than more compressed.
    """
    n = len(mix)
    if n == 0:
        return b""
    p95 = sorted(abs(v) for v in mix)[int(n * 0.95)]
    drive = (_CEILING / p95) if p95 > 1e-9 else 0.0

    # Fast enough to catch a transient before it clips, slow enough that the gain reduction
    # isn't itself audible as pumping.
    attack_coef = 1.0 - math.exp(-1.0 / (0.003 * SAMPLE_RATE))
    release_coef = 1.0 - math.exp(-1.0 / (0.080 * SAMPLE_RATE))

    out = array("d", bytes(8 * n))
    gain = 1.0
    for i, v in enumerate(mix):
        driven = v * drive
        target = _CEILING / abs(driven) if abs(driven) > _CEILING else 1.0
        gain += (target - gain) * (attack_coef if target < gain else release_coef)
        out[i] = driven * gain

    # A hard safety ceiling for whatever the smoothed gain still lets slip past it.
    peak = max((abs(v) for v in out), default=0.0)
    safety = (_CEILING / peak) if peak > _CEILING else 1.0
    return array("h", (int(max(-1.0, min(1.0, v * safety)) * 32767) for v in out)).tobytes()


def wav_bytes(pcm: bytes) -> bytes:
    """Wrap raw PCM in a RIFF container, ready for a player to hand to the OS."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(SAMPLE_RATE)
        out.writeframes(pcm)
    return buffer.getvalue()


def theme(seed: int | str | None = None, style: Style = ARCADE, *, echo: bool = False) -> bytes:
    """The one call a game needs: seed in, loopable WAV out."""
    return wav_bytes(render(compose(seed, style), echo=echo))


CLICK = "click"
CONFIRM = "confirm"
BACK = "back"
ERROR = "error"
WIN = "win"
LOSE = "lose"
VICTORY = "victory"

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
    # A major triad climbing into a held top note — a duel round won.
    WIN: (
        (ARP, 523.25, 523.25, 0.08, 0.55),
        (ARP, 659.25, 659.25, 0.08, 0.55),
        (ARP, 783.99, 783.99, 0.08, 0.55),
        (LEAD, 1046.5, 1046.5, 0.25, 0.60),
    ),
    # Two steps down, then a long sag to nothing — a duel round lost.
    LOSE: (
        (LEAD, 392.0, 392.0, 0.10, 0.50),
        (LEAD, 329.63, 329.63, 0.10, 0.50),
        (LEAD, 261.63, 130.8, 0.35, 0.55),
    ),
    # A brass call-and-answer, not a blip: an ascending triad stated, a breath, the same triad
    # answered a step further and louder, another breath, then a lip-slur up into a held top note —
    # the buildup a fanfare takes before the *actual* tune is allowed to start. BRASS, not LEAD: an
    # instrument sustains, it doesn't snap to a peak and decay away like a keypress does.
    VICTORY: (
        (BRASS, 392.00, 392.00, 0.13, 0.24),   # call: G4 — stated slower and quiet, distance before the push
        (BRASS, 523.25, 523.25, 0.13, 0.26),   # C5
        (BRASS, 659.25, 659.25, 0.18, 0.28),   # E5
        (BRASS, 0.0, 0.0, 0.06, 0.0),          # breath — shorter now that the note ahead of it tapers into it
        (BRASS, 392.00, 392.00, 0.10, 0.44),   # answer: same call again, now up close...
        (BRASS, 523.25, 523.25, 0.10, 0.44),
        (BRASS, 659.25, 659.25, 0.10, 0.46),
        (BRASS, 783.99, 783.99, 0.15, 0.48),   # ...pushed one step further: G5
        (BRASS, 0.0, 0.0, 0.03, 0.0),          # breath
        (BRASS, 783.99, 1046.5, 0.08, 0.41),   # the slur up into landing
        (BRASS, 1046.5, 1046.5, 0.45, 0.43),   # held — rings well into the theme before it fades
    ),
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
