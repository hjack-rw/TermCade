"""Outcome screen — the final scoreboard when the run ends.

Shown once the draw pile is spent (or a point limit is reached): final points, the winner (or a
tie), and a way on — play again with a fresh dragon, back to the menu, or quit.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.widgets import Footer, Header, Static

from termcade.ui.widgets import BoxedPanel, Button

from ...logic.flow.outcome import Outcome
from ..base import XiaolinScreen
from ..display.format import display_name

# A seed of its own (see `EngineApp.play_tune`) — the win jingle has to sound like an unrelated
# piece, not the temple's theme sped up and transposed.
VICTORY_SEED = "xiaolin_showdown:victory"

# Just enough that the fanfare's first note isn't fighting the theme's for the same instant — not
# the whole buildup, which would leave the theme with nothing left to intersect.
VICTORY_FANFARE_DELAY = 0.05

# Slower than the cabinet's own MUSIC_CROSSFADE: the theme has to stay behind the fanfare while it's
# still ringing, not climb to full volume partway through it and crowd the thing it's building up to.
VICTORY_THEME_CROSSFADE = 3.0

# How long `end_run` (see base.py) holds the prior screen before switching to this one. The music
# is started there, before the switch — this is what gives it a beat's head start rather than
# starting cold the instant GAME OVER appears, while still leaving the last duel on screen long
# enough to read before the screen changes under it.
OUTCOME_TRANSITION_DELAY = 0.4


class OutcomeScreen(XiaolinScreen):
    def __init__(self, outcome: Outcome) -> None:
        super().__init__()
        self._outcome = outcome

    def compose(self) -> ComposeResult:
        outcome = self._outcome
        verdict = (
            "A TIE —  NOBODY WINS!"
            if outcome.winner is None
            else f"{display_name(outcome.winner.name, upper=True)} WINS!"
        )

        yield Header()
        with BoxedPanel(title="GAME OVER"):
            yield Static(f"Final points: {outcome.player_points} / {outcome.bot_points}", id="final-points")
            yield Static(verdict, id="verdict")
            yield Button("Play Again", id="again", variant="primary")
            yield Button("Menu", id="menu")
            yield Button("Quit", id="quit")
        yield Footer()

    def on_mount(self) -> None:
        # The music itself is already playing by the time this screen mounts — started in
        # `end_run` (see base.py), a beat before the switch that brought this screen up.
        outcome = self._outcome
        if outcome.winner is None:
            pulse_class = "pulse-tie"
        elif outcome.winner is self.state.player.character:
            pulse_class = "pulse-win"
        else:
            pulse_class = "pulse-loss"
        verdict = self.query_one("#verdict", Static)
        # Add the class a beat after mount, not in compose: a transition only animates a *change*,
        # so starting the background already coloured would just paint it, not pulse it.
        self.set_timer(0.05, lambda: verdict.add_class(pulse_class))
        self.set_timer(0.55, lambda: verdict.remove_class(pulse_class))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        # Lazy imports keep the screen-transition graph free of import cycles.
        if event.button.id == "again":
            from .character_select import CharacterSelectScreen

            self.app.switch_screen(CharacterSelectScreen())
        elif event.button.id == "menu":
            from .start import StartScreen

            self.app.switch_screen(StartScreen())
        elif event.button.id == "quit":
            self.app.exit()
