"""``BoxedPanel`` — a double-bordered container with a centered title.

A real Textual border (``border: double``) with a centered title, themed by tokens so a
game reskins it by overriding CSS variables.
"""

from __future__ import annotations

from textual.containers import Vertical


class BoxedPanel(Vertical):
    def __init__(self, *children, title: str = "", **kwargs) -> None:
        super().__init__(*children, **kwargs)
        self.border_title = title
