"""``BoxedPanel`` — a double-bordered container with a centered title.

A real Textual border (``border: double``) with a centered title, themed by tokens so a
game reskins it by overriding CSS variables.
"""

from __future__ import annotations

from textual.containers import Vertical
from textual.widget import Widget


class BoxedPanel(Vertical):
    def __init__(
        self,
        *children: Widget,
        title: str = "",
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
        disabled: bool = False,
    ) -> None:
        super().__init__(*children, name=name, id=id, classes=classes, disabled=disabled)
        self.border_title = title
