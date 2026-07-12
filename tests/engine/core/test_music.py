"""The rules the generator must not be able to break, whatever seed it is handed.

Each of these is a property of *every* track, so they run over a spread of seeds. A
waveform can't be asserted, but "the beat is where it says it is" and "no note is out
of key" can — and those are the two claims that make the output music.
"""

from __future__ import annotations

from array import array

import pytest

from termcade.core import music

SEEDS = ["termcade", "xiaolin", "wuya", 0, 7, 12345]


@pytest.mark.parametrize("seed", SEEDS)
def test_bass_and_kick_land_on_the_downbeat_of_every_bar(seed):
    track = music.compose(seed)

    for voice in (music.BASS, music.KICK):
        beats = {n.step % music.STEPS_PER_BAR for n in track.notes if n.voice == voice}
        assert beats == {0, 8}, f"{voice} drifted off the grid: {sorted(beats)}"


@pytest.mark.parametrize("seed", SEEDS)
def test_every_pitched_note_is_in_key(seed):
    track = music.compose(seed)
    pitched = {music.BASS, music.ARP, music.LEAD}

    for note in (n for n in track.notes if n.voice in pitched):
        assert note.semitone % 12 in {s % 12 for s in music.SCALE}, f"{note} is out of key"


@pytest.mark.parametrize("seed", SEEDS)
def test_lead_takes_a_chord_tone_on_every_strong_beat(seed):
    """The rotor may colour the weak beats with any scale note; on a strong beat it may only
    pick from the chord that is currently sounding, or the harmony comes apart."""
    track = music.compose(seed)

    for note in track.notes:
        if note.voice == music.LEAD and note.step % 4 == 0:
            chord = music._chord_at(track, note.step)
            assert note.semitone % 12 in {c % 12 for c in chord}


def test_the_same_seed_composes_the_same_track():
    a, b = music.compose("xiaolin"), music.compose("xiaolin")

    assert (a.bpm, a.root_hz, a.progression, a.phases) == (b.bpm, b.root_hz, b.progression, b.phases)
    assert a.notes == b.notes


def test_different_seeds_compose_different_tracks():
    assert music.compose("xiaolin").notes != music.compose("wuya").notes


def test_the_same_seed_renders_the_same_bytes():
    assert music.theme("xiaolin") == music.theme("xiaolin")


def test_theme_is_a_riff_wav():
    wav = music.theme("termcade")

    assert wav[:4] == b"RIFF" and wav[8:12] == b"WAVE"


@pytest.mark.parametrize("seed", SEEDS)
def test_the_render_is_exactly_one_loop_long(seed):
    """Any samples past the loop point are a silent gap the player hits every time it wraps —
    the ring-out of the last bar has to be folded back onto the start, not left on the end."""
    track = music.compose(seed)

    frames = len(music.render(track)) // 2  # 16-bit mono
    assert frames == int(track.loop_seconds * music.SAMPLE_RATE)


@pytest.mark.parametrize("seed", SEEDS)
def test_the_loop_seam_is_not_silent(seed):
    """The folded tail must actually land: the first moments of the loop carry the previous
    bar's decay, so they can never be digital silence."""
    pcm = music.render(music.compose(seed))
    head = array("h", pcm[: 2 * (music.SAMPLE_RATE // 10)])  # first 100ms

    assert max(abs(sample) for sample in head) > 0
