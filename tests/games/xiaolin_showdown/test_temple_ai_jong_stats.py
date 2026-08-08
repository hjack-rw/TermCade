"""Temple AI's initiative reads (`_wants_initiative`/`_initiative_is_wrong`) must see a jong-formed
duelist's flat 6/6/6 construct stat, not the real character stats underneath the costume — every
other in-duel stat read routes through `jong.battle_stats` for exactly this reason.
"""

from __future__ import annotations

from xiaolin_showdown.logic.characters import jong
from xiaolin_showdown.logic.flow import temple_ai


def test_wants_initiative_reads_the_bots_own_construct_stat_in_jong_form(state):
    """The bot's own real stats are weak, but it fights as the flat construct — the edge must be
    computed off that, not off the character underneath."""
    state.bot.hand = []
    state.player.hand = []
    state.bot.character.stats = dict.fromkeys(state.bot.character.stats, 0)
    state.player.character.stats = dict.fromkeys(state.player.character.stats, jong.JONG_STAT - 1)
    state.bot.jong_form = True

    assert temple_ai._wants_initiative(state, is_player=False) is True


def test_wants_initiative_reads_the_opponents_construct_stat_in_jong_form(state):
    """Symmetric case: the OPPONENT is jong-formed. Its real stats read weak, but the construct fights
    at a flat 6/6/6 — the bot must not read a stale, pre-transformation number for the other side."""
    state.bot.hand = []
    state.player.hand = []
    state.bot.character.stats = dict.fromkeys(state.bot.character.stats, jong.JONG_STAT - 1)
    state.player.character.stats = dict.fromkeys(state.player.character.stats, 0)
    state.player.jong_form = True

    # Naively read, the bot's raw stat would already beat the player's raw stat and want the
    # initiative. Read correctly, the player fights at the construct's flat stat instead, which ties
    # the bot's own — no edge, nothing worth buying.
    assert temple_ai._wants_initiative(state, is_player=False) is False
