"""``EngineApp._use_browser_audio``: resolving the driver's meta channel and swapping in a
:class:`~termcade.core.audio.BrowserPlayer` — the one place the engine reaches into Textual's
driver, so ``core.audio.browser_player`` itself never has to.
"""

from __future__ import annotations

from termcade.core.audio import BrowserPlayer
from termcade.ui.app import EngineApp


async def test_a_headless_session_keeps_its_device_player() -> None:
    """The test driver has no ``write_meta`` — same shape as a real terminal session."""
    app = EngineApp()
    async with app.run_test():
        assert not isinstance(app._player, BrowserPlayer)


async def test_a_driver_with_a_meta_channel_gets_a_browser_player(monkeypatch) -> None:
    """Only ``write_meta`` is faked, on the app's REAL driver — swapping the whole driver object
    breaks Textual's own shutdown, which reads several other attributes off it."""
    app = EngineApp()
    async with app.run_test():
        monkeypatch.delenv("TERMCADE_MUTE", raising=False)

        def write_meta(message: dict[str, object]) -> None:
            return None

        monkeypatch.setattr(app._driver, "write_meta", write_meta, raising=False)

        app._use_browser_audio()

        assert isinstance(app._player, BrowserPlayer)
