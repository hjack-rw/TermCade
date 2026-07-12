"""Silence is a supported outcome, not a failure. These pin that down."""

from __future__ import annotations

from array import array

import pytest

from termcade.app.game import Game, GameContext
from termcade.core.audio import MUSIC_OPTION, MUTE_ENV, SFX_OPTION, NullPlayer, make_player
from termcade.core.settings import Settings


def test_sound_off_in_settings_gives_silence():
    assert isinstance(make_player(enabled=False), NullPlayer)


def test_mute_env_overrides_a_player_that_was_asked_for(monkeypatch):
    monkeypatch.setenv(MUTE_ENV, "1")

    assert isinstance(make_player(enabled=True), NullPlayer)


def test_a_machine_with_no_working_device_falls_back_to_silence(monkeypatch):
    """A missing sound card, a missing PortAudio wheel, a device another process has taken — the
    game must still run. Whatever the stream raises, it resolves to silence and never propagates."""
    monkeypatch.delenv(MUTE_ENV, raising=False)

    def no_device():
        raise OSError("no default output device")

    monkeypatch.setattr("termcade.core.audio.StreamPlayer", no_device)

    assert isinstance(make_player(enabled=True), NullPlayer)


def test_the_null_player_swallows_every_sound_without_complaint():
    """A headless run calls all four; none may raise, or every CI run dies."""
    player = NullPlayer()

    player.play_loop(b"RIFF....WAVE")
    player.play_once(array("h", [0, 1, 2]))
    player.stop()
    player.close()


class _NoState:
    def snapshot(self) -> dict:
        return {}

    def restore(self, data: dict) -> None:
        return None


@pytest.fixture
def ctx(tmp_path):
    return GameContext(Game(game_id="test", title="Test", state_cls=_NoState), data_dir=tmp_path)


def test_music_off_does_not_take_the_player_away(ctx):
    """The context must hand out a player whatever the setting says. Resolving the setting here
    instead would freeze it at boot, and the settings-screen toggle would do nothing until the
    next launch — which is exactly the bug this pins."""
    ctx.settings.save(Settings(options={MUSIC_OPTION: False}))

    assert ctx.audio is not None


def test_the_music_setting_is_readable_after_it_changes(ctx):
    """A live toggle only works if the *setting* is re-read, not cached."""
    ctx.settings.save(Settings(options={MUSIC_OPTION: False}))
    assert ctx.settings.current.options[MUSIC_OPTION] is False

    ctx.settings.save(Settings(options={MUSIC_OPTION: True}))
    assert ctx.settings.current.options[MUSIC_OPTION] is True


def test_music_and_effects_are_two_switches(ctx):
    """They annoy separately — a player may want the clicks without the theme, or the reverse — so
    one must never imply the other."""
    ctx.settings.save(Settings(options={MUSIC_OPTION: False, SFX_OPTION: True}))

    assert ctx.settings.current.options[MUSIC_OPTION] is False
    assert ctx.settings.current.options[SFX_OPTION] is True
