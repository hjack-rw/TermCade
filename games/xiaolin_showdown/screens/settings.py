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
        edited = XiaolinSettings(**values).to_settings(self.ctx.settings.current)
        self.ctx.settings.save(edited)
        self.app.pop_screen()
