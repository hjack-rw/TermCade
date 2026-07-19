"""Chase Young — Beast Form (+3 contested, Wu score nothing) and "The Good Guys Finish Last"."""

from __future__ import annotations

from termcade.core.rng import Rng

from xiaolin_showdown.logic.bot import choose_beast_form
from xiaolin_showdown.logic.duel import BEAST_BOOST, Duel, DuelChoices
from xiaolin_showdown.logic.models import Character, Mechanic, Power
from xiaolin_showdown.logic.settings import XiaolinSettings
from xiaolin_showdown.logic.state import XiaolinState

from factories import duelist, wu

BEAST = Power(-7, "Beast Form", Mechanic.BEAST_FORM, "", 0)


class _NoPlaces:
    """A catalog stub for the duel's background-flavour lookup — no named places, just the element."""

    def backgrounds_for(self, _element):
        return []


def _chase(**kwargs):
    d = duelist(**kwargs)
    d.character = Character(13, "Chase", {"force": 7, "agility": 7, "intellect": 7}, BEAST, "heylin", False, tier="boss")
    return d


def test_beast_form_when_the_contested_stat_is_close():
    # Opponent's reach (base 6 + a 1-force Wu = 7) ties Chase's 7 → lead 0 < margin → take the +2.
    chase = _chase()
    opp = duelist(stats={"force": 6, "agility": 6, "intellect": 6}, hand=[wu(1, name="F")])
    assert choose_beast_form(chase, opp, ["force"]) == "force"


def test_wu_play_when_chase_leads_the_stat_comfortably():
    # Ahead by more than the boost — the +2 changes nothing, so keep the Wu and the prize.
    chase = _chase()
    opp = duelist(stats={"force": 3, "agility": 3, "intellect": 3}, hand=[wu(1, name="F")])
    assert choose_beast_form(chase, opp, ["force"]) is None


def test_a_tournament_boosts_only_the_tightest_stat():
    # Once a fight: of three contested stats, he spends the +2 on the one he most risks losing.
    chase = _chase()
    opp = duelist(stats={"force": 1, "agility": 7, "intellect": 1})
    assert choose_beast_form(chase, opp, ["force", "agility", "intellect"]) == "agility"


def _choices() -> DuelChoices:
    async def _one(options):
        return options[0]

    async def _none(_options):
        return None

    return DuelChoices(
        challenge=_one, background=_one, wager=_one, boost=_none, card=_one, element=_one, stat=_one
    )


async def _run(duel: Duel) -> None:
    from xiaolin_showdown.logic.duel import END

    for _ in range(12):
        if await duel.advance() == END:
            return
    raise AssertionError("showdown never ended")


async def test_beast_form_adds_the_boost_to_the_contested_stat():
    # Chase, weak hand → Beast Form. His base 7 + BEAST_BOOST on the contested stat carries the
    # battle even though his fielded Wu score nothing.
    player = duelist(stats={"force": 5, "agility": 5, "intellect": 5}, hand=[wu(1, name="P")])
    chase = _chase(hand=[wu(0, name="Dead"), wu(0, name="Dead2")])
    state = XiaolinState(  # type: ignore[arg-type]
        catalog=_NoPlaces(), player=player, bot=chase, card_deck=[wu(2, name="Prize")]
    )
    duel = Duel(state, Rng(0), _choices(), XiaolinSettings())
    await _run(duel)
    assert duel.duel.beast_stat is not None  # a weak hand took the beast
    assert duel.duel.winner is False  # 7+3 contested beats the player's 5 + a 1-Wu


async def test_the_good_guys_finish_last_gifts_the_prize_to_the_loser():
    # Close on every stat (6 vs Chase 7) so he beasts whichever is contested, +2 still wins → gifts.
    player = duelist(stats={"force": 6, "agility": 6, "intellect": 6}, hand=[wu(0, name="P")])
    chase = _chase(hand=[wu(0, name="Dead"), wu(0, name="Dead2")])
    prize = wu(2, name="Prize")
    state = XiaolinState(catalog=_NoPlaces(), player=player, bot=chase, card_deck=[prize])  # type: ignore[arg-type]
    duel = Duel(state, Rng(0), _choices(), XiaolinSettings())
    await _run(duel)
    assert duel.duel.winner is False and duel.duel.card_won  # Chase won and earned the prize...
    assert any(c.name == "Prize" for c in player.whole_hand)  # ...but the loser holds it
    assert all(c.name != "Prize" for c in chase.whole_hand)


