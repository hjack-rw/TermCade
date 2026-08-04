"""Jack Spicer's own flavour pools — the names his bots wear.

Kept apart from :mod:`summons` (whose pools are keyed off the *character* holding a Wu) because
these are keyed off nothing but Jack himself, chosen fresh each time he uses the power, not derived
from the arena or the duelist facing him.
"""

from __future__ import annotations

from termcade.core.rng import Rng

from ..flow.battle import Side
from ..mechanics.powers import mechanic_of
from ..schema.models import Card, Mechanic

# Jack-Bot's curse flavour (see :func:`choose_jack_bot`): singular, joke-shaped constructs, unlike
# the Attack! pool's swarms and heavy-hitters — the owner's own split, not a balance one.
JACK_BOT_NAMES = ("Jack-Bot", "Tickle-Bot", "Yes-Bot", "Chef-Bot", "Soda-Bot")

# The two identity swaps (see :func:`choose_jack_mode`). Fixed names, not a rotating pool like
# Jack-Bot's — each is a specific gadget with its own effect, not interchangeable flavour.
AI_JACK_NAME = "AI Jack"
CHAMELON_NAME = "Chamelon-Bot"
# Chamelon-Bot's denial is a boost now, not a base override — a synthetic Card built fresh each cycle
# (see `duel.Duel._chamelon_boost_card`), never a real catalog row. Reserved, negative, and distinct
# from every real power id and from Jack-Bot's own -8, so it can never collide with one.
CHAMELON_BOOST_ID = -9

# Jack-bots Attack! swaps to a name from THIS pool, chosen fresh each time, never twice in a row —
# the same shape as JACK_BOT_NAMES, but its own pool: an army of bots, not one construct, and a
# heylin-bot per shipped boss rather than jokes.
ATTACK_NAME = "Jack-bots Attack!"
# Flat, before the metal swing (see `duel.Duel._jack_base`) — the same shape as Jong's JONG_STAT.
ATTACK_STAT = 3
ATTACK_BOT_NAMES = (
    "Blade-Bots", "Gun-Bots", "Hound-Bots", "Giant Jack-Bot", "Wuya-Bot", "Chase-Bot", "Hannibal-Bot",
    "Winged-Bots", "Regenerating Jack-Bots", "Cheerleader-Bots", "Junk-Bots", "U-Bots", "Guard-Bots",
)

# A Yin/Yang Yo-Yo away (see `Player.yoyo_flipped`, `duel.Duel._jack_base`), not a bot swap: he still
# fights as himself. Force/agility are GOOD_JACK_STAT plus whatever training delta Evil Jack has
# already banked on them (fully trained, that reads 5/6) — JACK_PRINTED_PHYSICAL (3) is Evil Jack's
# own printed force/agility, the baseline that delta is measured against. Intellect is his own,
# separately trained value (`Player.good_jack_intellect`) — "stupider by design," never derived from
# Evil's frozen real 7. Can't deploy any bot form while worn (see `duel.Duel._choose_jack_mode`).
GOOD_JACK_NAME = "Good Jack"
GOOD_JACK_STAT = 4
JACK_PRINTED_PHYSICAL = 3

# Denshi Bunny, Sands of Time, Shard of Lightning, either Yo-Yo half, and the combined Yo-Yo — built
# specifically because they answer him well (see docs/design/BOSSES.md's "Counters" section), even
# though most of them are ordinary pool Wu any duelist can hold and play against anyone. Jack is meant
# to be wary of them (see `bot.steal_target`'s ``prefer`` and `turn._priority_deposit`) — the same
# wariness every boss with a keyed set gets, via `turn.counters_against`.
counter = frozenset(
    {Mechanic.HACK, Mechanic.STEAL, Mechanic.CONDUCT, Mechanic.STAT_SWAP, Mechanic.CHI_SWAP}
)


def is_counter(card: Card) -> bool:
    """Whether ``card`` is one of Jack's keyed counters."""
    return mechanic_of(card.power) in counter


def choose_jack_bot(opponent: Side) -> bool:
    """Jack's per-boost call: deploy Jack-Bot to curse the opponent (``True``), or hold it back for
    a normal Wu self-buff instead (``False``) — Jack-Bot itself never buffs, only curses.

    v1, swept later like every other boss knob: deploy it unless the opponent already can't be
    cursed this battle (a Reversing Mirror is up), where a self-buff never can be blocked. Excluded
    from the generic ``bot.choose_boost`` comparison (see there) because that machinery only knows
    how to weigh a boost against the caster's *own* reach — never one that lands on the opponent
    instead.
    """
    return not opponent.defence_negated


ATTACK_MIN_CHANCE = 5  # a floor: it never fully vanishes, only fades — still "unpredictable by design"
ATTACK_MAX_CHANCE = 90  # a ceiling: even desperate, there is always some chance he stays himself

