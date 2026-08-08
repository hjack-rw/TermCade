"""What a Wu is worth — held, on the table, or banked — and the hand-size/shelving rules that price
share the same currency.

Split out of turn.py: these four are pure primitives with no dependency on the rest of flow/, but
bot.py, actions.py, and temple_ai.py all price a card by them. Importing them straight off turn.py
made every one of those modules import turn.py at module level — while turn.py's own orchestration
needed to call back into all three, so those back-edges could only exist as local, function-body
imports (a circular-import workaround). Moving the primitives here breaks the knot: turn.py keeps
calling into bot/actions/temple_ai, and nothing calls back into turn.py for them.
"""

from __future__ import annotations

from termcade.core.rng import Rng

from ..mechanics.powers import (
    ANIMATE_STAT,
    MORPH_ASIDE,
    MORPH_CONTESTED,
    NAMED_STAT_VALUE,
    Mechanic,
    is_gamble,
    is_uncontrolled,
    mechanic_of,
    roll_gamble,
)
from ..schema.models import Card, Player

# What a booster is worth in a showdown, since it carries no stats of its own.
BOOSTER_PREMIUM = 4

# What a Wu is worth on the table when its printed stats say nothing (a `? ? ?` card reads as ZERO).
# Same currency as a printed stat.
_MECHANIC_VALUE: dict[Mechanic, int] = {
    # Priced off the Morph rule itself, so retuning the rule re-prices the bot.
    Mechanic.MORPH: MORPH_ASIDE * 2 + MORPH_CONTESTED,
    Mechanic.BUFF: NAMED_STAT_VALUE,
    Mechanic.MISFORTUNE: NAMED_STAT_VALUE,
    Mechanic.NULLIFY_STATS: 5,
    Mechanic.NULLIFY_WU: 5,
    Mechanic.NULLIFY_CURSE: 4,
    # Prints 0/0/0; its swing is board-dependent and uncapped (see `duel.Duel._conduct_bonus`), so
    # the bot can't know its true value at decision time. Priced level with NULLIFY_CURSE.
    Mechanic.CONDUCT: 4,
    # `temple_ai._worth_swapping` decides when it's worth spending; priced here for what it's worth
    # banked instead, when that policy passes it up.
    Mechanic.TRANSFER: 5,
    # `temple_ai._worth_refreshing` decides when it's worth spending; priced here for what it's worth
    # banked instead, when that policy passes it up.
    Mechanic.REFRESH: 3,
    # Prints 0/0/0 but FIELDED it wins the showdown outright (see `bot.choose_card`, which always
    # fields it). Spending it deliberately is `temple_ai._worth_wishing`; this price is what it's
    # worth held or banked as junk, not what a chosen Vault pull is worth.
    # (Deposited it is worth its 10 printed points, counted the ordinary way.)
    Mechanic.WISH: 10,
    # Prints ? ? ? but in the boost slot comes alive as a flat ANIMATE_STAT form — priced off that so
    # retuning the form re-prices the bot.
    Mechanic.ANIMATE: ANIMATE_STAT * 3,
    # Prints ? ? ?; the swap outlives the battle (see `duel.Duel._swap_stat_and_flip`) — no spend
    # policy yet, level with TRANSFER.
    Mechanic.STAT_SWAP: 5,
    # Never dealt (see `constants.in_pool`) — only reached by combining both halves — but still needs
    # a price so a bot holding one never banks it as junk. Same swap as STAT_SWAP, priced a step above.
    Mechanic.CHI_SWAP: 6,
}

# (Witchcraft is a CHARACTER power — no card carries it, so its table price is moot; it sits in
# `_STATS_ARE_THE_WHOLE_VALUE` below purely to satisfy the every-mechanic-is-accounted guard.)

# Mechanics whose printed stats are the whole value, declared rather than assumed. The two sets must
# cover every `Mechanic` — `test_every_mechanic_is_priced` enforces it. An unpriced `? ? ?` Wu reads as
# zero: the bot banks the strongest card in the game for 2 points.
#
# Two of them are excused for a *different* reason: they are worth nothing on the table at all, and
# that is deliberate. Kept apart from the rest because "its stats say what it is worth" and "it is
# worth nothing" are different claims, and only the second one may price at zero.
_WORTH_NOTHING_ON_THE_TABLE: frozenset[Mechanic] = frozenset(
    {
        Mechanic.FILLER,  # deck padding: no stats, no power, no business being fielded
        # The joke Wu prints `? ? ?` and does nothing in a battle. Everything it is worth is at the
        # temple, where it is rolled for points — so zero on the table is honest, not an oversight.
        Mechanic.GAMBLE,
    }
)

