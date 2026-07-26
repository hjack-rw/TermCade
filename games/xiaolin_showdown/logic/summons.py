"""Summon flavour — what a summon Wu shows on the board instead of its own name.

Five pools, keyed one of three ways:

- by the **arena** element — ``{beast}`` (Tongue of Saiping), ``{drawing}`` (Imo Gazer);
- by the **caster's** character — ``{spirit}`` (Monarch Wings), ``{desire}`` (Moonstone Cat's Eye),
  and the Heart of Jong's metal form (Jack Spicer's Dude-Bot);
- by the **target's** character — ``{fear}`` (Shadow of Fear), the fear of the duelist it lands on.

Pure data and pure functions: the duel passes the two characters and the arena. The stats never change
here — a summon is a costume over its Wu. Flavour, the user's own picks; reword the pools freely.
"""

from __future__ import annotations

from .models import Character
from .naming import display_name

# What a ``{beast}`` Wu calls up, one per ARENA element — the background decides it (Tongue of Saiping's
# animals, Imo Gazer draws from ``{drawing}`` below), so the same Wu summons a shoal on water and a
# troop on metal.
_BEASTS = {
    "water": "a Pod of Seals",
    "fire": "a Congress of Salamanders",
    "wind": "a Kettle of Vultures",
    "earth": "a Sounder of Boars",
    "metal": "a Troop of Monkeys",
}

# Imo Gazer's own pool (``{drawing}``): a fantastic beast of Chinese myth sketched to life, one per
# element — the Four Symbols and the Qilin, mapped onto the arena.
_DRAWINGS = {
    "water": "the Black Turtle-Snake",
    "fire": "the Vermilion Bird",
    "wind": "the Azure Dragon",  # East/Wood in myth; wind is this game's stand-in for it
    "earth": "the Qilin",
    "metal": "the White Tiger",
}

# Moonstone Cat's Eye ({desire}) conjures whatever the caster most wants made real — keyed to the
# duelist, one per character. A caster with no entry (a construct, say) falls back to a plain figment.
_DESIRES = {
    "Omi": "his Long Lost Parents",
    "Raimundo": "a Carnival of Revelers",
    "Kimiko": "a Wave of Space Invaders",
    "Clay": "a Herd of Texan Longhorns",
    "Tubbimura": "a Sumo Wrestler",
    "Katnappé": "a Litter of Kittens",
    "Salvador_Cumo": "a Komodo Dragon",
    "Vlad": "a Set of Matryoshka Dolls",
    "Le_Mime": "an Invisible Impenetrable Box",
    "PandaBubba": "a Mob of Goons",
    "Hannibal_Roy_Bean": "a Towering Suit of Armor",
    "Wuya": "an Army of Rock Golems",
    "Chase_Young": "an Evil Omi",
}
_A_FIGMENT = "a Figment of the Imagination"

# Heart of Jong: the character its life leaps into in the boost slot, one per background element. Metal
# waits on a face not yet in the roster — Jack Spicer's form is the Dude-Bot; until he is a playable,
# everyone's metal form is the T-Rex.
_JONG_FORMS = {
    "water": "Raksha",
    "fire": "Cyclops",
    "wind": "Bird of Paradise",
    "earth": "Gigi",
    "metal": "T-Rex",
}

# Shadow of Fear ({fear}) gives a body to the worst fear of the duelist it is used ON — the target, not
# the caster. Keyed to the victim's character. The Heylin bosses fear the one who bound them, Grand
# Master Dashi. An unfilled entry meets a nameless dread.
_FEARS = {
    "Omi": "a Squirrel",
    "Kimiko": "a Melted Tamochika Doll",
    "Raimundo": "a Jellyfish Monster",
    "Clay": "Clay's Granny Lily",
    "Tubbimura": "an Empty Rice Bowl",
    "Katnappé": "a Dog",
    "Salvador_Cumo": "an Angry Wuya",
    "Vlad": "a Swimming Pool",
    "Le_Mime": "a Booing Crowd",
    "PandaBubba": "a Jail Cell",
    "Hannibal_Roy_Bean": "a Vision of Grand Master Dashi",
    "Wuya": "a Vision of Grand Master Dashi",
    "Chase_Young": "a Vision of Grand Master Dashi",
}
_A_NAMELESS_DREAD = "a Nameless Dread"


def _spirit(caster: Character) -> str:
    """Monarch Wings ({spirit}) calls a spirit chosen by the caster's side, not the arena: a Chi Creature
    for the Xiaolin, Sibini for the Heylin — but Hannibal, a Yin-Yang world native, draws no Sibini and
    gets the Ying-Yang Bird."""
    if caster.name == "Hannibal_Roy_Bean":
        return "Ying-Yang Bird"
    return "Chi Creature" if caster.affiliation == "xiaolin" else "Sibini"


# Mala Mala Jong wears its own fear and desire over the duelist underneath (see logic/jong.py): it
# dreads the Vault it could be disassembled into, and it wants what its real side wants.
_JONG_FEAR = "the Shen Gong Wu Vault"


def _desire(caster: Character, *, is_jong: bool = False) -> str:
    """Moonstone Cat's Eye ({desire}) conjures what the caster most wants — keyed to the character, or
    to the construct's side when Mala Mala Jong casts it (peace for the Xiaolin under it, else dominion)."""
    if is_jong:
        return "World Peace" if caster.affiliation == "xiaolin" else "World Domination"
    return _DESIRES.get(caster.name, _A_FIGMENT)


def _fear(target: Character, *, is_jong: bool = False) -> str:
    """Shadow of Fear ({fear}) gives a body to the TARGET's worst fear — the duelist it lands on, or the
    construct's own dread of the Vault when Mala Mala Jong is the target."""
    if is_jong:
        return _JONG_FEAR
    return _FEARS.get(target.name) or _A_NAMELESS_DREAD  # an unfilled entry meets the dread too


def jong_form(element: str, caster: Character) -> str:
    """Which animated form the Heart of Jong wakes, by the arena element — and, on metal, by who cast it:
    Jack Spicer's own construct is the Dude-Bot, not the T-Rex. Dormant until Jack joins the roster."""
    if element == "metal" and caster.name == "Jack_Spicer":
        return "Dude-Bot"
    return _JONG_FORMS.get(element, "")


def summon_name(
    template: str,
    *,
    caster: Character,
    target: Character,
    arena: str,
    caster_is_jong: bool = False,
    target_is_jong: bool = False,
) -> str:
    """Fill a Wu's ``summon`` template with the form it calls up. ``{caster}`` is the short name of the
    duelist fielding it; ``{fear}`` is the *target's* (their opponent's); the rest key off the arena or
    the caster. The ``*_is_jong`` flags swap ``{desire}``/``{fear}`` to the construct's own when that
    side wears the form. Unused placeholders in a template are simply left untouched."""
    return (
        template.replace("{caster}", display_name(caster.name, short=True))
        .replace("{beast}", _BEASTS.get(arena, ""))
        .replace("{drawing}", _DRAWINGS.get(arena, ""))
        .replace("{spirit}", _spirit(caster))
        .replace("{desire}", _desire(caster, is_jong=caster_is_jong))
        .replace("{fear}", _fear(target, is_jong=target_is_jong))
    )
