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

from ...logic.flow.training import TRAIN_LENGTH
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
    # The score alone never says what it is a race TO — and the target is per-run now (derived from the
    # deck this game dealt), so it cannot be learned once and remembered. Hovering the score answers it.
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
    compact: bool = False,
    short_names: bool = False,
) -> Table:
    # The Wu behind each initiative: this duelist's own buffs plus the opponent's debuffs, which is
    # why a card in your bracket may be sitting in their hand.
    player_sources, bot_sources = initiative_sources(player, bot)

    # Columns size to their content, so a short name leaves no trailing gap. TWO flex columns bracket
    # the training bar and split the slack evenly, which centres the bar between the name and Deck; a
    # single flex on one side dumps every spare cell into one hole beside it.
    grid = Table.grid(expand=True, padding=(0, 1))
    grid.add_column(no_wrap=True)  # Player n
    grid.add_column(no_wrap=True)  # affiliation icon + name (stats)
    grid.add_column(ratio=1, min_width=3)  # flex — half the slack, left of the bar
    grid.add_column(no_wrap=True)  # training bar
    grid.add_column(ratio=1, min_width=3)  # flex — the other half, right of the bar
    grid.add_column(justify="right", no_wrap=True)  # deck
    grid.add_column(width=4)  # gap between
    grid.add_column(justify="right", no_wrap=True)  # initiative
    # Abbreviated where the row cannot afford words. A phone upright reports about 60 columns, and
    # "Player 1:", "Training:", "Deck:" and "Initiative:" spend 34 of them on labels alone — the
    # values then truncate to nothing, which is the one thing a label must never cost.
    player_label, deck_label, init_label = (
        ("P", "Dk", "Init") if compact else ("Player ", "Deck", "Initiative")
    )
    rows = (
        (f"{player_label}1", player, init_player, player_sources),
        (f"{player_label}2", bot, init_bot, bot_sources),
    )
    for label, duelist, init, sources in rows:
        char = duelist.character
        name = Text(f"{affiliation_icon(char)} ")
        name.append(display_name(char.name, upper=True, short=short_names), style="bold")
        name.append(f" ({char_stats(char)})", style="dim")  # stats in brackets, next to the name
        # The two rows share one Static, so a widget-level tooltip could not tell them apart — the
        # bonuses ride on this cell's own span instead (see TooltipStatic). Always tagged, even with
        # nothing applied, so a hover that shows nothing means the cursor missed, not that the
        # duelist is unbuffed.
        bonuses = [card.power.initiative_bonus for card in sources]
        initiative_cell = labelled(init_label, str(init))
        initiative_cell.stylize(Style(meta={"tooltip": bonus_tooltip(bonuses)}))
        grid.add_row(
            Text(f"{label}:", style="dim"),
            name,
            Text(""),  # flex spacer
            _training_cell(duelist, compact=compact),
            Text(""),  # flex spacer
            labelled(deck_label, str(len(duelist.deck))),
            Text(""),  # gap before Initiative
            initiative_cell,
        )
    return grid


