"""The two revealing Wu: Falcon's Eye reads the opponent's deck, Eagle Scope reads the pile.

Both are spent from the vault and tell you something the board does not. Everything worth pinning
about them is a rule about *what you are shown* and *when you are allowed to look* — a Wu that
reveals nothing is a Wu the player paid for with a Wu, so the gate is the feature.
"""

from __future__ import annotations

import pytest

from termcade.core.rng import Rng

from xiaolin_showdown.logic.actions import coming_wu, usable_powers, use_power
from xiaolin_showdown.logic.duel import Duel, DuelChoices
from xiaolin_showdown.logic.mechanics.powers import SCOPE_DEPTH
from xiaolin_showdown.logic.mechanics.cards import is_one_of
from xiaolin_showdown.logic.settings import XiaolinSettings

FALCONS_EYE = 25
EAGLE_SCOPE = 26
MIND_READER_CONCH = 27
GLOVE_OF_JISAKU = 30
RUBY_OF_RAMSES = 31

DEPOSIT_LIMIT = 1


@pytest.fixture
def held(state, card):
    """Put a Wu in the player's hand and hand it back."""

    def _held(card_id: int):
        wu = card(card_id)
        state.player.hand.append(wu)
        return wu

    return _held


def test_the_scope_names_the_next_wu_in_the_pile(state, held):
    scope = held(EAGLE_SCOPE)
    coming = state.card_deck[:SCOPE_DEPTH]

    message = use_power(state, scope)

    for wu in coming:
        assert wu.name in message


def test_the_scope_sees_exactly_three_deep(state, held):
    scope = held(EAGLE_SCOPE)
    fourth = state.card_deck[SCOPE_DEPTH]

    message = use_power(state, scope)

    assert fourth.name not in message, "the scope showed a Wu it should not reach"


def test_the_scope_does_not_draw_the_wu_it_shows(state, held):
    """It is a look, not a draw: the pile keeps its order and its cards."""
    scope = held(EAGLE_SCOPE)
    before = [wu.id for wu in state.card_deck]

    use_power(state, scope)

    assert [wu.id for wu in state.card_deck] == before


def test_the_eye_reads_the_whole_opponent_deck(state, held, card):
    eye = held(FALCONS_EYE)
    state.bot.deck = [card(6), card(7)]

    message = use_power(state, eye)

    assert "Fist of Tebigong" in message
    assert "Helmet of Jong" in message


def test_the_eye_is_not_offered_against_an_empty_deck(state, held):
    """The opponent's deck is empty most turns. A Wu spent to be told 'nothing' is a trap, not a
    choice — so the vault never offers the look in the first place."""
    eye = held(FALCONS_EYE)
    state.bot.deck = []

    assert not is_one_of(eye, usable_powers(state, DEPOSIT_LIMIT))


def test_the_eye_is_offered_once_the_opponent_holds_a_deck(state, held, card):
    eye = held(FALCONS_EYE)
    state.bot.deck = [card(6)]

    assert is_one_of(eye, usable_powers(state, DEPOSIT_LIMIT))


def test_the_scope_is_not_offered_against_a_drained_pile(state, held):
    scope = held(EAGLE_SCOPE)
    state.card_deck = []

    assert not is_one_of(scope, usable_powers(state, DEPOSIT_LIMIT))


# --- the Mind Reader Conch: a look, and then an answer ----------------------------


def _priority_of(state) -> bool | None:
    """Who holds priority in the showdown these hands would open."""
    choices = DuelChoices(*[None] * 7)  # never advanced; only the opening read is under test
    return Duel(state, Rng(1), choices, XiaolinSettings()).duel.player_priority


def test_the_conch_shows_the_one_wu_that_comes_next(state, held):
    """It hears one thought, not three — the Scope is the Wu that reaches further."""
    conch = held(MIND_READER_CONCH)
    next_up = state.card_deck[0]

    assert [wu.id for wu in coming_wu(state)] == [next_up.id]

    use_power(state, conch, priority=True)


