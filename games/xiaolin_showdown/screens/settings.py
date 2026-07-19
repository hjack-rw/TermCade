"""Settings screen — edit the ruleset before starting a game.

Each ``XiaolinSettings`` field is an integer input, plus the Easy/Hard/Boss difficulty toggle (which
picks both the opponent roster and the bot's deposit skill). Saving writes the values back through
the engine's ``SettingsStore`` (global defaults for new games); a new game then reads them via
``XiaolinSettings.from_settings`` and the engine freezes them into that save.
"""

from __future__ import annotations

from dataclasses import fields, replace
from typing import cast

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Footer, Header, Input, Static

from termcade.core.audio import MUSIC_OPTION, SFX_OPTION
from termcade.core.settings import Difficulty
from termcade.ui.app import EngineApp
from termcade.ui.widgets import BoxedPanel, Button

from ..logic.settings import XiaolinSettings
from .base import XiaolinScreen

# The difficulty button cycles these in order. NORMAL (an old file or the engine default) folds to EASY.
_DIFFICULTY_CYCLE = (Difficulty.EASY, Difficulty.HARD, Difficulty.BOSS)


def _out_of_range_message(adjusted: dict[str, tuple[int, int]]) -> str:
    """A human line per value the clamp had to change, for the invalid-settings toast."""
    return "\n".join(
        f"{name.replace('_', ' ').title()}: {entered} isn't allowed — nearest valid is {ok}."
        for name, (entered, ok) in adjusted.items()
    )


def _difficulty_label(difficulty: Difficulty) -> str:
    return f"Difficulty:  {difficulty.value.upper()}"


def _music_label(on: bool) -> str:
    return f"Music:  {'ON' if on else 'OFF'}"


def _sfx_label(on: bool) -> str:
    return f"Sound FX:  {'ON' if on else 'OFF'}"


class SettingsScreen(XiaolinScreen):
    BINDINGS = [("escape", "app.pop_screen", "Back")]

    # The pending choices, toggled by their buttons and only written on Save.
    # Three states — Easy, Hard, Boss; never NORMAL.
    _difficulty: Difficulty = Difficulty.EASY
    _music: bool = True
    _sfx: bool = True

    def compose(self) -> ComposeResult:
        current = self.ctx.settings.current
        self._difficulty = (
            current.difficulty if current.difficulty in _DIFFICULTY_CYCLE else Difficulty.EASY
        )
        self._music = bool(current.options.get(MUSIC_OPTION, True))
        self._sfx = bool(current.options.get(SFX_OPTION, True))
        rules = self.rules
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
            yield Button(_music_label(self._music), id="music")
            yield Button(_sfx_label(self._sfx), id="sfx")
            yield Button("Save", id="save", variant="primary")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "difficulty":
            self._toggle_difficulty()
            return
        if event.button.id == "music":
            self._toggle_music()
            return
        if event.button.id == "sfx":
            self._toggle_sfx()
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
        # The toggles only land here, on Save — an abandoned screen changes nothing.
        base = replace(
            self.ctx.settings.current,
            difficulty=self._difficulty,
            options={
                **self.ctx.settings.current.options,
                MUSIC_OPTION: self._music,
                SFX_OPTION: self._sfx,
            },
        )
        self.ctx.settings.save(coerced.to_settings(base))
        # Silence (or the theme) has to arrive with the Save, not the next launch.
        cast(EngineApp, self.app).apply_music_setting()
        self.app.pop_screen()

    def _toggle_difficulty(self) -> None:
        nxt = (_DIFFICULTY_CYCLE.index(self._difficulty) + 1) % len(_DIFFICULTY_CYCLE)
        self._difficulty = _DIFFICULTY_CYCLE[nxt]
        self.query_one("#difficulty", Button).label = _difficulty_label(self._difficulty)

    def _toggle_music(self) -> None:
        self._music = not self._music
        self.query_one("#music", Button).label = _music_label(self._music)

    def _toggle_sfx(self) -> None:
        self._sfx = not self._sfx
        self.query_one("#sfx", Button).label = _sfx_label(self._sfx)
