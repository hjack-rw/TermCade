"""``spaced_dashes``: the project's own fix for a terminal font eating the space after an em dash —
untested until now, despite being exactly the kind of small pure function a rendering regression
hides in.
"""

from __future__ import annotations

from termcade.ui.typography import DASH_GAP, EM_DASH, spaced_dashes


def test_a_mid_sentence_dash_gets_a_space_before_and_a_double_space_after():
    assert spaced_dashes("power — spent") == f"power {EM_DASH}{DASH_GAP}spent"


def test_every_dash_in_a_multi_dash_line_is_spaced():
    result = spaced_dashes("a — b — c")
    assert result == f"a {EM_DASH}{DASH_GAP}b {EM_DASH}{DASH_GAP}c"


def test_a_line_that_starts_with_a_dash_gets_no_space_in_front_of_it():
    """The docstring's own edge case: nothing to separate the dash from at the start of a line, and a
    leading space there would read as a stray indent."""
    result = spaced_dashes("—like this")
    assert result == f"{EM_DASH}{DASH_GAP}like this"
    assert not result.startswith(" ")


def test_a_line_already_indented_with_a_leading_space_keeps_it():
    result = spaced_dashes(" —like this")
    assert result.startswith(" ")


def test_plain_text_with_no_dash_passes_through_unchanged():
    assert spaced_dashes("no dash here") == "no dash here"
