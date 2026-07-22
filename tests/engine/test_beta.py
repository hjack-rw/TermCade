"""The closed-beta gate: which passcodes open the door, and whose saves they open onto."""

from __future__ import annotations

import pytest
from aiohttp.test_utils import TestClient, TestServer

from termcade import beta, session, web_driver
from termcade.app.game import Game, GameContext

_CODE = "beta-alpha-1"
_OTHER = "beta-bravo-2"


@pytest.fixture
def codes_file(tmp_path):
    path = tmp_path / "codes.txt"
    path.write_text(f"# beta testers\n{_CODE}\n{_OTHER}\n\n", encoding="utf-8")
    return path


def test_comments_and_blank_lines_are_not_passcodes(codes_file) -> None:
    assert beta.load_codes(codes_file) == frozenset({_CODE, _OTHER})


def test_a_missing_codes_file_admits_nobody(tmp_path) -> None:
    """A typo'd path must close the beta, never open it."""
    assert beta.load_codes(tmp_path / "absent.txt") == frozenset()


def test_a_malformed_line_never_becomes_a_passcode(tmp_path) -> None:
    """The file is as untrusted as the player: a bad line there would become a directory name."""
    path = tmp_path / "codes.txt"
    path.write_text(f"../../etc\n$(whoami)\nwith space\n{_CODE}\n", encoding="utf-8")
    assert beta.load_codes(path) == frozenset({_CODE})


@pytest.mark.parametrize(
    "code",
    ["../escape", "a", "x" * 33, "code;rm -rf /", "code with space", "", "code$(id)", "sub/dir"],
)
def test_codes_that_could_mean_something_elsewhere_are_refused(code: str) -> None:
    """``Server.command`` is run through a shell and the code names a directory — so the safe set
    is the one that is inert in both."""
    assert not beta.is_well_formed(code)


def test_two_passcodes_get_two_directories(tmp_path) -> None:
    assert beta.player_dir(tmp_path, _CODE) != beta.player_dir(tmp_path, _OTHER)


def test_a_passcode_maps_to_the_same_directory_every_time(tmp_path) -> None:
    """A tester who comes back must find their saves where they left them."""
    assert beta.player_dir(tmp_path, _CODE) == beta.player_dir(tmp_path, _CODE)


def test_the_directory_does_not_spell_out_the_passcode(tmp_path) -> None:
    assert _CODE not in str(beta.player_dir(tmp_path, _CODE))


class _State:
    """The smallest thing the save layer accepts; the engine never looks inside a snapshot."""

    schema_version = 1

    def snapshot(self) -> dict:
        return {}

    @classmethod
    def restore(cls, data: dict, ctx) -> "_State":  # type: ignore[no-untyped-def]
        return cls()


def test_two_players_saves_do_not_collide(tmp_path) -> None:
    """The defect this whole gate exists to fix: same slot, two players, both saves survive."""
    game = Game(game_id="demo", title="Demo", state_cls=_State)
    contexts = {
        code: GameContext(game, data_dir=beta.player_dir(tmp_path, code))
        for code in (_CODE, _OTHER)
    }
    for code, ctx in contexts.items():
        ctx.saves.save(0, _State(), ctx.rng, title=code)

    assert [ctx.saves.list()[0].title for ctx in contexts.values()] == [_CODE, _OTHER]


# --- the door -------------------------------------------------------------------------------
# Driven through a real aiohttp client rather than a stub request, because the thing most likely to
# break is not the check — it is the check being wired into the app at all.

@pytest.fixture
def server(codes_file, tmp_path):
    return beta.BetaServer(
        "true", codes_path=codes_file, data_dir=tmp_path, public_url="http://localhost:8000"
    )


@pytest.fixture
async def client(server):
    async with TestClient(TestServer(await server._make_app())) as client:
        yield client


async def test_the_door_is_shut_without_a_passcode(client) -> None:
    assert (await client.get("/", allow_redirects=False)).status == 401


async def test_a_code_that_is_not_on_the_list_is_refused(client) -> None:
    response = await client.get("/", params={"code": "beta-zulu-9"}, allow_redirects=False)
    assert response.status == 401


async def test_a_valid_code_is_moved_out_of_the_url_into_a_cookie(client) -> None:
    """So the passcode does not ride in the address bar for the length of the beta."""
    response = await client.get("/", params={"code": _CODE}, allow_redirects=False)
    assert response.status == 302
    assert response.cookies[beta.COOKIE].value == _CODE


async def test_the_page_assets_are_behind_the_gate_too(client) -> None:
    """An unauthenticated fetch of anything, not just the index."""
    assert (await client.get("/static/js/textual.js", allow_redirects=False)).status == 403


async def test_a_passcode_holder_reaches_the_assets(client) -> None:
    await client.get("/", params={"code": _CODE})
    assert (await client.get("/static/js/textual.js", allow_redirects=False)).status == 200


async def test_removing_a_line_locks_that_tester_out(client, codes_file) -> None:
    """Revocation is editing the file — so the codes are re-read per request, never cached.

    Driven through the real client on purpose. The old version of this test called ``load_codes``
    twice and asserted a file-reading function reads files, which is true of any implementation:
    caching the set in ``BetaServer.__init__`` would have left it green while revocation quietly
    stopped working — and revocation is the only reason the gate exists.
    """
    await client.get("/", params={"code": _CODE})
    assert (await client.get("/", allow_redirects=False)).status == 200

    codes_file.write_text(_OTHER, encoding="utf-8")

    assert (await client.get("/", allow_redirects=False)).status == 401


def test_the_session_subprocess_is_told_its_own_data_dir(tmp_path) -> None:
    """The whole point of the ``AppService`` subclass: upstream copies our environment verbatim, so
    without this every session resolves the same save directory."""
    service = session.TermCadeAppService(
        "true",
        extra_env={beta.DATA_DIR_ENV: str(beta.player_dir(tmp_path, _CODE))},
        write_bytes=None, write_str=None, close=None, download_manager=None,
    )

    environment = service._build_environment()

    assert environment[beta.DATA_DIR_ENV] == str(beta.player_dir(tmp_path, _CODE))


def test_the_rest_of_the_environment_still_reaches_the_subprocess(tmp_path) -> None:
    """Adding to the environment, not replacing it — the child still needs textual's own vars."""
    service = session.TermCadeAppService(
        "true", extra_env={beta.DATA_DIR_ENV: str(tmp_path)},
        write_bytes=None, write_str=None, close=None, download_manager=None,
    )

    assert service._build_environment()["TERM_PROGRAM"] == "textual"


def test_the_session_runs_the_engines_own_driver(tmp_path) -> None:
    """Upstream's driver takes a resize and never lays the app out again — see
    :mod:`termcade.web_driver`. The environment is where that substitution happens, so a session
    quietly falling back to `textual.drivers.web_driver` is a phone that no longer survives being
    turned over."""
    service = session.TermCadeAppService(
        "true", extra_env={beta.DATA_DIR_ENV: str(tmp_path)},
        write_bytes=None, write_str=None, close=None, download_manager=None,
    )

    assert service._build_environment()["TEXTUAL_DRIVER"] == web_driver.DRIVER