def test_taking_initiative_beats_a_losing_sum(state, held):
    """The point of the Wu: the hands say you lose the read, and you take it anyway."""
    conch = held(MIND_READER_CONCH)
    # Both hands set outright: initiative is read off them, so a Wu the seed happened to deal could
    # otherwise tie the sums and hand priority to a coin toss instead of to the bot.
    state.player.hand = [conch]
    state.bot.hand = [state.catalog.card(9)]  # Longhorn Taurus, +1 — the bot out-reads the player

    assert _priority_of(state) is False  # without the Conch, theirs

    use_power(state, conch, priority=True)

    assert _priority_of(state) is True


def test_refusing_initiative_gives_it_away(state, held):
    """It cuts both ways, and that is the choice: sometimes you want them to commit first."""
    conch = held(MIND_READER_CONCH)

    use_power(state, conch, priority=False)

    assert _priority_of(state) is False


def test_the_conch_overrules_a_tie_without_a_coin(state, held):
    """A tie is settled by a coin toss. An answered Conch means there is nothing left to toss for."""
    conch = held(MIND_READER_CONCH)
    state.player.hand, state.bot.hand = [], []  # nobody holds an initiative Wu: 0 against 0

    use_power(state, conch, priority=True)

    assert _priority_of(state) is True


def test_the_conch_cannot_be_spent_without_an_answer(state, held):
    """A Wu that quietly does nothing is the bug this game keeps a whole test file about."""
    conch = held(MIND_READER_CONCH)

    with pytest.raises(ValueError, match="without an answer"):
        use_power(state, conch)


def test_a_look_is_paid_for_with_the_wu(state, held):
    """Spent, not banked: the Wu leaves the hand and pays no points."""
    scope = held(EAGLE_SCOPE)
    points = state.player.points

    use_power(state, scope)

    assert not is_one_of(scope, state.player.whole_hand)
    assert state.player.points == points


# --- the Glove pulls a Wu to you; the Ruby shoves one away -------------------------


def test_the_glove_pulls_the_wu_you_named_out_of_your_deck(state, held, card):
    glove = held(GLOVE_OF_JISAKU)
    wanted, other = card(6), card(7)
    state.player.deck = [other, wanted]

    use_power(state, glove, target=wanted)

    assert is_one_of(wanted, state.player.hand)
    assert not is_one_of(wanted, state.player.deck)
    assert is_one_of(other, state.player.deck), "it pulled a Wu nobody asked for"


def test_the_glove_leaves_the_hand_no_bigger_than_it_found_it(state, held, card):
    """The Glove goes as the Wu arrives, so the hand limit is never a question."""
    glove = held(GLOVE_OF_JISAKU)
    state.player.deck = [card(6)]
    before = len(state.player.hand)

    use_power(state, glove, target=state.player.deck[0])

    assert len(state.player.hand) == before


def test_the_glove_is_not_offered_against_an_empty_deck(state, held):
    glove = held(GLOVE_OF_JISAKU)
    state.player.deck = []

    assert not is_one_of(glove, usable_powers(state, DEPOSIT_LIMIT))


def test_the_ruby_banks_the_wu_you_named_from_their_hand(state, held, card):
    ruby = held(RUBY_OF_RAMSES)
    victim = card(6)  # Fist of Tebigong, 2 points
    state.bot.hand = [victim, card(7)]
    before = state.bot.points

    use_power(state, ruby, target=victim, rng=Rng(1))

    assert not is_one_of(victim, state.bot.hand)
    assert state.bot.points == before + victim.points, "they were not paid for the Wu"


def test_the_ruby_never_empties_their_hand(state, held, card):
    """A deposit may never leave a duelist with nothing to field — theirs no more than yours."""
    ruby = held(RUBY_OF_RAMSES)
    state.bot.hand = [card(6)]

    assert not is_one_of(ruby, usable_powers(state, DEPOSIT_LIMIT))


def test_the_ruby_hands_you_nothing_but_the_shove(state, held, card):
    """You do not take the Wu, and you do not take its points. You only push it away."""
    ruby = held(RUBY_OF_RAMSES)
    victim = card(6)
    state.bot.hand = [victim, card(7)]
    mine = state.player.points

    use_power(state, ruby, target=victim, rng=Rng(1))

    assert state.player.points == mine
    assert not is_one_of(victim, state.player.whole_hand)
