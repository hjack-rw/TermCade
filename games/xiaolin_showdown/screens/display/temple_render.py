"""Render helpers for TempleScreen's three panels — pure Rich construction, called once each from
`compose`, no Screen lifecycle of their own.

Kept apart from :mod:`format` (whose helpers are shared across nearly every screen) because these
are sized and laid out for exactly the panels `TempleScreen.compose` builds, nothing else.
"""

from __future__ import annotations

from collections.abc import Mapping

from rich.cells import cell_len
from rich.style import Style
from rich.table import Table
from rich.text import Text
from termcade.ui.widgets import BoxedPanel, TooltipStatic, render_bar

from ...logic.config.settings import XiaolinSettings
from ...logic.flow.training import can_train
from ...logic.mechanics.scoring import initiative_sources
from ...logic.schema.models import Card, Player
from ...logic.schema.state import XiaolinState
from .format import (
    COLORS,
    ICONS,
    STAT_ORDER,
    affiliation_icon,
    bonus_tooltip,
    char_stats,
    display_name,
    display_type,
    labelled,
    stat_str,
)


def _summary_line(
    player: Player, bot: Player, state: XiaolinState, *, target: int, actions_left: int
) -> Text:
    line = Text()  # centred by the #summary `text-align`, not Rich justify (which uses natural width)
    # target is per-run (derived from the dealt deck), so it's surfaced via tooltip, not a static label.
    points = labelled("Points", f"{player.points}/{bot.points}")
    points.stylize(Style(meta={"tooltip": f"Earn {target} to win!"}))
    line.append_text(labelled("Actions Left", str(actions_left)))
    line.append("       ")
    line.append_text(labelled("Remaining Wu", str(len(state.card_deck))))
    line.append("       ")
    line.append_text(points)
    return line


def _state_grid(
    player: Player,
    bot: Player,
    init_player: int,
    init_bot: int,
    *,
    train_length_player: int,
    train_length_bot: int,
    settings: XiaolinSettings,
    compact: bool = False,
    short_names: bool = False,
    player_training_override: int | None = None,
) -> Table:
    # initiative_sources returns this duelist's own buffs plus the opponent's debuffs — a card in your
    # bracket may be sitting in their hand.
    player_sources, bot_sources = initiative_sources(player, bot)

    # TWO flex columns (not one) bracket the training bar and split the slack evenly, centring the bar
    # between name and Deck; a single flex column would dump all spare width into one hole beside it.
    grid = Table.grid(expand=True, padding=(0, 1))
    grid.add_column(no_wrap=True)  # Player n
    grid.add_column(no_wrap=True)  # affiliation icon + name (stats)
    grid.add_column(ratio=1, min_width=3)  # flex — half the slack, left of the bar
    grid.add_column(no_wrap=True)  # training bar
    grid.add_column(ratio=1, min_width=3)  # flex — the other half, right of the bar
    grid.add_column(justify="right", no_wrap=True)  # deck
    grid.add_column(width=4)  # gap between
    grid.add_column(justify="right", no_wrap=True)  # initiative
    # Abbreviated when the row is too narrow: a phone's ~60 columns can't spare 34 for full labels
    # without truncating the values.
    player_label, deck_label, init_label = (
        ("P", "Dk", "Init") if compact else ("Player ", "Deck", "Initiative")
    )
    rows = (
        (f"{player_label}1", player, init_player, player_sources, train_length_player, player_training_override),
        (f"{player_label}2", bot, init_bot, bot_sources, train_length_bot, None),
    )
    for label, duelist, init, sources, train_length, training_override in rows:
        char = duelist.character
        name = Text(f"{affiliation_icon(char)} ")
        name.append(display_name(char.name, upper=True, short=short_names), style="bold")
        name.append(f" ({char_stats(char)})", style="dim")
        # The two rows share one Static, so a widget-level tooltip can't tell them apart — the bonuses
        # ride on this cell's own span instead (see TooltipStatic). Always tagged, so a silent hover
        # means the cursor missed, never that the duelist is unbuffed.
        bonuses = [card.power.initiative_bonus for card in sources]
        initiative_cell = labelled(init_label, str(init))
        initiative_cell.stylize(Style(meta={"tooltip": bonus_tooltip(bonuses)}))
        grid.add_row(
            Text(f"{label}:", style="dim"),
            name,
            Text(""),  # flex spacer
            _training_cell(duelist, train_length, settings, compact=compact, shown_training=training_override),
            Text(""),  # flex spacer
            labelled(deck_label, str(len(duelist.deck))),
            Text(""),  # gap before Initiative
            initiative_cell,
        )
    return grid


def _training_cell(
    duelist: Player,
    train_length: int,
    settings: XiaolinSettings,
    *,
    compact: bool = False,
    shown_training: int | None = None,
) -> Text:
    """A duelist's training bar. Every stat at the cap and it *cannot* train: it reads MASTER,
    centred in a dashed ruler as wide as the bar, tooltip ``-/-``. A boss is usually there by
    design, but the cap is a player setting now — read the real state, not the tier.

    ``shown_training`` overrides the displayed value without touching ``duelist.training`` itself —
    the temple's mid-fill tween uses this to animate a frame that was never the real, persisted
    value."""
    cell = Text("Train: " if compact else "Training: ", style="dim")
    if not can_train(duelist, settings):
        # Measured off the real bar (not a hand-derived segment count), so MASTER centres against the
        # actual rendered width.
        width = cell_len(render_bar(0.0, train_length, segments=not compact))
        word = " MASTER "
        dashes = (width - len(word)) // 2  # the same run both sides: symmetry beats exact width
        cell.append("-" * dashes + word + "-" * dashes)
        cell.stylize(Style(meta={"tooltip": "-/-"}))
        return cell
    training = duelist.training if shown_training is None else shown_training
    cell.append(render_bar(training / train_length, train_length, segments=not compact))
    cell.stylize(Style(meta={"tooltip": f"{training}/{train_length}"}))
    return cell