# Attack! always transfers the full prize outright, no partial-credit ladder (`PrizeRoute.BRAWL_WON`)
# — so its VALUE isn't its own per-showdown win rate in isolation, it's that rate against what it
# replaces. Once Chamelon-Bot was redesigned (below) to actually hold its own when the player leads
# (~30% Jack win, up from the old ~15-19%), Attack! stopped being an improvement over either
# alternative and became a pure drag: more full-prize losses with no offsetting upside. Swept 0-70
# (n=300 each) post-redesign — the aggregate got monotonically WORSE as Attack!'s share grew in
# EITHER branch. So both are now near-floor: rare enough to keep him "unpredictable by design"
# without being the number that decides the run — see BOSSES.md.
ATTACK_CHANCE_WHEN_LEADING = 2  # percent — Jack leads, "himself"/AI Jack are already strong

ATTACK_CHANCE_WHEN_TRAILING = 5  # percent at momentum 0 — Chamelon-Bot now covers this spot instead
# `jack_attack_momentum` (XiaolinState) still shifts this with the run's recent record — losing a
# showdown reaches for Attack! harder, winning one leaves it alone — clamped to +-ATTACK_MOMENTUM_CAP,
# a fresh run starting at 0. Kept even though the redesign made Attack! a minor lever: momentum being
# net-neutral-to-positive here is not a reason to strip a mechanic that costs nothing to keep.
ATTACK_MOMENTUM_STEP = 10  # percentage points shifted per showdown won/lost, applied only here
ATTACK_MOMENTUM_CAP = 30  # how far a streak can push the trailing chance off its base, either way

# A losing showdown fighting as HIMSELF (never a stand-in, never Attack! — those already have their
# own economics) costs him twice: his own wager and, at `prize_threshold`'s usual rate, the prize
# too. Fleeing trades a coward's escape for both: no route can claim the prize (it goes to lost,
# never to the winner — strictly better than the ~61% of losses that hand it over outright today),
# and his wager stays his. No downside on any single use, so it is capped instead of tuned — a scarce
# resource he burns on his worst run of showdowns, not a standing "never actually lose" rule.
JACK_FLEE_CAP = 3  # per run — v1, swept later like every other boss knob


def choose_to_flee(flees_used: int) -> bool:
    """Whether Jack concedes a showdown he has already lost, rather than pay the normal cost."""
    return flees_used < JACK_FLEE_CAP


# Chamelon-Bot used to be gated by a margin on the SUM of all three stats ("only mirror when it
# looks worth it") — swept 0/1/2/3/4 (n=300 each) and it lost to fighting as himself at EVERY value,
# because a full mirror traded his real intellect edge on the two UNCONTESTED stats for a coin-flip
# on the one that mattered, and the sum told it nothing about the single stat actually in play.
# Redesigned twice: first to raise his OWN contested stat to the opponent's and no further (never
# touching the other two), which needed no margin since there was no longer a downside to deny — then
# again to make that denial a BOOST (see `duel.Duel._chamelon_boost_card`), competing with a real Wu
# for the one boost his fielded Wu gets — fed straight into `bot.choose_boost`'s own reach-comparison
# alongside Shimo Staff, the Heart, or anything else in hand, rather than preferred by default (it
# targets his OWN side, unlike Jack-Bot's curse, so the same machinery can weigh it fairly). Still
# fires unconditionally whenever the player leads — what changed is whether he SPENDS it that cycle.
def attack_chance(player_has_priority: bool, momentum: int) -> int:
    """Attack!'s own percentage this showdown. Jack leading is always low, whatever his form —
    Attack! only hurts him there. Player leading is his base rate plus momentum (his recent
    showdown record this run), clamped to the floor and ceiling."""
    if not player_has_priority:
        return ATTACK_CHANCE_WHEN_LEADING
    return max(ATTACK_MIN_CHANCE, min(ATTACK_MAX_CHANCE, ATTACK_CHANCE_WHEN_TRAILING + momentum))


def choose_jack_mode(
    player_has_priority: bool,
    can_swap: bool,
    momentum: int,
    rng: Rng,
) -> str | None:
    """Jack's identity swap, decided once at commitment: Attack!, a stand-in, or himself.

    v1, swept later like every other boss knob. Attack! rolls first, a priority-aware percentage
    (:func:`attack_chance`) — high when it would replace Jack's weakest spot (fighting as himself
    while the player leads), and higher still there the more he has been losing this run
    (``momentum``); low when it would replace his strongest (himself/AI Jack while he leads),
    regardless of momentum. It neither reads nor writes ``can_swap``, so it never disrupts the
    pattern underneath it.

    Missing that roll, priority decides which stand-in is even on the table — the two never compete:
    Chamelon-Bot when the player is about to name the challenge (unconditional — see the redesign
    note above); AI Jack when HE leads instead (he already picks intellect there, so a steal is pure
    upside), gated by ``can_swap`` alone — the "cannot spam a stand-in" rule is his, not
    Chamelon-Bot's.
    """
    if rng.randint(1, 100) <= attack_chance(player_has_priority, momentum):
        return ATTACK_NAME
    if player_has_priority:
        return CHAMELON_NAME
    return AI_JACK_NAME if can_swap else None