_STATS_ARE_THE_WHOLE_VALUE: frozenset[Mechanic] = _WORTH_NOTHING_ON_THE_TABLE | frozenset(
    {
        Mechanic.INNATE,  # the stats *are* the Wu
        Mechanic.INITIATIVE,  # its bonus is a hand power; in a battle it is only its stats
        Mechanic.HAND_SIZE,  # likewise — it buys a hand slot, not a blow
        Mechanic.DOUBLE_TRAINING,  # a hand power (doubles training); in a battle it is only its stats
        Mechanic.HAND_FIZZLE,  # unprinted (see `powers.UNPRINTED`)
        Mechanic.DRAW,  # a temple power; on the table it is just its printed stats
        Mechanic.READ_DECK,  # likewise
        Mechanic.SCRY,  # likewise
        Mechanic.ENHANCED_VISION,  # likewise
        Mechanic.FETCH,  # likewise
        Mechanic.BOUNCE,  # likewise
        Mechanic.LUCK,  # likewise — it acts on the lost pile, never in a battle
        Mechanic.PROGNOSIS,  # likewise — a temple power, on the table just its printed stats
        Mechanic.WITCHCRAFT,  # a character power (Wuya's) — no card ever prints it
        Mechanic.BEAST_FORM,  # a character power (Chase's) — likewise
        # The dragon and the booster carry no stats but decide duels — they are priced by
        # BOOSTER_PREMIUM in `duel_value` rather than here, which is the older seam.
        Mechanic.DRAGON,
        Mechanic.BOOST,
        # Jack-Bot is an inalienable boss fixture, never pooled or bought — its -1/-1/-1 lands on the
        # opponent (`resolve.curse_from_boost`), not scored as its own printed stats, so there is
        # nothing here for a points-vs-stats check to weigh in the first place.
        Mechanic.BOT,
        # Worth more than its printed stats (it vetoes the elemental bonus and the prize's elemental
        # route both), but priced by stats alone deliberately — do not raise it.
        Mechanic.NULLIFY_ELEMENT,
        # Worth more than its printed stats (it reverses the elemental bonus), but priced by them —
        # the reversal is contextual, read by the bot's play-it-out eval, not here.
        Mechanic.REVERSE_ELEMENT,
        # The four boss counters print real stats; their showdown effect (negate a boost, recolour a
        # side or the arena) is contextual and read by the bot's play-it-out eval, not priced here.
        Mechanic.NULLIFY_BOOST,
        Mechanic.CLEANSE,
        Mechanic.SET_ELEMENT,
        Mechanic.WARD,
        Mechanic.SET_ARENA,
        # Prints real stats; its shield (no curse on the stat it boosts) is contextual, read by the
        # bot's play-it-out eval, not priced here.
        Mechanic.STAT_SHIELD,
        # Prints real stats; its seize is contextual, read by the bot's play-it-out eval
        # (`bot._worth_the_side_effect`, `_SIDE_EFFECT_MECHANICS`), not priced here.
        Mechanic.SEIZE_GROUND,
        # Prints real stats; its win-vs-construct is entirely contextual — worth nothing outside a
        # Jack fight, and even then only in two of his four states. Read by the bot's play-it-out
        # eval, not priced here.
        Mechanic.HACK,
        # Prints real stats; the steal it buys is read by the bot's play-it-out eval (it already has
        # `bot.steal_target` to weigh the hand it would take), not priced flat here — a steal against
        # an empty hand and deck is worth nothing, and no fixed number captures that.
        Mechanic.STEAL,
        # Prints real stats; its temple undo (Retrokinesis) has nothing to fix — every bot action is
        # already play-it-out-best when taken. Fielded into a duel, its rewrite power is player-only
        # by a hardcoded dispatch check ("the bot never amends", duel.py) — not a missing heuristic.
        Mechanic.AMEND,
        # A summon: on the table it is just its printed stats (the fielded horde/clone). Its extra worth
        # is the temple +training, a use `temple_ai._worth_summoning_to_train` decides — so table value
        # is the stats alone; the training value is weighed separately, at spend time.
        Mechanic.TRAIN_BOOST,
        # Prints real stats; its doubled elemental bonus is contextual (great in tune, awful against),
        # read by the bot's play-it-out eval, not priced here.
        Mechanic.DOUBLE_ELEMENT,
        # Its printed stats are its whole table value — the fat deposit is the points column, which the
        # bot reads straight off when it decides what to bank.
        Mechanic.TREASURE,
    }
)


def duel_value(card: Card) -> int:
    """Roughly what ``card`` is worth held in a showdown.

    Stat magnitude, not signed value: a negative stat is a *weapon* (``powers`` mirrors it onto the
    opponent's queue), so it is as worth keeping as a positive one. A booster carries no stats but
    decides duels, hence the premium.

    A Wu whose stats resolve at play prints none, so the stats cannot answer for it either — its
    mechanic does, through :data:`_MECHANIC_VALUE`. Without that, every card that reads `? ? ?` is
    worth nothing to the opponent, and it will cheerfully bank an Emperor Scorpion for two points.
    """
    # The Sapphire Dragon prints no stats and LOSES the showdown if fielded — its whole worth is the
    # temple level it grants. Priced so the bot holds it over junk rather than banking it away;
    # temple_ai has no policy to actually spend it. (Deposited, it is its printed points.)
    if is_uncontrolled(card.power):
        return 8
    stats = sum(abs(v) for v in card.stats.values() if v is not None)
    mechanic = mechanic_of(card.power)
    premium = BOOSTER_PREMIUM if mechanic is Mechanic.BOOST else 0
    return stats + _MECHANIC_VALUE.get(mechanic, 0) + premium


def bank_value(card: Card, rng: Rng) -> int:
    """What depositing this Wu pays: its printed points, unless it is the gamble, which is rolled.

    Both duelists bank on the same terms and neither is told the gamble's worth — the bot picks it by
    the DB expected value (``GAMBLE_SPREAD``), blind like a player eyeing a ``?``.
    """
    return roll_gamble(rng) if is_gamble(card.power) else card.points


def max_hand_size(player: Player, base: int) -> int:
    """The size limit, plus one while a "Third-Arm Sash" (a HAND_SIZE Wu) is held."""
    sash = any(mechanic_of(c.power) is Mechanic.HAND_SIZE for c in player.whole_hand)
    return base + int(sash)


def shelve(player: Player, card: Card, *, rng: Rng) -> None:
    """Put a Wu on a personal deck — and shuffle it in. The deck is an OBSTACLE, not an ordered stack:
    a shelved Wu must not come back in a known order or on a countable turn, or it could be memorised
    and played around. Load-bearing randomness (it decides a draw), so it draws the main stream."""
    player.deck.append(card)
    rng.shuffle(player.deck)
