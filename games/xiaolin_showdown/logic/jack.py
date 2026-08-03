"""Jack Spicer's own flavour pools — the names his bots wear.

Kept apart from :mod:`summons` (whose pools are keyed off the *character* holding a Wu) because
these are keyed off nothing but Jack himself, chosen fresh each time he uses the power, not derived
from the arena or the duelist facing him.
"""

from __future__ import annotations

# Jack-Bot's curse flavour (see logic/bot.choose_jack_bot): singular, joke-shaped constructs, unlike
# the Attack! pool's swarms and heavy-hitters — the owner's own split, not a balance one.
JACK_BOT_NAMES = ("Jack-Bot", "Tickle-Bot", "Yes-Bot", "Chef-Bot", "Soda-Bot")

# The two identity swaps (see logic/bot.choose_jack_mode). Fixed names, not a rotating pool like
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
