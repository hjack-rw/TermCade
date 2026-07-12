"""The mixer is the whole point of the audio rewrite, and it needs no sound card to prove itself.

The claim that matters is that two sounds *coexist* — the old backend could only ever replace one
with the other. Everything else here defends the properties that make coexistence survivable: the
sum must not wrap, a one-shot must let go, and a loop must not.
"""

from __future__ import annotations

from array import array

from termcade.core import music
from termcade.core.mixer import PEAK, Mixer, pcm_of


def samples(pcm: bytes) -> array:
    out = array("h")
    out.frombytes(pcm)
    return out


def test_two_voices_are_summed_not_swapped():
    """The one thing winsound could never do."""
    mixer = Mixer()
    mixer.play(array("h", [100, 100, 100, 100]))
    mixer.play(array("h", [5, 5, 5, 5]))

    assert list(samples(mixer.fill(4))) == [105, 105, 105, 105]


def test_a_loud_sum_clips_instead_of_wrapping():
    """Two near-peak voices overflow int16. Wrapping flips the sign — a loud moment becomes a
    crack, which is far more audible than the squash clipping costs."""
    mixer = Mixer()
    mixer.play(array("h", [30000, -30000]))
    mixer.play(array("h", [30000, -30000]))

    assert list(samples(mixer.fill(2))) == [PEAK, -PEAK]


def test_gain_scales_a_voice():
    mixer = Mixer()
    mixer.play(array("h", [1000, 1000]), gain=0.5)

    assert list(samples(mixer.fill(2))) == [500, 500]


def test_a_one_shot_ends_and_leaves():
    """It must drop itself, or every click ever pressed stays in the mix list forever."""
    mixer = Mixer()
    mixer.play(array("h", [7, 7]))

    assert list(samples(mixer.fill(4))) == [7, 7, 0, 0]
    assert mixer.voices == 0


def test_a_loop_wraps_and_stays():
    mixer = Mixer()
    mixer.play(array("h", [1, 2]), loop=True)

    assert list(samples(mixer.fill(5))) == [1, 2, 1, 2, 1]
    assert mixer.voices == 1


def test_a_loop_wraps_mid_block():
    """The wrap lands inside a block, not on its edge — there is no gap to hide a click in, which
    is why the theme has to be rendered as a seamless loop in the first place."""
    mixer = Mixer()
    mixer.play(array("h", [1, 2, 3]), loop=True)

    assert list(samples(mixer.fill(4))) == [1, 2, 3, 1]


def test_an_empty_voice_does_not_spin_forever():
    """A looping voice with no samples has no end to reach. Guard, or the audio thread hangs and
    the app takes the whole terminal down with it."""
    mixer = Mixer()
    mixer.play(array("h"), loop=True)

    assert list(samples(mixer.fill(3))) == [0, 0, 0]
    assert mixer.voices == 0


def test_stopping_one_voice_leaves_the_others():
    mixer = Mixer()
    kept = mixer.play(array("h", [10, 10]), loop=True)
    dropped = mixer.play(array("h", [1, 1]), loop=True)

    mixer.stop(dropped)

    assert list(samples(mixer.fill(2))) == [10, 10]
    assert mixer.voices == 1
    assert kept.pos == 2


def test_silence_when_nothing_plays():
    assert list(samples(Mixer().fill(3))) == [0, 0, 0]


def test_a_theme_round_trips_through_the_riff_container():
    """``music.theme`` hands out a WAV because that is the shape it always had; the mixer wants the
    samples inside. If the unwrap is wrong the theme plays as noise, so pin the seam."""
    track = music.compose("xiaolin")
    pcm = music.render(track)

    assert pcm_of(music.wav_bytes(pcm)).tobytes() == pcm


def test_every_effect_synthesizes_to_audible_samples():
    """No files on disk — an effect that renders to digital silence is indistinguishable from the
    sound being broken, so assert each one actually moves."""
    for name in (music.CLICK, music.CONFIRM, music.BACK, music.ERROR):
        pcm = music.sfx(name)

        assert len(pcm) > 0, f"{name} rendered nothing"
        assert max(abs(s) for s in pcm) > 0, f"{name} is silent"
