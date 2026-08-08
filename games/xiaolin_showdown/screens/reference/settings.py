"""Settings screen — edit the ruleset before starting a game.

Each ``XiaolinSettings`` field is an integer input, plus the Easy/Hard/Boss difficulty toggle (which
picks both the opponent roster and the bot's deposit skill). Saving writes the values back through
the engine's ``SettingsStore`` (global defaults for new games); a new game then reads them via
``XiaolinSettings.from_settings`` and the engine freezes them into that save.
"""

from __future__ import annotations

from dataclasses import fields, replace
from typing import cast

from textual import events
from textual.app import ComposeResult
from textual.containers import Center, Horizontal
from textual.widgets import Footer, Header, Input, Static

from termcade.core.audio import MUSIC_OPTION, SFX_OPTION
from termcade.core.settings import Difficulty
from termcade.ui.app import EngineApp
from termcade.ui.widgets import BoxedPanel, Button

from ...logic.config.ladder import boss_tier_unlocked
from ...logic.config.settings import XiaolinSettings, deal_target, deck_size_for, roster_of
from ...logic.schema.catalog import load_catalog
from ..base import XiaolinScreen

# The difficulty button cycles these in order. NORMAL (an old file or the engine default) folds to EASY.
# BOSS only enters the cycle once the ladder has opened it — see `_cycle`.
_DIFFICULTY_CYCLE = (Difficulty.EASY, Difficulty.HARD, Difficulty.BOSS)

# Friendlier wording than the generic `field.name.title()` for a field whose plain name reads flat
# out of context. Anything not listed falls back to the generic title-case.
_FIELD_LABELS: dict[str, str] = {
    "empty_draw_limit": "On Empty Draw Limit",
    "prize_threshold": "Win Prize Stat Threshold",
    "max_wager": "Max Wu Wager",
    "wear_limit": "Wear Wu Limit",
    "stat_cap": "Training Stat Cap",
}

# `random_background` gets its own button (see `_background_label`), not a generic Input row.
_HIDDEN_FIELDS = frozenset({"random_background"})

# A player/bot pair renders as one row, two columns, instead of two separate label rows.
_PAIRS: dict[str, tuple[str, str, str]] = {
    "actions_per_turn_player": ("Actions Per Turn", "actions_per_turn_player", "actions_per_turn_bot"),
    "max_hand_size_player": ("Max Hand Size", "max_hand_size_player", "max_hand_size_bot"),
    "starting_hand_player": ("Starting Hand", "starting_hand_player", "starting_hand_bot"),
    "starting_points_player": ("Starting Points", "starting_points_player", "starting_points_bot"),
    "train_length_player": ("Training Length", "train_length_player", "train_length_bot"),
    "loss_fill_player": ("On Loss Fill Bar", "loss_fill_player", "loss_fill_bot"),
}
# Only the BOT half is hidden from the generic loop — the player half is the trigger key that
# _PAIRS itself is keyed on, so it must stay visible to reach the `field.name in _PAIRS` branch.
_PAIRED_FIELDS = frozenset({bot_field for _, _, bot_field in _PAIRS.values()})


def _label_for(field_name: str) -> str:
    return _FIELD_LABELS.get(field_name, field_name.replace("_", " ").title())


def _out_of_range_message(adjusted: dict[str, tuple[int, int]]) -> str:
    """A human line per value the clamp had to change, for the invalid-settings toast."""
    return "\n".join(
        f"{_label_for(name)}: {entered} isn't allowed, nearest valid is {ok}."
        for name, (entered, ok) in adjusted.items()
    )


def _difficulty_label(difficulty: Difficulty) -> str:
    return f"Difficulty:  {difficulty.value.upper()}"


def _background_label(random: bool) -> str:
    return f"Arena Element:  {'RANDOM' if random else 'CHOSEN'}"


def _music_label(on: bool) -> str:
    return f"Music:  {'ON' if on else 'OFF'}"


def _sfx_label(on: bool) -> str:
    return f"Sound FX:  {'ON' if on else 'OFF'}"