# Temple actions, laid out row-major into three columns that fill the panel (see _actions_grid).
_ACTIONS = [
    '1. "Gong Yi Tanpai!"',
    "2. Draw a Card",
    "3. Deposit a Card",
    "4. Use a Power",
    "5. Train a Stat",
    "6. Look Things Up",
    "7. Game Log",
    "8. Game Rules",
    "9. Save game",
    # Escape is on the footer, not listed here. Nine actions fill the three columns exactly; a tenth
    # would leave one hanging alone on a fourth row.
]

# Hover text for an action that *is* available; a blocked one shows why instead (see _action_cell).
_ACTION_HELP = {
    "1": "Duel for the next Wu on the pile.",
    "2": "Take a Wu from your personal deck.",
    "3": "Cash a Wu from your hand for points.",
    "4": "Spend a Wu for its power.",
    "5": "Fill your training bar.",
    "6": "Inspect either hand or duelist.",
    "7": "Everything that has happened so far.",
    "8": "Rulebook for the game.",
    "9": "Save this run to a slot.",
}


def _actions_grid(blocked: dict[str, str | None], action_by_key: Mapping[str, str]) -> Table:
    # Three equal ratio columns, each entry centred within its own — keeps the block balanced
    # left-to-right at any panel width, instead of huddling as a natural-width block in the middle.
    grid = Table.grid(expand=True, padding=(1, 2))
    for _ in range(3):
        grid.add_column(ratio=1, justify="center")
    for start in range(0, len(_ACTIONS), 3):
        cells: list[Text] = [
            _action_cell(entry, blocked, action_by_key) for entry in _ACTIONS[start : start + 3]
        ]
        cells += [Text("")] * (3 - len(cells))
        grid.add_row(*cells)
    return grid


def _action_cell(entry: str, blocked: dict[str, str | None], action_by_key: Mapping[str, str]) -> Text:
    key, _, rest = entry.partition(". ")
    reason = blocked.get(key)
    cell = Text()
    if reason is None:
        cell.append(f"{key}. ", style="bold")
        cell.append(rest)
    else:
        cell.append(f"{key}. {rest}", style="dim")
    # Every action is tagged, so hovering a live one confirms what it does and a greyed one says why
    # it is out of reach (see TooltipStatic). Silence means the cursor missed the text.
    meta: dict[str, str] = {"tooltip": reason or _ACTION_HELP.get(key, rest)}
    # Clickable, running the same screen action its number key does — a phone has no number row, so
    # without this the actions are unreachable on a touch screen.
    if reason is None and key in action_by_key:
        meta["@click"] = f"screen.{action_by_key[key]}()"
    cell.stylize(Style(meta=meta))
    return cell


def _rows(cards: list[Card], name_width: int, col_width: dict[str, int]) -> list[Text]:
    rows = []
    for index, card in enumerate(cards, 1):
        colour = COLORS.get(card.element, "white")
        icon = ICONS.get(display_type(card), "")
        name = card.name.rjust(name_width)
        stats = "/".join(stat_str(card.stats[key]).rjust(col_width[key]) for key in STAT_ORDER)
        # Styled Text, not markup, so the element colour renders reliably in a Static.
        row = Text()
        row.append(f"{index}. ", style="dim")
        row.append(name, style=f"bold {colour}")
        row.append(f"  {stats}  {icon}")
        # Rides on the row's own span (the panels share one Static, so a widget-level tooltip
        # wouldn't distinguish rows — see the state grid's tooltip note above).
        row.stylize(Style(meta={"tooltip": f"Used: {card.uses}"}))
        rows.append(row)
    return rows


# Body-slot display order for a hand: wudai first (always held), item last.
_SLOT_ORDER = ("wudai", "head", "torso", "amulet", "arms", "boots", "item")


def _by_slot(card: Card) -> tuple[int, bool, str]:
    """Sort key: the slot's place in the body, then the Wu's name to break ties within a slot.
    Within the wudai slot, elemental dragon weapons rank above the metal one."""
    place = _SLOT_ORDER.index(card.type) if card.type in _SLOT_ORDER else len(_SLOT_ORDER)
    metal_wudai = card.type == "wudai" and card.element == "metal"
    return (place, metal_wudai, card.name)


def hands_lines(hand_a: list[Card], hand_b: list[Card]) -> tuple[list[Text], list[Text]]:
    """Format both hands with *shared* name and per-column widths, so the two panels come out
    the same size and every name / ``/`` separator / icon lines up down and across the columns.

    Each hand is shown slot-ordered (:data:`_SLOT_ORDER`), not draw-ordered."""
    hand_a, hand_b = sorted(hand_a, key=_by_slot), sorted(hand_b, key=_by_slot)
    both = hand_a + hand_b
    name_width = max((len(card.name) for card in both), default=0)
    col_width = {
        key: max((len(stat_str(card.stats[key])) for card in both), default=1) for key in STAT_ORDER
    }
    return _rows(hand_a, name_width, col_width), _rows(hand_b, name_width, col_width)


def _hand_panel(character_name: str, rows: list[Text]) -> BoxedPanel:
    # Through `display_name`, not a bare split on the space — a plain split turned "Le Mime" into
    # "LE'S HAND".
    title = f"{display_name(character_name, upper=True, short=True)}'S HAND"
    # All rows in one widget so the panel centres them as a block (rows stay left-aligned within
    # it) — a TooltipStatic, so each row's own wear tooltip answers on hover (see _rows above).
    return BoxedPanel(TooltipStatic(Text("\n").join(rows), classes="hand-block"), title=title)
