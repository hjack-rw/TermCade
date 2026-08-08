"""``apply_music_setting``'s crossfade argument, on the branch that has to render a tune first.

The cached-tune branch forwards ``crossfade`` straight to ``play_loop`` — never in question. The
not-cached branch defers to ``_start_theme``, which reads ``self._crossfade`` instead of taking a
parameter; nothing wired the caller's argument into that attribute, so a requested crossfade into a
tune's first play was silently dropped and it hard-cut instead.
"""

from __future__ import annotations

from termcade.ui.app import EngineApp


async def test_a_crossfade_into_an_unrendered_tune_reaches_start_theme(monkeypatch):
    app = EngineApp()
    async with app.run_test():
        app._tunes.clear()  # boot's own on_mount already rendered the attract theme — force a re-render
        started = []
        monkeypatch.setattr(app, "_start_theme", lambda: started.append(app._crossfade))

        app.apply_music_setting(crossfade=2.5)

        assert started == [2.5]


async def test_no_crossfade_requested_leaves_it_at_zero(monkeypatch):
    app = EngineApp()
    async with app.run_test():
        app._tunes.clear()
        started = []
        monkeypatch.setattr(app, "_start_theme", lambda: started.append(app._crossfade))

        app.apply_music_setting()

        assert started == [0.0]
