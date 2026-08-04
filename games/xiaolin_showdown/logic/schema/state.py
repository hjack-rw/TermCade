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
from typing import TYPE_CHECKING, Any

from .catalog import Catalog, load_catalog
from ..mechanics.cards import held_as_wudai
from .models import Card, Player

if TYPE_CHECKING:  # settings imports nothing from here, but importing it at runtime would still cycle
    from termcade.core.rng import Rng

    from ..config.settings import XiaolinSettings


@dataclass
class XiaolinState:
    catalog: Catalog
    player: Player
    bot: Player
    card_deck: list[Card] = field(default_factory=list)
    previous_challenge: list[str] = field(default_factory=list)
    previous_background: list[str] = field(default_factory=list)
    has_ended: bool = False
    # Actions spent this turn (reset by the duel end phase). The bot has its own because
    # `turn._emergency_fill` (the mercy rule) can spend it on the bot's behalf.
    actions_taken: int = 0
    bot_actions_taken: int = 0
    # How many of this turn's actions went to the vault — kept separate because `actions_taken` alone
    # can't say which actions were deposits (see `settings.deposit_limit`).
    deposits_taken: int = 0
    bot_deposits_taken: int = 0
    # The opponent takes the same temple turn you do, and takes it once. Retreating from a
    # showdown returns you to a turn you have already spent, so this keeps them from banking
    # twice on the way back in. Reset, like the counters, by the duel end phase.
    bot_turn_done: bool = False
    # Who holds priority next showdown, set by a temple power. ``None`` is the ordinary game.
    #
    # Spent by the duel *end* phase, not by the showdown that reads it — a player who opens a
    # showdown and retreats has not had their answer yet, and burning it there would sell them
    # a Wu for nothing.
    forced_priority: bool | None = None
    # The Prognosis power's promise: ``locked_challenge`` is the stat the opponent is pinned to next
    # showdown; ``conch_tiebreak`` is who holds the challenger's ground despite not leading. Both
    # spent by the duel end phase, like ``forced_priority``. ``None`` is the ordinary game.
    locked_challenge: str | None = None
    conch_tiebreak: bool | None = None
    # Who seized the challenger's ground this showdown (SEIZE_GROUND), or ``None``. Tracked apart from
    # ``conch_tiebreak`` so a second seize reads as a clash to cancel, not as overwriting a Prognosis.
    # Spent by the duel end phase.
    ground_seized: bool | None = None
    # The board and RNG stream as they stood before the player's most recent temple action, kept so an
    # AMEND power can put them back. One level deep. Never serialized — a run is saved only between
    # turns, when it is ``None`` (cleared at turn-over by ``turn.refill_hands``).
    undo_stash: tuple[dict[str, Any], list[Any]] | None = None
    # Both duelists reached for the initiative the same turn: neither's answer stands and the coin
    # decides. Set when a second initiative power lands on an already-answered showdown; spent by the
    # duel end phase.
    initiative_contested: bool = False
    # How many Wu Wuya's witchcraft has called back this run (see `characters.wuya.WITCH_RECALL_LIMIT`).
    # Per-run, never reset by the turn.
    witch_recalls: int = 0
    # The Jack-Bot flavour last cursed under (`jack.JACK_BOT_NAMES`), so the next curse can rule it
    # out. Per-run, not per-showdown — must survive the temple between fights and a reload.
    last_jack_bot_name: str | None = None
    # Same idea for Attack!'s own pool (`jack.ATTACK_BOT_NAMES`) — a separate counter, since the two
    # never rule each other out.
    last_attack_bot_name: str | None = None
    # Whether a stand-in (AI Jack/Chamelon-Bot) is eligible next showdown — alternates with playing
    # himself (see `jack.choose_jack_mode`). Starts `False`. Attack! rolls independently and never
    # touches this.
    jack_can_swap: bool = False
    # Jack's recent form this run, in showdowns won/lost — feeds Attack!'s own odds (see
    # `jack.choose_jack_mode`/`attack_chance`). Updated at showdown end (`duel._end`), clamped so a
    # streak can't run away.
    jack_attack_momentum: int = 0
    # How many showdowns Jack has fled this run (see `jack.choose_to_flee`). Capped at
    # `jack.JACK_FLEE_CAP`.
    jack_flees_used: int = 0
    # Wu fought over and won by neither side — out of play, not destroyed, and one day recoverable
    # (the Rooster Booster reaches for the oldest). Shared between both duelists.
    lost: list[Card] = field(default_factory=list)
    # Wu spent on their own power and discarded (deposited Wu are banked and never reach it). Shared,
    # in the order used — a Refresh Wu calls the most recent back into the caster's hand.
    used: list[Card] = field(default_factory=list)
    # A per-game win target, when this run deals a weighted subset of the pool (its size varies, so its
    # target must too). ``None`` uses ``settings.point_limit`` — the ordinary whole-pool game.
    point_limit: int | None = None

    schema_version: int = 1

    def win_target(self, settings: "XiaolinSettings") -> int:
        """The points that end the run: this game's own if it dealt a subset, else the settings'."""
        return self.point_limit if self.point_limit is not None else settings.point_limit

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

    def stash_undo(self, rng: "Rng") -> None:
        """Remember the board and RNG stream before a player temple action, so a Hodoku Mouse can put
        them back. The RNG rides along: a gamble deposit undone without it would leave the stream
        advanced and the next roll would come out different (see the engine's ``spawn`` note)."""
        self.undo_stash = (self.snapshot(), rng.get_state())

    def undo(self, rng: "Rng") -> bool:
        """Put the board back the way it was before the last stashed action; restore the RNG too.

        The turn's action *budget* is deliberately NOT restored — the undone action and the Amend both
        cost — so it cannot loop. The Mouse itself is consumed by the caller, not handed back by this
        restore. Returns ``False`` when there is nothing to undo (the Amend then fizzles)."""
        if self.undo_stash is None:
            return False
        snapshot, rng_state = self.undo_stash
        self.undo_stash = None
        restored = XiaolinState.restore(snapshot, None)
        for name in ("player", "bot", "card_deck", "previous_challenge",
                     "previous_background", "lost", "used", "point_limit"):
            setattr(self, name, getattr(restored, name))
        rng.set_state(rng_state)
        return True

    # --- engine GameState protocol -------------------------------------------------
    def snapshot(self) -> dict[str, Any]:
        return {
            "player": _player_dict(self.player),
            "bot": _player_dict(self.bot),
            "card_deck": [c.id for c in self.card_deck],
            "previous_challenge": list(self.previous_challenge),
            "previous_background": list(self.previous_background),
            "has_ended": self.has_ended,
            "jack_attack_momentum": self.jack_attack_momentum,
            "jack_flees_used": self.jack_flees_used,
            "actions_taken": self.actions_taken,
            "bot_actions_taken": self.bot_actions_taken,
            "deposits_taken": self.deposits_taken,
            "bot_deposits_taken": self.bot_deposits_taken,
            "witch_recalls": self.witch_recalls,
            "last_jack_bot_name": self.last_jack_bot_name,
            "last_attack_bot_name": self.last_attack_bot_name,
            "jack_can_swap": self.jack_can_swap,
            "bot_turn_done": self.bot_turn_done,
            "forced_priority": self.forced_priority,
            "locked_challenge": self.locked_challenge,
            "conch_tiebreak": self.conch_tiebreak,
            "ground_seized": self.ground_seized,
            "initiative_contested": self.initiative_contested,
            "lost": [card.id for card in self.lost],
            "used": [card.id for card in self.used],
            "point_limit": self.point_limit,
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
            jack_attack_momentum=data.get("jack_attack_momentum", 0),  # absent before Attack!'s momentum
            jack_flees_used=data.get("jack_flees_used", 0),  # absent before the flee mechanic
            # A save from before the one-action turn counted a deposit and a draw separately. Both
            # were spends of the turn, so the sum is what the turn had already cost.
            actions_taken=data.get(
                "actions_taken", data.get("deposit_counter", 0) + data.get("draw_counter", 0)
            ),
            bot_actions_taken=data.get("bot_actions_taken", 0),
            # Absent in a save from before the deposit cap. Zero is the honest read: that run never
            # counted deposits, so it starts the loaded turn owing none.
            deposits_taken=data.get("deposits_taken", 0),
            bot_deposits_taken=data.get("bot_deposits_taken", 0),
            # Absent in a save from before the recall cap — that run spent them uncounted, so it
            # loads with its whole allowance. Generous, and it errs toward the boss, not the player.
            witch_recalls=data.get("witch_recalls", 0),
            last_jack_bot_name=data.get("last_jack_bot_name"),  # absent in a save from before Jack
            last_attack_bot_name=data.get("last_attack_bot_name"),  # absent before Attack!
            jack_can_swap=data.get("jack_can_swap", False),
            bot_turn_done=data.get("bot_turn_done", False),
            forced_priority=data.get("forced_priority"),  # absent in a save from before the Conch
            locked_challenge=data.get("locked_challenge"),
            conch_tiebreak=data.get("conch_tiebreak"),
            ground_seized=data.get("ground_seized"),  # absent in a save from before the Cube
            initiative_contested=data.get("initiative_contested", False),
            lost=[_fresh_card(catalog, cid) for cid in data.get("lost", [])],
            used=[_fresh_card(catalog, cid) for cid in data.get("used", [])],
            point_limit=data.get("point_limit"),
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
        "vault": [c.id for c in p.vault],  # deposited Wu, kept so a Treasurebox can wish one back
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
        # Mala Mala Jong (logic/characters/jong.py): the form persists between turns, so a save taken in it must
        # remember it AND the Heart it exiled — the character stays the real one (the form is an
        # overlay), so only these two ride along.
        "jong_form": p.jong_form,
        "jong_heart": p.jong_heart.id if p.jong_heart else None,
        # Yin/Yang Yo-Yo (logic/characters/jack.py): the affiliation flip (Good Jack, for Jack specifically)
        # persists across showdowns too, and Good Jack's own separately trained intellect with it.
        "yoyo_flipped": p.yoyo_flipped,
        "good_jack_intellect": p.good_jack_intellect,
    }


