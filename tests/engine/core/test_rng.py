"""RNG determinism and JSON-safe state round-trip."""

from __future__ import annotations

import json

from termcade.core.rng import Rng, resolve_seed


def test_same_seed_same_sequence():
    a = Rng(1234)
    b = Rng(1234)
    assert [a.randint(0, 1000) for _ in range(20)] == [b.randint(0, 1000) for _ in range(20)]


def test_resolve_seed_forms():
    assert resolve_seed(7) == 7
    assert resolve_seed("alpha") == resolve_seed("alpha")  # stable
    assert resolve_seed("alpha") != resolve_seed("beta")
    assert isinstance(resolve_seed(None), int)  # fresh entropy


def test_state_round_trip_reproduces_sequence():
    rng = Rng(99)
    for _ in range(5):
        rng.randint(0, 1000)
    snapshot = rng.get_state()
    expected = [rng.randint(0, 1000) for _ in range(10)]

    resumed = Rng(99)
    resumed.set_state(snapshot)
    assert [resumed.randint(0, 1000) for _ in range(10)] == expected


def test_state_survives_json():
    rng = Rng(5)
    rng.randint(0, 10)
    state = json.loads(json.dumps(rng.get_state()))  # simulate save file round-trip
    expected = [rng.randint(0, 10) for _ in range(5)]

    resumed = Rng(5)
    resumed.set_state(state)
    assert [resumed.randint(0, 10) for _ in range(5)] == expected
