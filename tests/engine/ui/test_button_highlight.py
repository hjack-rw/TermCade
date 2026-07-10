"""A styled Button label yields its colour while highlighted, so the CSS highlight applies whole.

The flattening happens at render time. ``label`` keeps its colour throughout, so a screen may
reassign it (``SettingsScreen`` retitles its difficulty button) without the highlight resurrecting
an older label.
"""

from __future__ import annotations

from rich.text import Text
from textual.app import App, ComposeResult

from termcade.ui.widgets import Button


class _App(App):
    AUTO_FOCUS = ""  # as EngineApp does: nothing is focused until the player tabs in

    def compose(self) -> ComposeResult:
        yield Button(Text("Changing Chopsticks", style="#ff5555"), id="wu")


def _spans(button):
    """The spans the button actually paints — not the label it stores."""
    return button.render().spans


async def test_a_styled_label_keeps_its_colour_at_rest():
    async with _App().run_test() as pilot:
        button = pilot.app.query_one("#wu", Button)
        assert not button.has_focus  # AUTO_FOCUS="" — genuinely at rest
        assert _spans(button), "element colour lost at rest"


async def test_a_focused_label_drops_its_colour_so_the_highlight_wins():
    async with _App().run_test() as pilot:
        button = pilot.app.query_one("#wu", Button)
        button.focus()
        await pilot.pause()
        assert not _spans(button), "focused label kept an inline colour; the highlight cannot win"


async def test_a_hovered_label_drops_its_colour_too():
    async with _App().run_test() as pilot:
        button = pilot.app.query_one("#wu", Button)
        await pilot.hover("#wu")
        await pilot.pause()
        assert not _spans(button), "hovered label kept an inline colour"


async def test_the_colour_returns_when_the_highlight_leaves():
    async with _App().run_test() as pilot:
        button = pilot.app.query_one("#wu", Button)
        button.focus()
        await pilot.pause()
        pilot.app.set_focus(None)
        await pilot.pause()
        assert _spans(button), "colour never came back"


class _RelabelApp(App):
    AUTO_FOCUS = ""

    def compose(self) -> ComposeResult:
        yield Button("Difficulty: Easy", id="d")
        yield Button("elsewhere", id="away")


async def test_relabelling_a_button_survives_a_later_highlight():
    """A screen may rewrite a label (SettingsScreen does). The highlight must restore *that*, not
    whatever the button was constructed with."""
    async with _RelabelApp().run_test(size=(60, 12)) as pilot:
        button = pilot.app.query_one("#d", Button)
        button.label = "Difficulty: Hard"
        await pilot.pause()

        await pilot.hover("#d")
        await pilot.pause()
        await pilot.hover("#away")
        await pilot.pause()

        assert button.label.plain == "Difficulty: Hard"


async def test_a_relabelled_button_still_flattens_while_hovered():
    async with _RelabelApp().run_test(size=(60, 12)) as pilot:
        button = pilot.app.query_one("#d", Button)
        button.label = Text("Difficulty: Hard", style="#ff5555")
        await pilot.pause()

        await pilot.hover("#d")
        await pilot.pause()

        assert not _spans(button)
