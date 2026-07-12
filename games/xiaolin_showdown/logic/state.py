"""``XiaolinState`` — the between-duel game state the engine persists.

Implements the engine's ``GameState`` protocol (``schema_version`` / ``snapshot`` /
``restore``). Saving is menu-only, so this captures exactly the state that exists at the
vault menu (``duel_stage == 0``): both duelists' hands/decks/points/character, the draw
pile, and the cross-duel challenge/background history. Transient in-duel scratch is never
here — it does not exist between duels.

Serialization stores card/character *ids*; :meth:`restore` rehydrates fresh instances
from the catalog. The RNG stream and the run's frozen settings (``XiaolinSettings``) are
persisted separately by the engine's ``SaveManager`` — not here.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from .catalog import Catalog, load_catalog
from .models import Card, Player


@dataclass
class XiaolinState:
    catalog: Catalog
    player: Player
    bot: Player
    card_deck: list[Card] = field(default_factory=list)
    previous_challenge: list[str] = field(default_factory=list)
    previous_background: list[str] = field(default_factory=list)
    has_ended: bool = False
    deposit_counter: int = 0  # deposits used this turn (reset by the duel end phase)
    draw_counter: int = 0  # draws used this turn (reset by the duel end phase)
    # The opponent takes the same vault turn you do, and takes it once. Retreating from a
    # showdown returns you to a turn you have already spent, so this keeps them from banking
    # twice on the way back in. Reset, like the counters, by the duel end phase.
    bot_turn_done: bool = False

    schema_version: int = 1

    # --- engine GameState protocol -------------------------------------------------
    def snapshot(self) -> dict[str, Any]:
        return {
            "player": _player_dict(self.player),
            "bot": _player_dict(self.bot),
            "card_deck": [c.id for c in self.card_deck],
            "previous_challenge": list(self.previous_challenge),
            "previous_background": list(self.previous_background),
            "has_ended": self.has_ended,
            "deposit_counter": self.deposit_counter,
            "draw_counter": self.draw_counter,
            "bot_turn_done": self.bot_turn_done,
        }

    @classmethod
    def restore(cls, data: dict[str, Any], ctx: Any) -> "XiaolinState":
        catalog = load_catalog()
        return cls(
            catalog=catalog,
            player=_player_from_dict(data["player"], catalog),
            bot=_player_from_dict(data["bot"], catalog),
            card_deck=[_fresh_card(catalog, cid) for cid in data["card_deck"]],
            previous_challenge=list(data["previous_challenge"]),
            previous_background=list(data["previous_background"]),
            has_ended=data["has_ended"],
            deposit_counter=data.get("deposit_counter", 0),
            draw_counter=data.get("draw_counter", 0),
            bot_turn_done=data.get("bot_turn_done", False),
        )


def _fresh_card(catalog: Catalog, card_id: int) -> Card:
    # Own a private copy: duel logic mutates card scratch in place, never the catalog.
    return deepcopy(catalog.card(card_id))


def _player_dict(p: Player) -> dict[str, Any]:
    return {
        "character": p.character.id,
        "points": p.points,
        "hand": [c.id for c in p.hand],
        "inalienable_hand": [c.id for c in p.inalienable_hand],
        "deck": [c.id for c in p.deck],
    }


def _player_from_dict(data: dict[str, Any], catalog: Catalog) -> Player:
    return Player(
        character=deepcopy(catalog.character(data["character"])),
        hand=[_fresh_card(catalog, cid) for cid in data["hand"]],
        inalienable_hand=[_fresh_card(catalog, cid) for cid in data["inalienable_hand"]],
        deck=[_fresh_card(catalog, cid) for cid in data["deck"]],
        points=data["points"],
    )