def _training_cell(duelist: Player, *, compact: bool = False) -> Text:
    """A duelist's training bar (see ``logic.training``). A boss is at the stat cap and *cannot*
    train — it reads MASTER, centred in a dashed ruler as wide as the bar, and its tooltip is
    ``-/-``, not a full bar.

    Both rows start with the same ``Training:`` prefix in a left-justified column, so their labels line
    up under each other; a spacer column holds them clear of the name."""
    cell = Text("Train: " if compact else "Training: ", style="dim")
    if duelist.character.tier == "boss":
        # Measured off the real bar, percent included — that whole span is what the eye centres
        # against, and a hand-derived segment count leaves MASTER sitting left of it.
        width = cell_len(render_bar(0.0, TRAIN_LENGTH, segments=not compact))
        word = " MASTER "
        dashes = (width - len(word)) // 2  # the same run both sides: symmetry beats exact width
        cell.append("-" * dashes + word + "-" * dashes)
        cell.stylize(Style(meta={"tooltip": "-/-"}))
        return cell
    cell.append(render_bar(duelist.training / TRAIN_LENGTH, TRAIN_LENGTH, segments=not compact))
    cell.stylize(Style(meta={"tooltip": f"{duelist.training}/{TRAIN_LENGTH}"}))
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
    # Escape is NOT listed. It is on the footer, where every screen's escape is, and a panel of things
    # to *do* in the temple is not where "leave the temple" belongs. Nine actions fill the three columns
    # exactly; a tenth entry left one hanging alone on a fourth row.
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
    # Expand to the panel and split it into three equal columns, so the actions spread across the
    # width instead of huddling in a natural-width block in the middle. Each entry is centred in its
    # own column, which keeps the block balanced left-to-right at any panel width.
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
        cell.append(f"{key}. {rest}", style="dim")  # greyed out — you can't take this action now
    # Every action is tagged, so hovering a live one confirms what it does and a greyed one says why
    # it is out of reach (see TooltipStatic). Silence means the cursor missed the text.
    meta: dict[str, str] = {"tooltip": reason or _ACTION_HELP.get(key, rest)}
    # A live action is also *clickable*, running the same screen action its number key does. The
    # panel reads as a list of shortcuts, but a phone has no number row — without this the nine
    # actions are unreachable on a touch screen. A blocked one stays inert, as pressing its key would.
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
        # Built as styled Text (not markup) so the element colour renders reliably in a Static:
        # dim list number, bright element-coloured Wu name, plain stats + type glyph.
        row = Text()
        row.append(f"{index}. ", style="dim")
        row.append(name, style=f"bold {colour}")
        row.append(f"  {stats}  {icon}")
        # The wear count rides on the row's own span (the panels share one Static — see the state
        # grid's tooltip note above), so hovering any Wu answers "how worn is it".
        row.stylize(Style(meta={"tooltip": f"Used: {card.uses}"}))
        rows.append(row)
    return rows


# The order a temple hand is shown in — by slot, so an assembling Mala Mala Jong set reads down the
# body head-to-boots and a missing part is a visible gap. Wudai leads (it is always held), item trails.
_SLOT_ORDER = ("wudai", "head", "torso", "amulet", "arms", "boots", "item")


def _by_slot(card: Card) -> tuple[int, bool, str]:
    """Sort key: the slot's place in the body, then the Wu's name to break ties within a slot.

    Within the wudai slot the elemental dragon weapons always rank above the metal one (the Shimo
    Staff) — metal is the tax element, favoured on no arena, so the dragons read first."""
    place = _SLOT_ORDER.index(card.type) if card.type in _SLOT_ORDER else len(_SLOT_ORDER)
    metal_wudai = card.type == "wudai" and card.element == "metal"
    return (place, metal_wudai, card.name)


def hands_lines(hand_a: list[Card], hand_b: list[Card]) -> tuple[list[Text], list[Text]]:
    """Format both hands with *shared* name and per-column widths, so the two panels come out
    the same size and every name / ``/`` separator / icon lines up down and across the columns.

    Each hand is shown slot-ordered (:data:`_SLOT_ORDER`), not draw-ordered — so the parts of a Jong
    set line up in body order and a gap in the set is plain to see."""
    hand_a, hand_b = sorted(hand_a, key=_by_slot), sorted(hand_b, key=_by_slot)
    both = hand_a + hand_b
    name_width = max((len(card.name) for card in both), default=0)
    col_width = {
        key: max((len(stat_str(card.stats[key])) for card in both), default=1) for key in STAT_ORDER
    }
    return _rows(hand_a, name_width, col_width), _rows(hand_b, name_width, col_width)


def _hand_panel(character_name: str, rows: list[Text]) -> BoxedPanel:
    # Always the short form — two of these titles sit side by side, so the panel has never had room
    # for a full name at any width. Through `display_name` rather than a bare split on the space:
    # the split turned "Le Mime" into "LE'S HAND", which is not a name and not an abbreviation.
    title = f"{display_name(character_name, upper=True, short=True)}'S HAND"
    # All rows in one widget so the panel centres them as a block (rows stay left-aligned within
    # it) — a TooltipStatic, so each row's own wear tooltip answers on hover (see _rows above).
    return BoxedPanel(TooltipStatic(Text("\n").join(rows), classes="hand-block"), title=title)
