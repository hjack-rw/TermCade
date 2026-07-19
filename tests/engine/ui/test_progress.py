"""The progress-bar render — half-block segments, percent. Pure string, no TTY."""

from __future__ import annotations

from termcade.ui.widgets import render_bar


def test_the_bar_fills_the_fraction():
    assert render_bar(0.7, width=10) == "▰ ▰ ▰ ▰ ▰ ▰ ▰ ▱ ▱ ▱  70%"


def test_the_bar_is_all_track_when_empty():
    assert render_bar(0.0, width=10) == "▱ ▱ ▱ ▱ ▱ ▱ ▱ ▱ ▱ ▱  0%"


def test_the_bar_is_all_filled_when_full():
    assert render_bar(1.0, width=10) == "▰ ▰ ▰ ▰ ▰ ▰ ▰ ▰ ▰ ▰  100%"


def test_out_of_range_fractions_clamp():
    assert render_bar(-0.5) == render_bar(0.0)
    assert render_bar(1.5) == render_bar(1.0)
