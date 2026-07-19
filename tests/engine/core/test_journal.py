"""The journal — the run's record of what it said. Pure core: no app, no screen, no TTY."""

from __future__ import annotations

from rich.text import Text

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


def test_a_snapshot_restores_the_lines_and_their_turns():
    journal = Journal()
    journal.add("You drew a Wu.", title="Your move")
    journal.next_turn()
    journal.add("They banked the Sphere.", title="Opponent's move")

    restored = Journal()
    restored.restore(journal.snapshot())

    assert [(e.turn, e.title, e.message) for e in restored.entries] == [
        (1, "Your move", "You drew a Wu."),
        (2, "Opponent's move", "They banked the Sphere."),
    ]


def test_a_restored_run_stacks_new_lines_where_it_left_off():
    """The turn count survives the save — a loaded run does not restart at Turn 1."""
    journal = Journal()
    journal.next_turn()
    journal.next_turn()
    journal.add("Turn three happened.")

    restored = Journal()
    restored.restore(journal.snapshot())
    restored.add("And this is still turn three.")

    assert restored.entries[-1].turn == 3


def test_a_rich_line_is_stored_as_its_plain_words():
    """Only what a load cannot rebuild is kept: the words, not the colour. The Game Log re-paints."""
    journal = Journal()
    journal.add(Text("The arena was summoned as Water.", style="blue"))

    stored = journal.snapshot()["entries"][0]["message"]

    assert stored == "The arena was summoned as Water."
    assert isinstance(stored, str)


def test_restoring_replaces_whatever_was_there():
    """A loaded run's log is that run's — not the leftovers of the menu it loaded from."""
    journal = Journal()
    journal.add("A menu leftover.")

    journal.restore({"turn": 1, "entries": [{"turn": 1, "title": "", "message": "The real run."}]})

    assert [e.message for e in journal.entries] == ["The real run."]


def test_a_save_without_a_journal_restores_to_empty():
    """An older save carries no journal block; restore must treat the absence as an empty log."""
    journal = Journal()
    journal.add("Left over.")

    journal.restore({})

    assert len(journal) == 0
    assert journal.turn == 1
