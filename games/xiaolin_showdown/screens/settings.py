"""Settings screen — edit the ruleset before starting a game.

Each ``XiaolinSettings`` field is an integer input, plus the Easy/Hard difficulty toggle (which
picks both the opponent roster and the bot's deposit skill). Saving writes the values back through
the engine's ``SettingsStore`` (global defaults for new games); a new game then reads them via
``XiaolinSettings.from_settings`` and the engine freezes them into that save.
"""

from __future__ import annotations

from dataclasses import fields, replace

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, Footer, Header, Input, Static

from termcade.core.settings import Difficulty
from termcade.ui.screens.base import EngineScreen
from termcade.ui.widgets import BoxedPanel

from ..logic.settings import XiaolinSettings, is_hard


def _out_of_range_message(adjusted: dict[str, tuple[int, int]]) -> str:
    """A human line per value the clamp had to change, for the invalid-settings toast."""
    return "\n".join(
        f"{name.replace('_', ' ').title()}: {entered} isn't allowed — nearest valid is {ok}."
        for name, (entered, ok) in adjusted.items()
    )


def _difficulty_label(difficulty: Difficulty) -> str:
    return f"Difficulty:  {difficulty.value.upper()}"


class SettingsScreen(EngineScreen):
    BINDINGS = [("escape", "app.pop_screen", "Back")]

    # The pending choice, toggled by the button and only written on Save. Two states, never NORMAL.
    _difficulty: Difficulty = Difficulty.EASY

    def compose(self) -> ComposeResult:
        current = self.ctx.settings.current
        self._difficulty = Difficulty.HARD if is_hard(current.difficulty) else Difficulty.EASY
        rules = XiaolinSettings.from_settings(current)
        yield Header()
        with BoxedPanel(title="SETTINGS"):
            for field in fields(XiaolinSettings):
                label = field.name.replace("_", " ").title()
                yield Horizontal(
                    Static(label, classes="setting-label"),
                    Input(value=str(getattr(rules, field.name)), id=f"set-{field.name}", type="integer"),
                    classes="setting-row",
                )
            yield Button(_difficulty_label(self._difficulty), id="difficulty")
            yield Button("Save", id="save", variant="primary")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "difficulty":
            self._toggle_difficulty()
            return
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
        # The toggle only lands here, on Save — an abandoned screen changes nothing.
        base = replace(self.ctx.settings.current, difficulty=self._difficulty)
        self.ctx.settings.save(coerced.to_settings(base))
        self.app.pop_screen()

    def _toggle_difficulty(self) -> None:
        self._difficulty = Difficulty.EASY if self._difficulty is Difficulty.HARD else Difficulty.HARD
        self.query_one("#difficulty", Button).label = _difficulty_label(self._difficulty)
