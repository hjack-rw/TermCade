"""How a stored name is shown to a human — pure string work, no rendering.

Lives in ``logic`` (not ``screens``) so both the display layer AND the duel can reach it: a summon Wu
fills ``{caster}`` with a duelist's *short* name, and the temple state row shortens the same way when a
phone cannot spare the columns. One rule, one home.
"""

from __future__ import annotations

# A name longer than this is shortened to its first word where space is scarce. The threshold is the
# point of it: "Le Mime" is two words and seven characters, and "Le" is not a name — so the rule has
# to fire on what a name COSTS, not on how many words it happens to have. At 10 it takes Salvador
# Cumo, Hannibal Roy Bean and Chase Young, all of whom are known by their first name, and leaves
# Le Mime whole.
SHORTEN_OVER = 10


def display_name(name: str, *, upper: bool = False, short: bool = False) -> str:
    """A stored name shown for humans: underscores become spaces (``Salvador_Cumo`` -> ``Salvador Cumo``).
    ``upper`` shouts it for a heading, keeping the underscore rule in one place.

    ``short`` asks for the first word alone, and is honoured only for a name long enough to be worth
    it (see ``SHORTEN_OVER``). Two callers: a phone's temple state row (space), and a summon Wu naming
    the clone/horde it calls up after its caster (``Clone of Chase``, not ``Clone of Chase Young``).
    """
    shown = name.replace("_", " ")
    if short and len(shown) > SHORTEN_OVER:
        shown = shown.split(" ", 1)[0]
    return shown.upper() if upper else shown