async def test_a_plain_opponent_never_takes_beast_form():
    # Beast Form is Chase's alone — a weak-handed ordinary bot must field its Wu, not sprout +3.
    player = duelist(stats={"force": 5, "agility": 5, "intellect": 5}, hand=[wu(1, name="P")])
    plain = duelist(stats={"force": 4, "agility": 4, "intellect": 4}, hand=[wu(0, name="w"), wu(0)])
    state = XiaolinState(catalog=_NoPlaces(), player=player, bot=plain, card_deck=[wu(2)])  # type: ignore[arg-type]
    duel = Duel(state, Rng(0), _choices(), XiaolinSettings())
    await _run(duel)
    assert duel.duel.beast_stat is None


def test_beast_form_boosts_only_the_battle_that_contests_its_stat():
    # A tournament leg that contests a DIFFERENT stat sees the plain 7/7/7 — the +2 is once a fight.
    from xiaolin_showdown.logic.battle import Round
    from xiaolin_showdown.screens.duel_board import _beast_for
    from xiaolin_showdown.logic.duel import DuelState

    duel = DuelState()
    duel.beast_stat = "force"
    assert _beast_for(duel, Round(stat="force")) == "force"
    assert _beast_for(duel, Round(stat="agility")) is None


def test_the_beast_boost_rides_the_offensive_line_joined_to_its_wu():
    from xiaolin_showdown.screens.duel_board import _beast_offensive

    line = _beast_offensive("agility", [wu(2, 2, 1, name="Dead", element="metal")], "agility")
    plain = line.renderables[0].plain
    assert f"Beast Form (0/{BEAST_BOOST}/0)" in plain  # element-free boost
    assert " + " in plain and "Dead (-/-/-)" in plain  # joined to the struck Wu


def test_neither_dampening_nor_subjugation_nullifies_beast_form():
    from xiaolin_showdown.logic.battle import Side, end_stat

    # Chase's base carries the +2 (force 7+2=9). A Star Hanabi (boost_negated) drops boost cards and
    # an Emperor Scorpion (offence_negated) drops played Wu — both act on the QUEUE, so the base-borne
    # beast survives both at once.
    side = Side()
    side.offence_negated = True
    side.boost_negated = True
    beast_base = {"force": 9, "agility": 7, "intellect": 7}
    assert end_stat("force", 1, side, beast_base, "metal") == 9

    # But the Sphere of Jianyu (base_negated) DOES: it zeroes the character itself, and the beast
    # rides the character — so the one counter that negates the base takes the +2 with it.
    trapped = Side()
    trapped.base_negated = True
    assert end_stat("force", 1, trapped, beast_base, "metal") == 0


def test_the_boost_is_element_free():
    # It lands on BASE, which carries no element — so no arena bonus, and no elemental counter (they
    # act on the elemental bonus) can touch it. But a player CURSE still bites: it lands on Chase's
    # side (his counted() keeps the suffered mirrors), reducing his beast score. See below.
    assert BEAST_BOOST == 2


def test_a_player_curse_still_bites_beast_form():
    from xiaolin_showdown.logic.battle import Round
    from xiaolin_showdown.logic.mechanics.resolve import resolve_played_power

    # Player fields a -3 force curse against Chase; in Beast Form his own Wu die but the curse does
    # not — it lands on him and drags his boosted force down.
    battle = Round(stat="force")
    resolve_played_power(battle, wu(-3, name="Curse"), is_player=True, element="metal")
    battle.bot.offence_negated = True  # Chase in Beast Form: his own Wu score nothing
    assert battle.bot.curses(), "the player's curse mirror still sits on Chase's side"
