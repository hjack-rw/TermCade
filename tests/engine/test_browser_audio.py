"""Sound for a served game: the samples go to the page, not to the server's speakers."""

from __future__ import annotations

import base64
from array import array

from termcade.core import music
from termcade.core.mixer import pcm_of
from termcade.core.audio import AUDIO_META, MUSIC_GAIN, SFX_GAIN, BrowserPlayer, browser_player


class _Meta:
    """Stands in for the app driver's channel to the browser."""

    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []

    def __call__(self, message: dict[str, object]) -> None:
        self.sent.append(message)

    def of(self, action: str) -> list[dict[str, object]]:
        return [m for m in self.sent if m.get("action") == action]

    def payload(self, key: str) -> bytes:
        """The samples the page was given under ``key``, reassembled as the page would."""
        chunks = [m for m in self.of("chunk") if m["id"] == key]
        joined = "".join(str(m["data"]) for m in sorted(chunks, key=lambda m: int(str(m["seq"]))))
        return base64.b64decode(joined)


def _wav() -> bytes:
    return music.theme("test", music.ARCADE)


def test_every_packet_is_namespaced_so_the_session_layer_forwards_it() -> None:
    """The prefix is the whole routing rule — upstream drops any meta type it does not know."""
    meta = _Meta()
    BrowserPlayer(meta).play_loop(_wav())
    assert meta.sent and all(m["type"] == AUDIO_META for m in meta.sent)


def test_the_page_is_sent_the_samples_themselves() -> None:
    """Raw PCM, so neither side has to agree on a container — the page builds a buffer from it."""
    meta = _Meta()
    wav = _wav()
    BrowserPlayer(meta).play_loop(wav)
    [command] = meta.of("loop")
    assert meta.payload(str(command["id"])) == pcm_of(wav).tobytes()


def test_the_samples_carry_the_rate_they_were_generated_at() -> None:
    """A buffer built at the wrong rate plays the tune at the wrong pitch."""
    meta = _Meta()
    BrowserPlayer(meta).play_loop(_wav())
    chunks = meta.of("chunk")
    assert chunks, "no chunks at all — the assertion below would pass vacuously"
    assert all(m["rate"] == music.SAMPLE_RATE for m in chunks)


def test_a_dead_channel_is_silence_rather_than_an_exception() -> None:
    """The module's contract is that sound is never an error path. The page goes before the app
    does — a closed tab, a dropped socket — and a click sounding into it must not surface in the UI
    of a game that is already leaving."""

    def gone(message: dict[str, object]) -> None:
        raise RuntimeError("the page is gone")

    player = BrowserPlayer(gone)
    player.play_loop(_wav())  # raises nothing
    player.play_once(array("h", [0, 1, 2, 3]))
    player.stop()
    player.close()


def test_a_dead_channel_is_not_retried_for_every_chunk() -> None:
    """A tune is hundreds of packets; once the page is gone they would all raise."""
    attempts: list[int] = []

    def gone(message: dict[str, object]) -> None:
        attempts.append(1)
        raise RuntimeError("the page is gone")

    BrowserPlayer(gone).play_loop(_wav())

    assert len(attempts) == 1, "kept writing to a channel already known to be dead"


def test_a_tune_is_transferred_once_however_often_it_plays() -> None:
    """A music toggle replays what the page already has; re-sending 600KB would make it a stutter."""
    meta = _Meta()
    player, wav = BrowserPlayer(meta), _wav()
    player.play_loop(wav)
    first = len(meta.of("chunk"))
    player.stop()
    player.play_loop(wav)

    assert first > 0
    assert len(meta.of("chunk")) == first
    assert len(meta.of("loop")) == 2


def test_a_tune_too_big_for_one_packet_is_split_and_numbered(monkeypatch) -> None:
    """The chunking was never actually exercised: whether a real tune crosses the 48KB boundary was
    incidental, so the `seq` field and the page's reassembly rested on nothing. Forced small here so
    the boundary is crossed on purpose rather than by luck."""
    monkeypatch.setattr("termcade.core.audio.CHUNK", 64)
    meta = _Meta()
    wav = _wav()

    BrowserPlayer(meta).play_loop(wav)

    chunks = meta.of("chunk")
    assert len(chunks) > 1, "the payload never crossed the chunk boundary"
    assert [m["seq"] for m in chunks] == list(range(len(chunks))), "sequence numbers are not in order"
    assert all(m["total"] == len(chunks) for m in chunks), "a chunk disagrees about how many there are"
    assert meta.payload(str(meta.of("loop")[0]["id"])) == pcm_of(wav).tobytes()


def test_two_different_sounds_are_told_apart() -> None:
    meta = _Meta()
    player = BrowserPlayer(meta)
    player.play_once(music.sfx(music.CLICK))
    player.play_loop(_wav())
    assert meta.of("once")[0]["id"] != meta.of("loop")[0]["id"]


def test_effects_and_music_keep_the_engines_own_balance() -> None:
    """The mix moved to the browser; the gains that keep an effect audible over the music did not."""
    meta = _Meta()
    player = BrowserPlayer(meta)
    player.play_loop(_wav())
    player.play_once(array("h", [0, 1, 2, 3]))
    assert meta.of("loop")[0]["gain"] == MUSIC_GAIN
    assert meta.of("once")[0]["gain"] == SFX_GAIN


def test_a_crossfade_survives_the_trip_to_the_page() -> None:
    """One tune replacing another mid-run fades; the page runs the ramp the engine asked for."""
    meta = _Meta()
    player = BrowserPlayer(meta)
    player.play_loop(_wav())
    player.play_loop(music.theme("other", music.ARCADE), crossfade=0.6)
    assert meta.of("loop")[-1]["crossfade"] == 0.6


def test_a_terminal_gets_no_browser_player() -> None:
    """No meta channel means nobody is watching through a page — that is the whole question."""

    class _Terminal:
        _driver = object()

    assert browser_player(_Terminal()) is None
    assert browser_player(object()) is None


def test_a_served_session_gets_one(monkeypatch) -> None:
    monkeypatch.delenv("TERMCADE_MUTE", raising=False)  # the suite mutes itself; see conftest

    class _Served:
        class _driver:
            @staticmethod
            def write_meta(message: dict[str, object]) -> None:
                return None

    assert isinstance(browser_player(_Served()), BrowserPlayer)


def test_the_mute_switch_still_wins(monkeypatch) -> None:
    """Otherwise the test suite narrates into every browser it opens."""
    monkeypatch.setenv("TERMCADE_MUTE", "1")

    class _Served:
        class _driver:
            @staticmethod
            def write_meta(message: dict[str, object]) -> None:
                return None

    assert browser_player(_Served()) is None
