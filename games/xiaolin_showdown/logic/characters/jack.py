"""Jack Spicer's own flavour pools — the names his bots wear.

Kept apart from :mod:`summons` (whose pools are keyed off the *character* holding a Wu) because
these are keyed off nothing but Jack himself, chosen fresh each time he uses the power, not derived
from the arena or the duelist facing him.
"""

from __future__ import annotations

from termcade.core.rng import Rng

from ..flow.battle import Side
from ..mechanics.powers import mechanic_of
from ..mechanics.scoring import element_score
from ..schema.catalog import load_mechanic_config
from ..schema.models import Card, Mechanic, Player
from . import jong

_BOT = load_mechanic_config()["bot"]

# Jack-Bot's curse flavour (see :func:`choose_jack_bot`) — its own pool, separate from ATTACK_BOT_NAMES.
JACK_BOT_NAMES = ("Jack-Bot", "Tickle-Bot", "Yes-Bot", "Chef-Bot", "Soda-Bot")

# The two identity swaps (see :func:`choose_jack_mode`). Fixed names, not a rotating pool.
AI_JACK_NAME = "AI Jack"
CHAMELON_NAME = "Chamelon-Bot"
# Chamelon-Bot's denial is a synthetic Card built fresh each cycle (see
# `duel.Duel._chamelon_boost_card`), never a real catalog row. Id reserved, negative, and distinct
# from every real power id and from Jack-Bot's own -8, so it can never collide with one.
CHAMELON_BOOST_ID = -9

# Jack-bots Attack! swaps to a name from THIS pool, chosen fresh each time, never twice in a row —
# its own pool, separate from JACK_BOT_NAMES.
ATTACK_NAME = "Jack-bots Attack!"
# Flat, before the metal swing (see `duel.Duel._jack_base`).
ATTACK_STAT = _BOT["attack_stat"]
ATTACK_BOT_NAMES = (
    "Blade-Bots", "Gun-Bots", "Hound-Bots", "Giant Jack-Bot", "Wuya-Bot", "Chase-Bot", "Hannibal-Bot",
    "Winged-Bots", "Regenerating Jack-Bots", "Cheerleader-Bots", "Junk-Bots", "U-Bots", "Guard-Bots",
)

# A Yin/Yang Yo-Yo away (see `Player.yoyo_flipped`, `duel.Duel._jack_base`), not a bot swap: he still
# fights as himself. Force/agility are GOOD_JACK_STAT plus whatever training delta Evil Jack has
# already banked on them — JACK_PRINTED_PHYSICAL (3) is Evil Jack's own printed force/agility, the
# baseline that delta is measured against. Intellect is its own, separately trained value
# (`Player.good_jack_intellect`), never derived from Evil's frozen real 7. Can't deploy any bot form
# while worn (see `duel.Duel._choose_jack_mode`).
GOOD_JACK_NAME = "Good Jack"
GOOD_JACK_STAT = _BOT["good_jack_stat"]
JACK_PRINTED_PHYSICAL = _BOT["printed_physical"]


def jack_stat_override(
    jack_mode: str | None, background: str | None, jack_player: Player
) -> dict[str, int] | None:
    """The stats Jack fights this showdown with, when they diverge from his own printed base — else
    ``None`` (plain battle stats apply).

    Attack! is a flat ``ATTACK_STAT`` on every stat, metal, plus the same resonance/suffer swing a
    metal Wu gets for free — ``Character`` carries no element of its own, so it's added here, same
    shape as ``BEAST_BOOST``. The swing needs a decided ``background``; it reads as neutral (0)
    while one is still being picked.

    Good Jack (``Player.yoyo_flipped``) is a flat ``GOOD_JACK_STAT`` on force/agility plus whatever
    training delta Evil Jack has already banked on them; intellect is his own separately trained
    value (``Player.good_jack_intellect``), never derived from Evil's.

    The one seam every bot-stats read of him passes through, on both sides that need it: the duel's
    own scoring (``Duel._jack_base``) and the board's live header (``duel_board._jack_stats``).
    """
    if jack_mode == ATTACK_NAME:
        swing = element_score("metal", background) if background else 0
        return {stat: ATTACK_STAT + swing for stat in jong.battle_stats(jack_player)}
    if mechanic_of(jack_player.character.power) is Mechanic.BOT and jack_player.yoyo_flipped:
        real = jack_player.character.stats
        return {
            "force": GOOD_JACK_STAT + (real["force"] - JACK_PRINTED_PHYSICAL),
            "agility": GOOD_JACK_STAT + (real["agility"] - JACK_PRINTED_PHYSICAL),
            "intellect": jack_player.good_jack_intellect,
        }
    return None

