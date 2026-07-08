"""The TermCade house theme — a stark black arcade-cabinet palette.

Pure-black background, near-white text, bright accents: the terminal look the games were born in.
Games inherit it, and can register their own :class:`~textual.theme.Theme` to reskin the cabinet.
Card element colours stay bright-ANSI (set in each game's format helpers), readable on the black.
"""

from __future__ import annotations

from textual.theme import Theme

TERMCADE_THEME = Theme(
    name="termcade",
    primary="#eaeaea",  # headings / primary buttons — bright, like the reference's bold white
    secondary="#8a929c",
    accent="#392989",  # an arcade purple for highlights
    foreground="#e6e6e6",
    background="#000000",  # pure black, the arcade-terminal look
    surface="#000000",
    panel="#0c0c0c",
    success="#5dd15d",
    warning="#f2c14e",
    error="#ff5f5f",
    boost="#141414",
    dark=True,
)
