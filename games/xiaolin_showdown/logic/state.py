"""``XiaolinState`` — the between-duel game state the engine persists.

Implements the engine's ``GameState`` protocol (``schema_version`` / ``snapshot`` /
``restore``). Saving is menu-only, so this captures exactly the state that exists at the
temple menu (``duel_stage == 0``): both duelists' hands/decks/points/character, the draw
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
from .mechanics.cards import held_as_wudai
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
    # Actions spent this turn, one counter each (both reset by the duel end phase). A temple turn buys
    # one action — bank a Wu, spend a Wu's power, or draw one off your shelf — so the hand is a
    # resource and a Wu spent is a Wu not replaced.
    #
    # The bot has its own because it is held to the same count, and because the mercy rule can spend
    # it: a duelist dealt back in from the pile (`turn._emergency_fill`) has had their turn's action
    # spent for them. The cards are the action, not a gift on top of it.
    actions_taken: int = 0
    bot_actions_taken: int = 0
    # The opponent takes the same temple turn you do, and takes it once. Retreating from a
    # showdown returns you to a turn you have already spent, so this keeps them from banking
    # twice on the way back in. Reset, like the counters, by the duel end phase.
    bot_turn_done: bool = False
    # What the Mind Reader Conch was promised: who holds priority in the next showdown, whatever
    # the initiative sums say. ``None`` is the ordinary game, where the hands decide.
    #
    # Spent by the duel *end* phase, not by the showdown that reads it — a player who opens a
    # showdown and retreats has not had their answer yet, and the Conch is already gone from their
    # hand. Burning it there would sell them a Wu for nothing.
    forced_priority: bool | None = None
    # The new Mind Reader Conch (Prognosis): you let the opponent lead, but you read their every move.
    # ``locked_challenge`` is the stat they are pinned to next showdown (chosen the moment the Conch is
    # spent, revealed to you, unchanged even as their hand shifts); ``conch_tiebreak`` is who holds the
    # challenger's ground despite NOT leading — the caster. Both spent by the duel end phase, like
    # ``forced_priority``. ``None`` is the ordinary game.
    locked_challenge: str | None = None
    conch_tiebreak: bool | None = None
    # Wu that surfaced, were fought over, and that nobody won hard enough to keep. They are **lost**,
    # not destroyed: out of play, and one day recoverable (the Rooster Booster reaches for the oldest).
    # Shared — a Wu dies to a showdown, not to a duelist.
    lost: list[Card] = field(default_factory=list)

    schema_version: int = 1

    # --- whose side is this ---------------------------------------------------------
    # Mirrors `DuelState.duelist` (the in-duel half), so one question has one spelling.
    def duelist(self, is_player: bool) -> Player:
        return self.player if is_player else self.bot

    def opponent(self, is_player: bool) -> Player:
        return self.bot if is_player else self.player

    @property
    def boss_run(self) -> bool:
        """Whether this run's opponent is a boss — the boss-run rules key off this.

        Derived from the opponent, never stored: the roster the run was dealt from IS the fact.
        """
        return self.bot.character.tier == "boss"

    def actions_spent(self, is_player: bool) -> int:
        return self.actions_taken if is_player else self.bot_actions_taken

    def spend_action(self, is_player: bool, count: int = 1) -> None:
        if is_player:
            self.actions_taken += count
        else:
            self.bot_actions_taken += count

    # --- engine GameState protocol -------------------------------------------------
    def snapshot(self) -> dict[str, Any]:
        return {
            "player": _player_dict(self.player),
            "bot": _player_dict(self.bot),
            "card_deck": [c.id for c in self.card_deck],
            "previous_challenge": list(self.previous_challenge),
            "previous_background": list(self.previous_background),
            "has_ended": self.has_ended,
            "actions_taken": self.actions_taken,
            "bot_actions_taken": self.bot_actions_taken,
            "bot_turn_done": self.bot_turn_done,
            "forced_priority": self.forced_priority,
            "locked_challenge": self.locked_challenge,
            "conch_tiebreak": self.conch_tiebreak,
            "lost": [card.id for card in self.lost],
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
            # A save from before the one-action turn counted a deposit and a draw separately. Both
            # were spends of the turn, so the sum is what the turn had already cost.
            actions_taken=data.get(
                "actions_taken", data.get("deposit_counter", 0) + data.get("draw_counter", 0)
            ),
            bot_actions_taken=data.get("bot_actions_taken", 0),
            bot_turn_done=data.get("bot_turn_done", False),
            forced_priority=data.get("forced_priority"),  # absent in a save from before the Conch
            locked_challenge=data.get("locked_challenge"),
            conch_tiebreak=data.get("conch_tiebreak"),
            lost=[_fresh_card(catalog, cid) for cid in data.get("lost", [])],
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
        # Wear rides beside the ids (same order): a rebuilt card must remember its showdowns —
        # the live count AND the other duelist's pocketed one (see wear.hand_over).
        "hand_uses": [c.uses for c in p.hand],
        "deck_uses": [c.uses for c in p.deck],
        "hand_uses_memory": [c.uses_memory for c in p.hand],
        "deck_uses_memory": [c.uses_memory for c in p.deck],
        "training": p.training,
        "just_trained": p.just_trained,
        # The catalog knows only printed stats — training raises them, so the current values are
        # the save's to keep.
        "stats": p.character.stats,
    }


def _player_from_dict(data: dict[str, Any], catalog: Catalog) -> Player:
    player = Player(
        character=deepcopy(catalog.character(data["character"])),
        hand=[_fresh_card(catalog, cid) for cid in data["hand"]],
        inalienable_hand=[held_as_wudai(_fresh_card(catalog, cid)) for cid in data["inalienable_hand"]],
        deck=[_fresh_card(catalog, cid) for cid in data["deck"]],
        points=data["points"],
        training=data.get("training", 0),
        just_trained=data.get("just_trained", False),
    )
    # The catalog knows only printed stats — training raised these past them.
    player.character.stats.update(data.get("stats", {}))
    for card, uses in zip(player.hand, data.get("hand_uses", ())):
        card.uses = uses
    for card, uses in zip(player.deck, data.get("deck_uses", ())):
        card.uses = uses
    for card, memory in zip(player.hand, data.get("hand_uses_memory", ())):
        card.uses_memory = memory
    for card, memory in zip(player.deck, data.get("deck_uses_memory", ())):
        card.uses_memory = memory
    return player
