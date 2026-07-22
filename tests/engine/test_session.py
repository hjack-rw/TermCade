"""One browser session: what its subprocess is told, and what reaches the page.

The meta channel carries the Back button and every sound the game makes, and none of it was covered
— the audit found the whole module untested. The forwarding override is the interesting part: it is
the kind of change that works for its own packets and quietly eats everyone else's.
"""

from __future__ import annotations

import json

import pytest

from termcade import session
from termcade.core.audio import AUDIO_META


class _Recorder(session.TermCadeAppService):
    """A service that records what it forwards instead of holding a websocket.

    The recorder is wired through ``write_str`` rather than by overriding ``remote_write_str``:
    upstream assigns that name as an *instance attribute* in ``__init__``, so a subclass method of
    the same name is shadowed and never runs.
    """

    def __init__(self, **extra_env: str) -> None:
        self.forwarded: list[str] = []
        self.upstream: list[bytes] = []

        async def _write_str(data: str) -> None:
            self.forwarded.append(data)

        super().__init__(
            "true",
            extra_env=dict(extra_env),
            write_bytes=None,
            write_str=_write_str,
            close=None,
            download_manager=None,
        )

    async def _upstream(self, data: bytes) -> None:
        self.upstream.append(data)


@pytest.fixture
def service(monkeypatch):
    """A recorder whose ``super().on_meta`` is captured rather than run — upstream would try to
    reach a websocket that does not exist here."""
    svc = _Recorder()
    monkeypatch.setattr(
        session.AppService, "on_meta", lambda self, data: svc._upstream(data), raising=True
    )
    return svc


async def test_our_own_packets_reach_the_page(service) -> None:
    await service.on_meta(json.dumps({"type": "termcade_back", "allowed": True}).encode())

    assert service.forwarded == [json.dumps(["termcade_back", {"type": "termcade_back", "allowed": True}])]
    assert not service.upstream


async def test_the_shape_the_page_destructures(service) -> None:
    """The page reads ``m[0]`` as the type and ``m[1]`` as the payload."""
    await service.on_meta(json.dumps({"type": AUDIO_META, "action": "stop"}).encode())

    [sent] = service.forwarded
    kind, payload = json.loads(sent)
    assert kind == AUDIO_META
    assert payload["action"] == "stop"


async def test_upstreams_own_meta_still_reaches_upstream(service) -> None:
    """The regression this override is most likely to cause: swallowing `exit` and `open_url`."""
    data = json.dumps({"type": "open_url", "url": "https://example.invalid"}).encode()

    await service.on_meta(data)

    assert service.upstream == [data]
    assert not service.forwarded


@pytest.mark.parametrize("payload", [b"[1,2]", b'"hello"', b"12", b"null", b"not json at all"])
async def test_json_that_is_not_an_object_is_passed_on_rather_than_raising(service, payload) -> None:
    """`json.loads(b'[1,2]')` parses fine and returns a list, whose `.get` does not exist. That
    AttributeError used to propagate into the websocket loop and take the session down with it."""
    await service.on_meta(payload)

    assert service.upstream == [payload]
    assert not service.forwarded


def test_the_audio_packet_is_named_so_the_session_layer_forwards_it() -> None:
    """Two modules, one prefix. Nothing else pins them together, so a rename on either side would
    silence every sound in the browser without failing a test."""
    assert AUDIO_META.startswith(session._OURS)


class _Request:
    def __init__(self, agent: str) -> None:
        self.headers = {"User-Agent": agent}


_PHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15"
_DESKTOP = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120"


def test_a_touch_session_is_told_it_is_one() -> None:
    """The only wiring point of the whole touch layout: UA -> env var -> `-touch` on every screen."""
    server = session.TermCadeServer("true", public_url="http://localhost:8000")

    assert server.session_env(_Request(_PHONE)) == {session.TOUCH_ENV: "1"}


def test_a_desktop_session_is_told_nothing_extra() -> None:
    server = session.TermCadeServer("true", public_url="http://localhost:8000")

    assert server.session_env(_Request(_DESKTOP)) == {}


def test_the_open_server_refuses_nobody() -> None:
    """Only the beta gate rejects; without a passcode file the server is open, as it was before."""
    server = session.TermCadeServer("true", public_url="http://localhost:8000")

    assert server.reject(_Request(_DESKTOP)) is False
