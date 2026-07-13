"""A settings file keeps every key ever written into it. Most of them are lies by then.

Xiaolin's file still carried `draw_limit` and `deposit_limit` months after the one-action economy
replaced them both. They did nothing — which is worse than doing something wrong, because the next
person to read the file believes them.

So the store drops what nobody declares. Three things must survive that: the game's own options, the
engine's (`music`, `sfx` — the app writes those itself, they are in no cartridge's defaults), and the
keys a game keeps for its own bookkeeping (Xiaolin's card-pool fingerprint).
"""

from __future__ import annotations

import json

from termcade.core.settings import Settings, SettingsStore


def _store(tmp_path, saved: dict, *, defaults: dict, private: frozenset[str] = frozenset()):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"difficulty": "easy", "options": saved}), encoding="utf-8")
    return SettingsStore(path, Settings(options=defaults), private_options=private)


def test_a_knob_the_game_no_longer_has_is_dropped(tmp_path):
    store = _store(tmp_path, {"max_wager": 3, "draw_limit": 1}, defaults={"max_wager": 3})

    assert "draw_limit" not in store.load().options


def test_the_options_the_game_still_declares_are_kept(tmp_path):
    store = _store(tmp_path, {"max_wager": 2, "draw_limit": 1}, defaults={"max_wager": 3})

    assert store.load().options["max_wager"] == 2  # the player's value, not the default


def test_the_engines_own_options_survive_a_game_that_never_heard_of_them(tmp_path):
    """`music` and `sfx` are written by the app and appear in no cartridge's defaults.

    Pruned on sight, muting the music would delete the setting that muted it.
    """
    store = _store(tmp_path, {"max_wager": 3, "music": False, "sfx": False}, defaults={"max_wager": 3})

    kept = store.load().options

    assert kept["music"] is False
    assert kept["sfx"] is False


def test_a_games_private_bookkeeping_survives(tmp_path):
    """Xiaolin's pool fingerprint is not a preference, so it is not in the defaults — and it must live.

    It records which card pool the file was written for. Pruned every launch, the check it exists for
    could never fire.
    """
    store = _store(
        tmp_path, {"max_wager": 3, "pool": 40093}, defaults={"max_wager": 3}, private=frozenset({"pool"})
    )

    assert store.load().options["pool"] == 40093


def test_a_game_that_declares_no_options_keeps_whatever_it_wrote(tmp_path):
    """Options are free-form by contract. Pruning is a service to a game that declared its options,
    not a rule imposed on one that has not."""
    store = _store(tmp_path, {"anything": True}, defaults={})

    assert store.load().options == {"anything": True}
