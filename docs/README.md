# docs

Player-facing game documentation, contributor-facing design notes, and the project's own planning
docs, in one folder, kept apart by what each is *for*.

Three files sit at the top because they answer three different questions:

| file | the question it answers |
|---|---|
| **`PLAN.md`** | what is **coming**. Open work only — nothing shipped, ever. A plan that records history is a changelog wearing a plan's name. |
| **`HANDOFF.md`** | where the project **is**, and how to run it. |
| **`CLAUDE.md`** | the **invariants** — the rules that were each got wrong by someone trying, written down so the next person does not. |

Everything else is grouped by what it is *for*:

| folder | what lives there |
|---|---|
| **`xs_game/`** | **game documentation** — how Xiaolin Showdown plays, not how it's coded. `BALANCE.md` (current numbers), `CIRCULATION.md` (how a Wu changes hands), `BOSSES.md` (the boss roster), `JONG.md` (Mala Mala Jong), `CARDS.html`/`KNOBS.html` (every card and live knob, generated from the DB — regenerate with `python scripts/generate_cards_page.py` / `generate_knobs_page.py`, never hand-edit). What every Wu power does is `logic/mechanics/powers.py` (`RULES`), not a doc. |
| **`design/`** | how the *code* works and why it was built that way, for a contributor rather than a player — `SCREEN_TEMPLATE.md`, `LORE_TAB.md`, `VOICE.md`, and `BALANCE-HISTORY.md` (the measurement history and dead ends behind `xs_game/BALANCE.md`'s current numbers). |
| **`notes/`** | working material that is not a document — the card planning spreadsheet, deferred lore drafts. |

The lore itself — the author's own reconciled universe, **not show canon** — lives with the game, not
here: `games/xiaolin_showdown/lore/`, five shipped chapters, tracked in git like the rest of the code.

## Running the harness

```bash
python scripts/balance.py . 150      # 150 runs a tier, both duelists played by the bot's brain
```

Every balance claim in this project's history came out of that script. A number that did not is a
guess.

## ⚠ This folder is gitignored — except `assets/` and `xs_game/`

`docs/` **does not survive a clone**, outside those two carved-out, tracked folders. `design/` stays
untracked and local, same as `PLAN.md`/`HANDOFF.md` — it is a contributor's-eye view of the code and
an engineering diary (measurement history, dead ends, process notes), not player-facing documentation
and cannot be rebuilt from anything. This is the top item in `PLAN.md` for a reason: decide to track
it, or accept that it is local-only and back it up yourself.
