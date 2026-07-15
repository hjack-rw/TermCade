"""The dev console — ``~`` opens it, and a cartridge fills it with commands.

**It is a workbench, not a cheat menu.** A card game is unplaytestable without one: a new Wu is worth
whatever it does in a real showdown, and waiting for a 40-card pile to deal it to you is not a test, it
is a wait. The console puts the Wu in your hand, stacks the pile, and lets you play the thing you are
trying to judge.

**A pop-up over the game, not a screen instead of it.** The board stays behind the console, dimmed —
which is the whole point: you conjure a Wu, and you *watch the hand it lands in*. A full screen would
hide the thing you are trying to change, and you would be typing blind.

**Locked, not merely hidden.** It exists only when ``TERMCADE_DEBUG`` is set (``1``/``true``/``yes``) —
see :func:`debug_enabled`. A shipped game has no console at all: the key does nothing, the screen is
never built, and no amount of guessing finds it. Hiding a thing is not the same as not having it, and a
tool that can hand a player any card in the game is worth the difference.

The engine owns the console; the *game* owns the commands. `Game.console_commands` is a mapping of name
to :class:`Command`, and each one is handed the running :class:`GameContext` plus whatever arguments were
typed. The engine supplies only ``help`` — everything a command can *do* is the cartridge's business,
because only the cartridge knows what a Wu is.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import cast

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Input, Static

from termcade.app.game import Game, GameContext
from termcade.ui.typography import spaced_dashes
from termcade.ui.widgets import BoxedPanel

DEBUG_ENV = "TERMCADE_DEBUG"


def debug_enabled() -> bool:
    """Is this a development run? Read fresh every time — a test may set it mid-flight.

    The console can deal a player any Wu in the game, so it is not a thing to leave lying in a shipped
    build behind an undocumented key. It is *absent* unless asked for:

        TERMCADE_DEBUG=1 xiaolin
    """
    import os

    return os.environ.get(DEBUG_ENV, "").strip().lower() in ("1", "true", "yes", "on")


class _CommandLine(Input):
    """The console's field — and the only place the closing key can be caught.

    A focused ``Input`` swallows every printable key to type it, *before* any binding is consulted —
    app-level and `priority=True` included. So the backtick that opens the console was being typed into
    it instead of shutting it, and no binding anywhere could have stopped that. The field has to refuse
    the character itself.
    """

    def on_key(self, event: events.Key) -> None:
        if event.key in ("grave_accent", "tilde"):
            event.stop()
            event.prevent_default()
            self.screen.dismiss()


@dataclass(frozen=True)
class Command:
    """One console command: what it does, and the one line that says so.

    ``run`` is handed the live :class:`GameContext` and the words that followed the command. It returns
    what to print — a command that returns nothing at all still gets an acknowledgement, so a player is
    never left wondering whether the key was even read.
    """

    run: Callable[[GameContext, Sequence[str]], str | None]
    help: str


class ConsoleScreen(ModalScreen[None]):
    """Type a command, read what it says, type another. Escape drops you back into the game behind it.

    A `ModalScreen` and not an `EngineScreen`: the game stays *visible* underneath, so a Wu conjured
    into a hand can be watched landing in it. It therefore cannot inherit `EngineScreen`'s `ctx`/`game`
    helpers, so it reaches for them the same way that class does.
    """

    # Escape only. The backtick TOGGLE lives on `EngineApp`, and it has to: an app-level priority
    # binding fires before any of the console's own, so a "close" binding here would race the "open"
    # binding there — they popped and re-pushed each other and the console never shut.
    BINDINGS = [Binding("escape", "dismiss", "Back", show=True)]

    @property
    def ctx(self) -> GameContext:
        ctx = getattr(self.app, "ctx", None)
        assert ctx is not None, "the console has no GameContext"
        return cast(GameContext, ctx)

    @property
    def game(self) -> Game:
        game = getattr(self.app, "game", None)
        assert game is not None, "the console has no Game"
        return cast(Game, game)

    def compose(self) -> ComposeResult:
        # The transcript is kept HERE, not read back off the widget. A rendered widget is the last place
        # to store anything — `Static.renderable` does not even exist any more, and code that reached for
        # it broke silently when Textual moved on.
        self._lines: list[Text] = [_greeting(self._commands())]

        with BoxedPanel(title="CONSOLE"):
            with VerticalScroll(id="console-log"):
                yield Static(self._transcript(), id="console-output")
            # A prompt glyph beside the field, because a bare Input on a dark panel reads as *nothing*:
            # the border is one shade off the background and an empty field has nothing in it to see.
            # The caret is what says "type here", and it costs one character.
            with Horizontal(id="console-prompt"):
                yield Static("❯", id="console-caret")
                yield _CommandLine(
                    placeholder="try:  help   ·   find blank   ·   refresh", id="console-input"
                )

    def _transcript(self) -> Text:
        return Text("\n").join(self._lines)

    def on_mount(self) -> None:
        self.query_one("#console-input", Input).focus()

    def _commands(self) -> dict[str, Command]:
        return dict(self.game.console_commands)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        typed = event.value.strip()
        event.input.value = ""
        if not typed:
            return

        self._say(Text(f"> {typed}", style="bold"))
        self._say(self._answer(typed))

    def _answer(self, typed: str) -> Text:
        """Run what was typed, and never let a bad command take the game with it.

        A console is where a person experiments, and experiments raise exceptions. One that killed the
        run would make the tool useless for the thing it exists for.
        """
        name, *args = typed.split()
        commands = self._commands()

        if name in ("help", "?"):
            return _help(commands)
        if name not in commands:
            return Text(f"no such command: {name!r} — try `help`", style="red")

        try:
            answer = commands[name].run(self.ctx, args)
        except Exception as error:  # noqa: BLE001 — a console must survive its own commands
            return Text(f"{type(error).__name__}: {error}", style="red")
        return Text(answer or "done.", style="green")

    def _say(self, line: Text) -> None:
        self._lines.append(line)
        self.query_one("#console-output", Static).update(self._transcript())
        self.query_one("#console-log", VerticalScroll).scroll_end(animate=False)


def _greeting(commands: dict[str, Command]) -> Text:
    return Text.assemble(
        Text("The console.", style="bold"),
        Text(f"  {len(commands)} commands. Type `help` to see them, Escape to go back.\n"),
    )


def _help(commands: dict[str, Command]) -> Text:
    """The names bright, everything explaining them dim.

    Two weights, not one: the *name* is what a reader is scanning for, and a description drawn as loudly
    as the name it describes competes with it. Bright is what you type; dim is what it means.
    """
    if not commands:
        return Text("this game supplies no commands.", style="dim")

    width = max(len(name) for name in commands)
    lines = [
        Text.assemble(
            Text(f"{name:<{width}}  ", style="bold"),
            Text(spaced_dashes(command.help), style="dim"),
        )
        for name, command in sorted(commands.items())
    ]
    return Text("\n").join(lines)