class SettingsScreen(XiaolinScreen):
    BINDINGS = [("escape", "app.pop_screen", "Back")]

    # The pending choices, toggled by their buttons and only written on Save.
    # Three states — Easy, Hard, Boss; never NORMAL.
    _difficulty: Difficulty = Difficulty.EASY
    _random_background: bool = True
    _music: bool = True
    _sfx: bool = True
    _boss_unlocked: bool = False

    def _cycle(self) -> tuple[Difficulty, ...]:
        """The states the difficulty button cycles through — BOSS only once the ladder has opened it."""
        return _DIFFICULTY_CYCLE if self._boss_unlocked else _DIFFICULTY_CYCLE[:2]

    def on_descendant_focus(self, event: events.DescendantFocus) -> None:
        """A numeric field starts with its whole value selected — otherwise the cursor drops at
        column 0 (Textual's default) and a typed digit is INSERTED into the old number instead of
        replacing it, e.g. clicking "50" and typing "30" left "3050" on the field."""
        if isinstance(event.widget, Input):
            event.widget.select_all()

    def compose(self) -> ComposeResult:
        current = self.ctx.settings.current
        self._boss_unlocked = boss_tier_unlocked(current)
        cycle = self._cycle()
        self._difficulty = current.difficulty if current.difficulty in cycle else Difficulty.EASY
        self._music = bool(current.options.get(MUSIC_OPTION, True))
        self._sfx = bool(current.options.get(SFX_OPTION, True))
        rules = self.rules
        self._random_background = bool(rules.random_background)
        yield Header()
        with BoxedPanel(title="GENERAL SETTINGS", id="general-panel"):
            with Center():
                yield Button(_music_label(self._music), id="music")
            with Center():
                yield Button(_sfx_label(self._sfx), id="sfx")
        with BoxedPanel(title="GAME SETTINGS", id="game-settings-panel"):
            yield from self._setting_rows(rules)
            with Center():
                yield Button(_background_label(self._random_background), id="background")
            with Center():
                yield Button(_difficulty_label(self._difficulty), id="difficulty")
            if not self._boss_unlocked:
                with Center():
                    yield Static("Beat HARD to unlock BOSS stages!", classes="setting-hint")
        # Directly under GAME SETTINGS, left-aligned with the panels above it. On a screen too short
        # for all of it, the screen itself scrolls to reach it (the engine default).
        yield Button("Save", id="save", variant="primary")
        yield Footer()

    def on_mount(self) -> None:
        # Deck Size / Point Limit must read as this difficulty's own numbers the instant the screen
        # opens, not only after a toggle — the widgets exist now, so the same reset the toggle uses
        # runs once here too.
        self._reset_deal_fields()

    def _setting_rows(self, rules: XiaolinSettings) -> ComposeResult:
        """Every shared (single-value) field first, then the player/bot pairs together at the end as
        one two-column row each (see `_PAIRS`), a "|" between the columns. `max_deck_size` carries a
        tooltip naming the pool it is capped at."""
        pool_size = deck_size_for(load_catalog().cards)
        for field in fields(XiaolinSettings):
            if field.name in _HIDDEN_FIELDS or field.name in _PAIRS or field.name in _PAIRED_FIELDS:
                continue
            row_input = Input(
                value=str(getattr(rules, field.name)), id=f"set-{field.name}", type="integer"
            )
            if field.name == "max_deck_size":
                row_input.tooltip = f"The card pool has {pool_size} Wu,\nthe most a run can deal."
            yield Horizontal(
                Static(_label_for(field.name), classes="setting-label"), row_input, classes="setting-row"
            )
        yield Horizontal(
            Static("", classes="setting-label"),
            Static("Player", classes="pair-heading"),
            Static("|", classes="pair-divider"),
            Static("Bot", classes="pair-heading"),
            classes="setting-row",
        )
        for label, player_field, bot_field in _PAIRS.values():
            yield Horizontal(
                Static(label, classes="setting-label"),
                Input(
                    value=str(getattr(rules, player_field)),
                    id=f"set-{player_field}", type="integer", classes="pair-input",
                ),
                Static("|", classes="pair-divider"),
                Input(
                    value=str(getattr(rules, bot_field)),
                    id=f"set-{bot_field}", type="integer", classes="pair-input",
                ),
                classes="setting-row",
            )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "background":
            self._toggle_background()
            return
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
        values = {"random_background": 1 if self._random_background else 0}
        for field in fields(XiaolinSettings):
            if field.name in _HIDDEN_FIELDS:
                continue
            raw = self.query_one(f"#set-{field.name}", Input).value
            values[field.name] = int(raw) if raw else getattr(XiaolinSettings(), field.name)
        coerced, adjusted = XiaolinSettings.coerce(values)
        # The pool size isn't known inside XiaolinSettings.coerce (settings stays DB-free), so the
        # two clamps that need the catalog are checked here instead.
        pool_size = deck_size_for(load_catalog().cards)
        hands = values["starting_hand_player"] + values["starting_hand_bot"]
        extra_message = None
        if hands > pool_size:
            # The real problem: dealing both opening hands would empty (or overrun) the pool before
            # the run even starts. Diagnosed ahead of the deck-size check below, which `min_deck` in
            # `__post_init__` would otherwise inflate to cover this same shortfall and misreport.
            extra_message = (
                f"Starting Hand: {values['starting_hand_player']} + {values['starting_hand_bot']} "
                f"leaves no room in a pool of {pool_size}."
            )
        elif coerced.max_deck_size > pool_size:
            adjusted = {**adjusted, "max_deck_size": (values["max_deck_size"], pool_size)}
        if adjusted or extra_message:
            # Flag an out-of-range value as a toast rather than silently doing nothing, and keep the
            # screen open so the player can fix it.
            lines = [_out_of_range_message(adjusted)] if adjusted else []
            if extra_message:
                lines.append(extra_message)
            self.app.notify("\n".join(lines), title="Invalid settings", severity="warning")
            # The toast says what changed; this says where to look. Both Starting Hand fields flash
            # on the pool-overflow message — neither one alone was out of range, only their sum.
            rejected = list(adjusted)
            if extra_message:
                rejected += ["starting_hand_player", "starting_hand_bot"]
            self._flash_rejected(rejected)
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
        cycle = self._cycle()
        nxt = (cycle.index(self._difficulty) + 1) % len(cycle)
        self._difficulty = cycle[nxt]
        self.query_one("#difficulty", Button).label = _difficulty_label(self._difficulty)
        self._reset_deal_fields()

    def _reset_deal_fields(self) -> None:
        """Snap Max Deck Size / Point Limit back to this difficulty's natural deal (`deal_target`) —
        the two knobs that scale by roster so a run doesn't run long. Fires on every difficulty toggle,
        discarding whatever was typed for the tier just left; Save is still what commits them."""
        from ...logic.schema.catalog import load_catalog  # local: settings must not drag in the DB

        def _hand(name: str) -> int:
            raw = self.query_one(f"#set-{name}", Input).value
            return int(raw) if raw else getattr(XiaolinSettings(), name)

        probe = XiaolinSettings(
            starting_hand_player=_hand("starting_hand_player"),
            starting_hand_bot=_hand("starting_hand_bot"),
        )
        deck_size, point_limit = deal_target(roster_of(self._difficulty), load_catalog().cards, probe)
        self.query_one("#set-max_deck_size", Input).value = str(deck_size)
        self.query_one("#set-point_limit", Input).value = str(point_limit)

    def _flash_rejected(self, field_names: list[str]) -> None:
        inputs = [self.query_one(f"#set-{name}", Input) for name in field_names]

        def add() -> None:
            for field in inputs:
                field.add_class("rejected")

        def remove() -> None:
            for field in inputs:
                field.remove_class("rejected")

        self.set_timer(0.05, add)
        self.set_timer(0.55, remove)

    def _toggle_background(self) -> None:
        self._random_background = not self._random_background
        self.query_one("#background", Button).label = _background_label(self._random_background)

    def _toggle_music(self) -> None:
        self._music = not self._music
        self.query_one("#music", Button).label = _music_label(self._music)

    def _toggle_sfx(self) -> None:
        self._sfx = not self._sfx
        self.query_one("#sfx", Button).label = _sfx_label(self._sfx)
