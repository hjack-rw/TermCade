"""The journal — the run's record of what it said. Pure core: no app, no screen, no TTY."""

from __future__ import annotations

from termcade.core.journal import Journal


def test_a_line_is_kept_with_what_it_was_about():
    journal = Journal()
    journal.add("They banked the Sphere.", title="Opponent's move")

    entry = journal.entries[0]
    assert (entry.title, entry.message) == ("Opponent's move", "They banked the Sphere.")


def test_an_empty_message_is_not_worth_a_line():
    journal = Journal()
    journal.add("   ")

    assert len(journal) == 0


def test_a_line_is_stamped_with_the_turn_it_happened_in():
    journal = Journal()
    journal.add("You drew a Wu.")
    journal.next_turn()
    journal.add("You banked it.")

    assert [(entry.turn, entry.message) for entry in journal.entries] == [
        (1, "You drew a Wu."),
        (2, "You banked it."),
    ]


def test_a_new_run_counts_from_turn_one_again():
    journal = Journal()
    journal.next_turn()
    journal.next_turn()

    journal.clear()
    journal.add("A fresh run.")

    assert journal.entries[0].turn == 1


def test_the_oldest_lines_fall_off_the_end():
    """Capped — and the cap drops the OLD ones. A log that forgot the newest would be worthless."""
    journal = Journal()
    for index in range(Journal.LIMIT + 5):
        journal.add(f"line {index}")

    assert len(journal) == Journal.LIMIT
    assert journal.entries[0].message == "line 5"
    assert journal.entries[-1].message == f"line {Journal.LIMIT + 4}"
