"""The new Mind Reader Conch (Prognosis): the opponent leads and names the challenge, but the caster
reads it in advance and keeps the challenger's ground. And Caleido-scope Glasses inherits Telepatheia.
"""

from __future__ import annotations

from termcade.core.rng import Rng

from xiaolin_showdown.logic.config.settings import XiaolinSettings
from xiaolin_showdown.logic.flow.actions import use_power
from xiaolin_showdown.logic.schema.catalog import load_catalog
from xiaolin_showdown.logic.schema.constants import TOURNAMENT, TOURNAMENT_BATTLES
from xiaolin_showdown.logic.mechanics.powers import mechanic_of
from xiaolin_showdown.logic.schema.models import Mechanic, Power
from xiaolin_showdown.logic.schema.state import XiaolinState

from factories import duelist, wu

PROGNOSIS = Power(51, "Telepatheia", Mechanic.PROGNOSIS, "", 0)
DEFAULT = XiaolinSettings()


def _state(player, bot) -> XiaolinState:
    return XiaolinState(catalog=None, player=player, bot=bot, card_deck=[])  # type: ignore[arg-type]


def test_the_conch_pins_the_bots_challenge_and_hands_it_the_lead():
    conch = wu(0, 0, 4, mechanic=Mechanic.PROGNOSIS, name="Conch")
    # The bot is strongest in intellect, so that is the challenge it is pinned to.
    state = _state(duelist(hand=[conch]), duelist(stats={"force": 1, "agility": 1, "intellect": 5}))
    use_power(state, conch, DEFAULT, is_player=True, rng=Rng(0))
    assert state.forced_priority is False  # the opponent leads
    assert state.locked_challenge == "intellect"  # their strongest, read and set in stone
    assert state.conch_tiebreak is True  # the caster keeps the ground


def test_the_caster_keeps_the_ground_though_the_opponent_leads():
    from xiaolin_showdown.logic.flow.duel import Duel
    from xiaolin_showdown.logic.config.settings import XiaolinSettings

    # conch_tiebreak overrides priority for the level-battle tiebreak: opponent leads, caster wins ties.
    state = _state(duelist(), duelist())
    state.conch_tiebreak = True
    state.forced_priority = False
    duel = Duel(state, Rng(0), _choices(), XiaolinSettings())  # _new_round reads forced_priority
    assert duel.duel.player_priority is False  # the opponent leads
    assert duel._ground().challenger_is_player is True  # but the caster keeps the ground


def _choices():
    from xiaolin_showdown.logic.flow.duel import DuelChoices

    async def _stub(*_a):
        return None

    return DuelChoices(
        challenge=_stub, background=_stub, wager=_stub, boost=_stub, card=_stub, element=_stub, stat=_stub
    )


def test_the_pin_and_ground_are_spent_when_the_showdown_ends():
    # After a showdown the Conch's promise is gone — the next duel is ordinary again.
    conch = wu(0, 0, 4, mechanic=Mechanic.PROGNOSIS, name="Conch")
    state = _state(duelist(hand=[conch, wu(1)]), duelist(stats={"force": 2, "agility": 2, "intellect": 2}))
    use_power(state, conch, DEFAULT, is_player=True, rng=Rng(0))
    assert state.locked_challenge is not None
    # Simulate the end-of-showdown reset (duel._end clears them).
    state.forced_priority = state.locked_challenge = state.conch_tiebreak = None
    assert state.locked_challenge is None


def test_prognosis_does_not_repin_a_stat_already_named_this_duel():
    """The pin obeys the same no-repeat rule as a live challenge call: the bot's strongest stat is
    off the table once it's already been named, so Prognosis must fall to the next-best legal one."""
    conch = wu(0, 0, 4, mechanic=Mechanic.PROGNOSIS, name="Conch")
    state = _state(duelist(hand=[conch]), duelist(stats={"force": 1, "agility": 1, "intellect": 5}))
    state.previous_challenge = ["intellect"]  # the bot's strongest stat — already named this duel
    use_power(state, conch, DEFAULT, is_player=True, rng=Rng(0))
    assert state.locked_challenge != "intellect"
    assert state.locked_challenge == "force"  # next-best of what's left, tie broken toward force


def test_prognosis_can_pin_a_tournament_when_the_bot_leads_broadly():
    """Prognosis's pin must offer the tournament too, exactly when a live challenge call would —
    both hands need three-plus Wu, and the bot must lead on a majority of the stats."""
    conch = wu(0, 0, 4, mechanic=Mechanic.PROGNOSIS, name="Conch")
    filler = [wu(name=f"Filler {i}") for i in range(TOURNAMENT_BATTLES)]
    bot = duelist(hand=filler, stats={"force": 5, "agility": 5, "intellect": 0})
    player = duelist(hand=[conch, *filler])
    state = _state(player, bot)
    use_power(state, conch, DEFAULT, is_player=True, rng=Rng(0))
    assert state.locked_challenge == TOURNAMENT


def test_stacking_two_initiative_powers_contests_the_showdown():
    """A second initiative power (Glasses, then the Conch) landing on an already-answered showdown
    contests it instead of overwriting the first answer: neither pin stands, the coin decides."""
    glasses = wu(0, 0, 3, mechanic=Mechanic.ENHANCED_VISION, name="Glasses")
    conch = wu(0, 0, 4, mechanic=Mechanic.PROGNOSIS, name="Conch")
    state = _state(
        duelist(hand=[glasses, conch]), duelist(stats={"force": 1, "agility": 1, "intellect": 5})
    )

    use_power(state, glasses, DEFAULT, is_player=True, priority=True, rng=Rng(0))
    assert state.forced_priority is True  # the first power's answer stands...

    report = use_power(state, conch, DEFAULT, is_player=True, rng=Rng(0))

    assert state.initiative_contested is True  # ...until a second one lands on the same showdown
    assert state.forced_priority is None
    assert state.locked_challenge is None
    assert state.conch_tiebreak is None
    assert report.toast == "You both reached for the initiative — a coin toss will decide who leads."


def test_caleido_scope_carries_telepatheia_now():
    cat = load_catalog()
    caleido = next(c for c in cat.cards if mechanic_of(c.power) is Mechanic.ENHANCED_VISION)
    conch = next(c for c in cat.cards if mechanic_of(c.power) is Mechanic.PROGNOSIS)
    assert mechanic_of(caleido.power) is Mechanic.ENHANCED_VISION
    assert mechanic_of(conch.power) is Mechanic.PROGNOSIS  # the Conch traded up


def test_a_prognosis_save_round_trips(state):
    state.locked_challenge = "force"
    state.conch_tiebreak = True
    restored = XiaolinState.restore(state.snapshot(), None)
    assert restored.locked_challenge == "force" and restored.conch_tiebreak is True
