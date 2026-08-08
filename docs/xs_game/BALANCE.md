# Xiaolin Showdown — balance, current state

**What's true today.** For the sweeps, the dead ends, and the owner's rulings behind these numbers,
see [`docs/design/BALANCE-HISTORY.md`](../design/BALANCE-HISTORY.md) (local-only) — this file states
outcomes, that one explains why.
Disagree about a number, re-run the harness. Disagree about a design decision, read the history.

## The harness

```bash
./.venv/Scripts/python.exe scripts/balance.py . 400
XS_BOSS=Wuya ./.venv/Scripts/python.exe scripts/balance.py . 400
```

`scripts/balance.py` is the main harness — a tracked dev script alongside the project's other
generators (`scripts/build_cards.py`, `scripts/generate_card_ids.py`, ...).
`scripts/train_sim.py` sits beside it, one-off harness for the training-bar sweep (`python
scripts/train_sim.py [runs]`).

Every `XS_*` env var referenced in `BALANCE-HISTORY.md` is a real override `balance.py` reads —
`XS_BOSS`, `XS_CARD`/`XS_CARDS`, `XS_SEED_COUNTERS`, `XS_PILE`, and the rest.

## Current boss ladder

n=400 each, `balance.py`, measured 2026-08-08 (commit `2c06a5e`) — re-checked after a pass of
bugfixes to `choose_background` and temple AI's initiative reads; both moved nothing outside
normal sampling noise for this n, so the ladder stands unchanged:

| tier        | player win | showdowns/run |
| ----------- | ---------- | ------------- |
| Easy        | **90.8%**  | 14.5          |
| Hard        | **47.2%**  | 13.8          |
| Hannibal    | **16.2%**  | 8.3           |
| Wuya        | **10.2%**  | 9.2           |
| Chase       | **5.0%**   | 7.5           |
| Jack Spicer | **21.2%**  | 8.8           |

Order: Hannibal > Wuya > Chase, all above the hard tier's own difficulty — intended, "3 distinct
bosses that all are hard to kill and a ladder for us to know about." Do not re-tune chasing tighter
separation between them. **Jack sits apart by design** ("he can be the weakest boss") and is
currently the high outlier, unretuned this pass — see [games/xiaolin_showdown/README.md](../../games/xiaolin_showdown/README.md#beyond-the-original) for his roster, or `docs/design/BOSSES.md` (local-only) for the full mechanic-by-mechanic history.

**Keep this table current.** Any commit that changes a boss's balance should re-measure and update
this table in the same commit — it went stale for two weeks once already.

## Live knobs

Every `mechanic_config` row, what it does, one per key: **[`KNOBS.html`](KNOBS.html)** — sortable,
searchable, regenerated from the DB with `python scripts/generate_knobs_page.py`. Not a markdown
table here on purpose: a 29-row, 4-column table is a pain to hand-align and worse to keep sorted.

## Not DB-backed, still live and worth knowing

Marked **[Settings]** where the value is a real `XiaolinSettings` field (`logic/config/settings.py`)
a player can change on the Settings screen — everything else is a code constant only.

- **`POINT_SHARE = 0.3`** — the ratio that derives the _default_ win target; the target itself
  (`point_limit`) **[Settings]**, so a player can override the derived value directly.
- **`prize_threshold = 7`** **[Settings]** — the stat bar a decisive-blow prize claim must clear;
  `N = threshold + 1`.
- **Pile size**: easy/hard 40, boss 30 (`_PILE_SIZE`) — code constant, not a setting; derives the
  _default_ deck size (`max_deck_size` **[Settings]**, overridable directly). The boss stays short
  and swingier on purpose.
- **Deal weights** `base=1, points=2, duel=1` (`_DealWeights`, `flow/setup.py`) — code constant, not
  a setting. Points lead because reaching the target is the harder constraint.
- **Per-boss deal scenarios** (`_SCENARIOS`, `flow/setup.py`) — code constant, not a setting; only
  reachable for a chosen boss. Wuya `points=+4`; Hannibal `counter=+14`; Chase `counter=-8` —
  `counter` biases how often the player is dealt an actual answer to that boss (positive) or starves
  it out of the deck (negative).
- **`empty_draw_limit = 1`** **[Settings]** (the mercy rule), clamped to `max_wager` — a duelist with
  nothing to field is dealt back in, never dealt more than they could have staked.
- **`deposit_limit`** — derived from `actions_per_turn_player`/`_bot` **[Settings]**, not itself a
  setting: a temple turn may spend at most half its actions depositing, rounded up.
- **Wager widening** has no numeric margin any more, settings or otherwise — `choose_wager` widens on
  a plain sign-of-margin rule (`ahead = [width for width in options if margin(width) > 0]`).

Other live `XiaolinSettings` fields not covered above: hand sizes, `max_wager`, `random_background`,
`wear_limit`, training length, `stat_cap`, `actions_per_turn_*`, `loss_fill_*` — see the Settings
screen itself, or `logic/config/settings.py`, for the full field list and defaults.

## What this file does not cover

The circulation cascade (prize routes, the Early Bird, the lost pile) is designed and measured in
[`CIRCULATION.md`](CIRCULATION.md), not repeated here. Card-by-card pricing (`bank%` / `fielded%`)
is a `docs/design/BALANCE-HISTORY.md` §16-17 finding, not a live table — re-run `XS_CARDS=1` for
current numbers.