# Jack's keyed counters (see docs/design/BOSSES.md). Read by `bot.steal_target`'s ``prefer`` and
# `turn._priority_deposit`, via `turn.counters_against`.
counter = frozenset(
    {Mechanic.HACK, Mechanic.STEAL, Mechanic.CONDUCT, Mechanic.STAT_SWAP, Mechanic.CHI_SWAP}
)


def is_counter(card: Card) -> bool:
    """Whether ``card`` is one of Jack's keyed counters."""
    return mechanic_of(card.power) in counter


def choose_jack_bot(opponent: Side) -> bool:
    """Jack's per-boost call: deploy Jack-Bot to curse the opponent (``True``), or hold it back for
    a normal Wu self-buff instead (``False``) — Jack-Bot itself never buffs, only curses.

    Deploys unless the opponent already can't be cursed this battle (a Reversing Mirror is up).
    Excluded from the generic ``bot.choose_boost`` comparison because that machinery only weighs a
    boost against the caster's *own* reach — never one that lands on the opponent instead.
    """
    return not opponent.defence_negated


ATTACK_MIN_CHANCE = _BOT["attack_min_chance"]  # a floor: never fully vanishes, only fades
ATTACK_MAX_CHANCE = _BOT["attack_max_chance"]  # a ceiling: even desperate, there is some chance he stays himself

# Attack! always transfers the full prize outright, no partial-credit ladder (`PrizeRoute.BRAWL_WON`)
# — see BOSSES.md for the rates behind these two constants.
ATTACK_CHANCE_WHEN_LEADING = _BOT["attack_chance_when_leading"]  # percent — Jack leads, already strong

ATTACK_CHANCE_WHEN_TRAILING = _BOT["attack_chance_when_trailing"]  # percent at momentum 0
# `jack_attack_momentum` (XiaolinState) shifts this with the run's recent record — losing a showdown
# reaches for Attack! harder, winning one leaves it alone — clamped to +-ATTACK_MOMENTUM_CAP, a
# fresh run starting at 0.
ATTACK_MOMENTUM_STEP = _BOT["attack_momentum_step"]  # percentage points shifted per showdown won/lost
ATTACK_MOMENTUM_CAP = _BOT["attack_momentum_cap"]  # how far a streak can push the trailing chance

# Fleeing a lost showdown: no route can claim the prize (it goes to lost, never to the winner), and
# his wager stays his. No downside on any single use, so it is capped instead of tuned.
JACK_FLEE_CAP = _BOT["flee_cap"]  # per run


def choose_to_flee(flees_used: int) -> bool:
    """Whether Jack concedes a showdown he has already lost, rather than pay the normal cost."""
    return flees_used < JACK_FLEE_CAP


# Chamelon-Bot's denial is a BOOST (see `duel.Duel._chamelon_boost_card`), competing with a real Wu
# for the one boost his fielded Wu gets — fed into `bot.choose_boost`'s own reach-comparison alongside
# Shimo Staff, the Heart, or anything else in hand, rather than preferred by default (it targets his
# OWN side, unlike Jack-Bot's curse, so the same machinery can weigh it fairly).
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

    Attack! rolls first, a priority-aware percentage (:func:`attack_chance`). It neither reads nor
    writes ``can_swap``, so it never disrupts the pattern underneath it.

    Missing that roll, priority decides which stand-in is even on the table — the two never compete:
    Chamelon-Bot when the player is about to name the challenge (unconditional); AI Jack when HE
    leads instead, gated by ``can_swap`` alone — the "cannot spam a stand-in" rule is his, not
    Chamelon-Bot's.
    """
    if rng.randint(1, 100) <= attack_chance(player_has_priority, momentum):
        return ATTACK_NAME
    if player_has_priority:
        return CHAMELON_NAME
    return AI_JACK_NAME if can_swap else None
