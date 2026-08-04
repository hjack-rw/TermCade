"""Jack-Bot — the permanent boost-slot curse. Always -1/-1/-1 on the opponent, never a self-buff."""

from __future__ import annotations

from termcade.core.rng import Rng

from factories import auto_choices, ground, wu

from xiaolin_showdown.logic.flow.battle import Round, Side
from xiaolin_showdown.logic.characters.jack import choose_jack_bot
from xiaolin_showdown.logic.flow.bot import choose_boost
from xiaolin_showdown.logic.schema.catalog import load_catalog
from xiaolin_showdown.logic.flow.duel import Duel
from xiaolin_showdown.logic.mechanics.powers import Mechanic, mechanic_of
from xiaolin_showdown.logic.mechanics.resolve import _booster_at_head, curse_from_boost
from xiaolin_showdown.logic.flow.setup import new_game
from xiaolin_showdown.screens.display.duel_board import _cards_line

JACK_BOT = wu(-1, -1, -1, mechanic=Mechanic.BOT, element="metal", type="wudai", name="Jack-Bot")


def _jack_duel() -> Duel:
    cat = load_catalog()
    jack_char = next(c for c in cat.characters if c.name == "Jack_Spicer")
    state = new_game(cat, Rng(1), cat.character(1), opponent=jack_char)
    duel = Duel(state, Rng(1), auto_choices())
    duel.duel.rounds.append(Round(stat="force"))
    duel.duel.background = "metal"
    return duel


def _jack_bot_card(duel: Duel):
    return next(c for c in duel.state.bot.inalienable_hand if mechanic_of(c.power) is Mechanic.BOT)


def test_choose_jack_bot_curses_when_the_opponent_can_be_hurt():
    assert choose_jack_bot(Side()) is True


def test_choose_jack_bot_holds_back_when_the_opponent_is_shielded():
    shielded = Side()
    shielded.defence_negated = True
    assert choose_jack_bot(shielded) is False


def test_choose_boost_never_offers_jack_bot():
    # The generic reach-comparison only knows how to weigh the caster's own side, and Jack-Bot's
    # whole effect lands on the opponent's — offering it here would misvalue it. See `bot.choose_boost`.
    result = choose_boost(Round(stat="force"), ground(), [JACK_BOT], [])
    assert result is None


def test_choose_boost_still_offers_a_normal_wu_alongside_jack_bot():
    normal = wu(1, 1, 1, name="Dragon", mechanic=Mechanic.DRAGON)
    field_wu = wu(0, name="Field")
    result = choose_boost(Round(stat="force"), ground(), [JACK_BOT, normal], [field_wu])
    assert result is normal  # Jack-Bot is filtered out; the real option still wins on its own merit


def test_committing_jack_bot_curses_the_opponent():
    duel = _jack_duel()
    duel._commit_boost(_jack_bot_card(duel), is_player=False, element="metal")
    victim = duel.duel.round.player
    assert victim.suffered, "the curse mirror landed on the opponent"
    assert victim.suffered[-1].stats == {"force": -1, "agility": -1, "intellect": -1}


def test_jack_bot_costs_him_nothing():
    duel = _jack_duel()
    duel._commit_boost(_jack_bot_card(duel), is_player=False, element="metal")
    his_own = duel.duel.round.bot
    assert all(v == 0 for card in his_own.queue for v in card.stats.values())
    assert his_own.spent and all(v == 0 for v in his_own.spent[-1].stats.values())


def test_jack_bots_curse_does_not_bury_a_live_boost():
    # `_booster_at_head` reads the queue's tail for the victim's OWN live boost, waiting on the card
    # they are about to field. A plain append would bury it under the curse mirror and silently
    # swallow it — `curse_from_boost` must insert ahead of it instead.
    victim = Side()
    live_boost = wu(0, name="Amplifier", mechanic=Mechanic.BOOST)
    victim.queue.append(live_boost)
    curse_from_boost(victim, wu(-1, -1, -1, name="Jack-Bot"))
    assert _booster_at_head(victim.queue) is live_boost


def test_jack_bots_flavour_name_never_repeats():
    from xiaolin_showdown.logic.characters import jack

    for excluded in jack.JACK_BOT_NAMES:
        duel = _jack_duel()
        duel.state.last_jack_bot_name = excluded
        duel._pick_jack_bot_name()
        assert duel.duel.jack_bot_name != excluded
        assert duel.state.last_jack_bot_name != excluded


def test_jack_bots_curse_joins_the_board_with_ampersand_not_plus():
    mirror = wu(-1, -1, -1, name="Tickle-Bot", element="metal")
    other = wu(-2, name="Sting", element="metal")
    line = _cards_line("Defensive", [mirror, other], [], None, "metal", jack_bot=[mirror])
    plain = line.renderables[0].plain
    assert " & " in plain
    assert " + " not in plain
