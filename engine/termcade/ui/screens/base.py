"""Base screen ("scene") shared by engine and game screens."""

from __future__ import annotations

from textual.screen import Screen


class EngineScreen(Screen[None]):
    """Common base for every termcade screen.

    A thin marker for now, so engine and game screens share one base type; typed
    ``ctx`` access (the ``GameContext``) and helper dialogs (``show_message`` /
    ``await confirm(...)``) land on it later.
    """
