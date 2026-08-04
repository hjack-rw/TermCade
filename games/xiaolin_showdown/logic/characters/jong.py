"""Mala Mala Jong — the assembly win-condition, as a character transformation.

Not a fielded Wu: a duelist who holds a full set of body parts and the Heart of Jong may, at the
temple, **become** Mala Mala Jong — a 6/6/6 construct (Wuya-tier). The form is a costume worn over
the real duelist: everything a screen shows reads the construct, but every rule that reads *who* is
playing — the ``{fear}``/``{spirit}`` summon pools, the boss-training asymmetry, the roster tier —
still sees the real Omi (or whoever) underneath. So this module only ever *overlays*; it never
overwrites ``player.character``, which is what a revert restores to.

The form persists between showdowns (it lives on :class:`~.models.Player`, the between-duel state)
until the game ends in it (an auto-win) or the set is broken (a form-drop). Both are handled by the
duel and temple layers; this module holds the pure state and the queries they read.
"""

from __future__ import annotations

from ..mechanics.powers import mechanic_of
from ..schema.models import Card, Mechanic, Player

# The construct's costume: the name and affiliation a screen shows, and the flat stat it fights at.
# Wuya-tier (6/6/6); Chase is 7/7/7, so the form is a genuine spike for a Xiaolin and lateral for a
# boss. Never written onto the real character — read through :func:`battle_stats` / :func:`shown_name`.
JONG_NAME = "Mala Mala Jong"
JONG_AFFILIATION = "construct"
JONG_STAT = 6
# The construct boosts only with its own Heart, and only as itself: a flat 1/1/1, element metal, one
# battle — not the ANIMATE summon (no arena form, no opponent's off-wager answer). The Heart it exiled
# to build the form is the source, so it is never staked and never wears (see duel._commit_boost).
JONG_BOOST_STAT = 1

# The five assembly slots — one Wu of each ``type`` (any Wu of that type counts) plus the Heart is
# the gate. The slot is otherwise cosmetic (see JONG.md); this is the one place that lists them.
PART_TYPES: tuple[str, ...] = ("head", "torso", "arms", "boots", "amulet")


def _is_heart(card: Card) -> bool:
    """The Heart of Jong — the only ANIMATE Wu, matched by mechanic so a re-id can't slip past it."""
    return mechanic_of(card.power) is Mechanic.ANIMATE


def battle_stats(player: Player) -> dict[str, int]:
    """The base stats a battle scores: a flat 6/6/6 in the form, else the real ones — minted fresh, so
    a revert restores the training-raised originals ``character.stats`` still holds."""
    if player.jong_form:
        return {stat: JONG_STAT for stat in player.character.stats}
    return player.character.stats


def shown_name(player: Player) -> str:
    """The character name a screen prints — the construct's in form, else the real one. Logic reads
    ``player.character.name``, never this, so summon pools and boss rules see the real duelist."""
    return JONG_NAME if player.jong_form else player.character.name


def shown_affiliation(player: Player) -> str:
    """The affiliation a screen prints — ``construct`` in form, the real xiaolin/heylin otherwise."""
    return JONG_AFFILIATION if player.jong_form else player.character.affiliation


def _one_of_each_part(hand: list[Card]) -> dict[str, Card] | None:
    """The first Wu found for each of the five slots, or ``None`` if any slot is empty."""
    found: dict[str, Card] = {}
    for card in hand:
        if card.type in PART_TYPES and card.type not in found:
            found[card.type] = card
    return found if len(found) == len(PART_TYPES) else None


def can_construct(player: Player) -> bool:
    """The gate: not already a construct, and the hand holds one Wu of each slot AND the Heart.

    Reads only the drawn hand — the parts are ordinary typed Wu, never the inalienable wudai slot.
    """
    if player.jong_form:
        return False
    if not any(_is_heart(card) for card in player.hand):
        return False
    return _one_of_each_part(player.hand) is not None


def construct(player: Player) -> list[Card]:
    """Become Mala Mala Jong: keep the five parts and any wudai, exile the Heart, deposit the rest.

    Returns the Wu deposited by the purge (already banked here for their points) so the caller can
    report them. The Heart goes out of play onto :attr:`Player.jong_heart` — it powers the form and
    cannot be recalled while it holds; a form-drop by a lost showdown hands it to the winner.
    """
    parts = _one_of_each_part(player.hand)
    assert parts is not None, "construct() called without a full set — gate with can_construct first"
    kept = set(id(card) for card in parts.values())

    heart = next(card for card in player.hand if _is_heart(card))
    player.jong_heart = heart
    player.hand.remove(heart)

    purged: list[Card] = []
    for card in list(player.hand):
        if id(card) in kept or card.type == "wudai":
            continue  # the body and the wudai weapons stay; everything else is deposited for points
        player.hand.remove(card)
        player.points += card.points
        player.vault.append(card)
        purged.append(card)

    player.jong_form = True
    return purged


def deposit_won(player: Player, card: Card) -> None:
    """Bank a won Wu for its points and vault it (still Treasurebox-recoverable) — the construct's
    locked hand only ever shrinks, so a won Wu is never held."""
    player.points += card.points
    player.vault.append(card)


def take_won(player: Player, card: Card) -> None:
    """Give a won Wu to ``player``: into the hand, or banked (:func:`deposit_won`) if the hand is a
    locked construct. The caller that resets wear passes ``hand_over(card)``."""
    if player.jong_form:
        deposit_won(player, card)
    else:
        player.hand.append(card)


def set_intact(player: Player) -> bool:
    """A constructed hand still holds one Wu of each of the five slots (the Heart is exiled, not counted)."""
    return _one_of_each_part(player.hand) is not None


def drop_if_broken(player: Player) -> Card | None:
    """A part left the hand (steal, Bounce, Transfer, discard, wear-out) → drop the form, Heart back to
    this duelist. NOT the lost-showdown drop (that gives the Heart to the winner, in duel._end)."""
    if not player.jong_form or set_intact(player):
        return None
    heart = revert(player)
    if heart is not None:
        player.hand.append(heart)
    return heart


def revert(player: Player) -> Card | None:
    """Drop the form; return the exiled Heart, unplaced — the caller puts it in the right hand (this
    duelist's on a set-break, the winner's on a lost showdown)."""
    player.jong_form = False
    heart = player.jong_heart
    player.jong_heart = None
    return heart
