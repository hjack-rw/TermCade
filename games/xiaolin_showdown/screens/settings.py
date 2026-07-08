"""Settings screen — edit the ruleset before starting a game.

Each ``XiaolinSettings`` field is an integer input. Saving writes the values back through the
engine's ``SettingsStore`` (global defaults for new games); a new game then reads them via
``XiaolinSettings.from_settings`` and the engine freezes them into that save.
"""

from __future__ import annotations

from dataclasses import fields

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, Footer, Header, Input, Static

from termcade.ui.screens.base import EngineScreen
from termcade.ui.widgets import BoxedPanel

from ..logic.settings import XiaolinSettings


def _out_of_range_message(adjusted: dict[str, tuple[int, int]]) -> str:
    """A human line per value the clamp had to change, for the invalid-settings toast."""
    return "\n".join(
        f"{name.replace('_', ' ').title()}: {entered} isn't allowed — nearest valid is {ok}."
        for name, (entered, ok) in adjusted.items()
    )


class SettingsScreen(EngineScreen):
    BINDINGS = [("escape", "app.pop_screen", "Back")]

    def compose(self) -> ComposeResult:
        rules = XiaolinSettings.from_settings(self.ctx.settings.current)
        yield Header()
        with BoxedPanel(title="SETTINGS"):
            for field in fields(XiaolinSettings):
                label = field.name.replace("_", " ").title()
                yield Horizontal(
                    Static(label, classes="setting-label"),
                    Input(value=str(getattr(rules, field.name)), id=f"set-{field.name}", type="integer"),
                    classes="setting-row",
                )
            yield Button("Save", id="save", variant="primary")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "save":
            return
        values = {}
        for field in fields(XiaolinSettings):
            raw = self.query_one(f"#set-{field.name}", Input).value
            values[field.name] = int(raw) if raw else getattr(XiaolinSettings(), field.name)
        coerced, adjusted = XiaolinSettings.coerce(values)
        if adjusted:
            # Don't silently accept an out-of-range value (which would just do nothing) — flag it as
            # a toast, like the bot-turn log, and keep the screen open so the player can fix it.
            self.app.notify(
                _out_of_range_message(adjusted), title="Invalid settings", severity="warning"
            )
            return
        self.ctx.settings.save(coerced.to_settings(self.ctx.settings.current))
        self.app.pop_screen()
