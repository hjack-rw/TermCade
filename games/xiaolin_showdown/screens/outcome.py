"""Outcome screen — the final scoreboard when the run ends.

Shown once the draw pile is spent (or a point limit is reached): final points, the winner (or a
tie), and a way on — play again with a fresh dragon, back to the menu, or quit.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.widgets import Footer, Header, Static

from termcade.ui.widgets import BoxedPanel, Button

from ..logic.outcome import final_score
from .base import XiaolinScreen
from .format import display_name


class OutcomeScreen(XiaolinScreen):
    def compose(self) -> ComposeResult:
        outcome = final_score(self.state, self.ctx.rng)
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