def _player_from_dict(data: dict[str, Any], catalog: Catalog) -> Player:
    player = Player(
        character=deepcopy(catalog.character(data["character"])),
        hand=[_fresh_card(catalog, cid) for cid in data["hand"]],
        inalienable_hand=[held_as_wudai(_fresh_card(catalog, cid)) for cid in data["inalienable_hand"]],
        deck=[_fresh_card(catalog, cid) for cid in data["deck"]],
        vault=[_fresh_card(catalog, cid) for cid in data.get("vault", ())],  # absent in a pre-Vault save
        points=data["points"],
        training=data.get("training", 0),
        just_trained=data.get("just_trained", False),
    )
    # The catalog knows only printed stats — training raised these past them.
    player.character.stats.update(data.get("stats", {}))
    # Mala Mala Jong: absent in a save from before the form — an ordinary duelist, no exiled Heart.
    player.jong_form = data.get("jong_form", False)
    heart_id = data.get("jong_heart")
    player.jong_heart = _fresh_card(catalog, heart_id) if heart_id is not None else None
    # Yin/Yang Yo-Yo: absent in a save from before it — never flipped, Good Jack's intellect untrained.
    player.yoyo_flipped = data.get("yoyo_flipped", False)
    player.good_jack_intellect = data.get("good_jack_intellect", 4)
    for card, uses in zip(player.hand, data.get("hand_uses", ())):
        card.uses = uses
    for card, uses in zip(player.deck, data.get("deck_uses", ())):
        card.uses = uses
    for card, memory in zip(player.hand, data.get("hand_uses_memory", ())):
        card.uses_memory = memory
    for card, memory in zip(player.deck, data.get("deck_uses_memory", ())):
        card.uses_memory = memory
    return player
