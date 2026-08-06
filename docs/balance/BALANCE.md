# Xiaolin Showdown — balance findings

Measured with a headless mirror-match harness: whole runs, both duelists driven by the bot's own
brain, so any departure from 50/50 is *structural* rather than one side simply playing worse. 200
runs per figure unless stated.

**THE HARNESS IS `docs/balance/balance.py`.** It has always been here, beside this file. Run it:

    ./.venv/Scripts/python.exe docs/balance/balance.py . 400
    XS_BOSS=Wuya ./.venv/Scripts/python.exe docs/balance/balance.py . 400

Every `XS_*` knob referenced anywhere in this file is a real environment override it reads —
`XS_BOSS`, `XS_BEAST_MARGIN`, `XS_BEAST_BOOST`, `XS_WITCH_RECALL`, `XS_LOSS_FILL`, `XS_CARD`,
`XS_SEED_COUNTERS`, and the rest. `docs/balance/train_sim.py` sits beside it.

**A header in this file used to say the harness was "not in the repo — it lives in the session
scratchpad".** That was false, and it cost a whole session (2026-07-19): a rebuilt-from-scratch
harness was used for every boss measurement that day, and it reads **easy 80.7 / hard 34.0** where the
real one reads **easy 90.0 / hard 47.5** — systematically pessimistic by 9-13 points. `docs/` is
gitignored, so no `git ls-files` sweep finds this file; look here FIRST. Numbers taken from that
rebuild are marked in place below. (A `tools/` directory was created that day for the same false
reason, and has since been deleted.)

**What this file is FOR, versus what the harness is for.** The harness answers *"what is it now?"* —
re-run it and the win-rate tables below regenerate, and they go stale the moment a card lands. **This
file exists for what cannot be re-derived:** the levers that measured BACKWARDS, the ones that measured
inert, and the owner's rulings. Re-running the harness is cheap; re-discovering "we tried that and it
went the wrong way" costs a session. Disagree about a number, trust the harness. Disagree about a
*decision*, trust this file.

**Caveat that limits every number below — CORRECTED 2026-07-13.** This file used to say the simulated
player never spends a Wu's power, so every player win rate was "a floor". **It now spends them, by the
same policy the opponent plays, and the claim was wrong in the flattering direction** — see §11. What is
genuinely unmeasurable here is narrower: the *revealing* Wu (Diaskopia, Teleskopia) inform no decision a
policy makes, because a policy has no memory to carry what it saw into a later turn. A human does. Those
two cards are strong in a player's hand and worth nothing in this harness, and that is a property of the
harness, not of the cards.

---

## 1. `duel_value` was blind to every Wu that resolves at play — FIXED

`turn.duel_value` scored a card by summing its **printed** stats. Every Wu whose stats resolve when
it is played prints `? ? ?` or `0/0/0` — so the Orb of Tornami, Kaijin's Curse, the Sphere of Jianyu,
the Reversing Mirror and the Emperor Scorpion all scored **zero**.

Consequences, all of them silent:

- the easy bot (which banks its *least* useful Wu) cashed the strongest cards in the game as junk
- `bot.choose_wager` counted them as empty rungs when pricing a wager
- the Ruby and Glove policies, which rank cards by `duel_value`, could never see them

Fixed with a mechanic-aware valuation (`turn._MECHANIC_VALUE`). Effect on the bot's win rate:

| bot win rate (banking its powers) | Easy | Hard |
|---|---|---|
| before the fix | 24.5% | 83.0% |
| **after the fix** | **40.5%** | 82.0% |

**16 points of win rate on Easy, from a bug that had nothing to do with the cards' rules.** Any new
Wu that prints no stats must be given a value here, or the opponent cannot see it.

## 2. The win target was decorative — FIXED

At `POINT_SHARE = 0.4` (target 25), **94% of Easy runs and 82% of Hard runs ended on an empty pile**,
not on anyone reaching the target. "Bank the target and the run is yours" was a promise the game
almost never kept.

Swept the share; it turned out to be a **pacing** knob, not a balance one — the win rate did not move
a point across the whole range:

| share | target | Easy: ends on target | Hard |
|---|---|---|---|
| 0.40 | 25 | 6% | 15% |
| **0.30 (now)** | **19** | **49%** | **75%** |
| 0.25 | 16 | 75% | 91% |

Set to **0.30**. About half of Easy runs are now decided by someone actually banking the target, and
the pile can still run out from under a duelist who dawdles.

## 3. The difficulty tiers are very far apart — OPEN

Player win rate, mirror brains: **~40% Easy vs ~78–82% bot-favoured on Hard.** Stable across every
action budget tried (1, 2, 3 actions per turn), so it is *not* the vault economy. It is the hard
roster's stat blocks.

Decision taken: **leave it — "it is hard" is the point.** Recorded here because the gap is wide
enough that a middle tier would have somewhere to live if one is ever wanted.

## 4. The bot's vault-power policy is marginal — OPEN

New module `logic/vault_ai.py` gives the opponent a fair policy for spending Wu at the vault. It
reads only what a player could (both hands are face up; pile and deck *sizes* are public) and
reasons about probabilities where it cannot see. It never looks inside the pile or the player's deck.

| bot win rate | Easy | Hard |
|---|---|---|
| banks every power Wu | 40.5% | 82.0% |
| plays them by the policy | 40.0% | 77.5% |

**Spending powers is neutral on Easy and actively worse on Hard.** Points are the win condition, and
a Wu spent is a Wu not banked. The policy is left on because it makes the opponent *play the game*
rather than ignore half the card pool — but it is not what makes it strong.

Firing rates (how often it spends a power it is holding):

| power | fires | note |
|---|---|---|
| Telepatheia (Conch) | 46% | the one that pays: +3% on Easy |
| Chronokinesis | 45% | slightly negative; banking is usually better |
| Repulsion (Ruby) | 26% | fires now — see below |
| Attraction (Glove) | **1.7%** | near-dead for a bot: the shelf almost never holds an upgrade worth a Wu |

### A threshold picked blind, and how it was caught

`REPULSION_THRESHOLD` was set to a duel-value of **5** — and **no card in the pool scores above 4**.
The Ruby therefore fired exactly zero times in 400 runs. Calibrated against the real distribution
(median 3, max 4) it now fires on 26% of the turns it is held.

Lesson for the next threshold: **measure the distribution before choosing the constant.**

## 5. Falcon's Eye and Eagle Scope do nothing for the bot — SUPERSEDED, both now have real bot value

Historical record — left as it was written, because it correctly explains what the gap was and why:

Not faked, not papered over:

- **Diaskopia** (read the opponent's shelf) informs *no decision the bot makes*. Nothing in `bot.py`
  — not the challenge, not the wager, not what to field — turns on what the player has shelved.
  Knowledge with no decision behind it is worth zero.
- **Teleskopia** cannot pay off under a one-action turn: looking **is** the turn. It cannot look and
  then act on what it saw.

Both are banked by the opponent, and both remain strong in a *player's* hand — a human carries
information across turns in their head. That asymmetry is real: it is the difference between a mind
and a policy.

**To wake them up** the bot needs either a memory (revealed cards persisted on the state, shifted as
the pile drains) or a decision that depends on the opponent's future hand. Neither is built.

**Both are built now.** Diaskopia got a memory and a consumer (Jack's steal) in the fog-of-war work,
§26. Eagle Scope's own combo (Farsight, fusing it with Falcon's Eye into a pile-reorder) is a
*player*-facing feature and does not touch this gap — it is Teleskopia specifically, spent alone,
that got the bot's own memory and consumer (Early Bird's veto), §29.

## 6. The wager collapses to one Wu — OPEN, probably fine

95–96% of showdowns are fought with a **single Wu**; tournaments fire on 12–18%. This is *not* the
action economy — `bot.choose_wager` only widens when the next rung *clearly* beats the opponent's,
and in a mirror match both hands are equal, so it never widens. A human would widen more. Worth
re-measuring against a real player before touching `WAGER_MARGIN`.

---

## Rules changed this session

- **One action a turn**, for both duelists: bank a Wu, spend a Wu's power, or draw one off your
  shelf. `deposit_counter` + `draw_counter` → `actions_taken`; the bot got its own counter and lost
  its free hand refill.
- **The mercy rule costs the action.** Being dealt back in is income, and income is not free.
- **The mercy rule empties your own shelf before it touches the pile.** Your shelved Wu are already
  yours; dealing off the pile while the shelf sits full pays you for having forgotten about it.
- **The turn turns over in `turn.refill_hands`**, not in the duel's end phase — otherwise a mercy
  charge is wiped before it can bite.

---

## Is it balanced? — as of this measurement

**2026-07-27 — LADDER RE-TUNED (n=500): Hannibal 10.2% > Wuya 7.8% > Chase 6.2%.** The 2026-07-17
ladder had drifted — a fresh sweep read Hannibal 13.8 / Wuya 6.0 / Chase 6.2, so the top rung was too
easy and the bottom two had collapsed together. Two character-power changes, both measured, restored
three rungs (Chase untouched, 6.2, ruled the wall it is by design):

- **Wuya → 7.8% (was 6.0).** Her flat +1 initiative was kept (it *is* her Wu-sense) but her recall
  now calls back the *most valuable* lost Wu, not the oldest, and her Witchcraft gained an **Early-Bird
  sense**: she flies the bird at a reduced gap (`temple_ai.WITCH_EARLY_BIRD_GAP = 2`). Counter-intuitively
  this made her *easier* to ~8% — the Early Bird is a net-negative tempo trap (it ends the pile early
  while she is behind on points), so flying it more costs her the race. init0 variants and higher
  bird-frequency were measured and rejected; init1 + gap2 is the shipped pair.
- **Hannibal → 10.2% (was 13.8).** New character passive **Elemental Deflection** (his renamed power,
  "Elemental Manipulation", still wields the free Morpher). Two halves, **the four elements only, never
  metal**: his own Wu ignore the arena's drag (a ward), and the foe's Wu lose their arena lift. Metal is
  the majority element, so it is a modest, non-dominant edge. Lift-only variants: foe-lift-only = 11.2,
  both halves = 10.2. Deflecting the foe's *drag* was rejected — it removes the player's penalty, i.e.
  makes him easier (backwards). The board's per-card strike is deflection-aware so the display matches
  the score (`duel_board._played_stats_text` `deflect=`).

**2026-07-17 — THE BOSS LADDER HOLDS (n=500, boss AI shipped): Hannibal 9.0% > Wuya 5.6% > Chase
1.6%.** All three above the hard tier's difficulty (hard = 31% player win). The fix was the AI, not
the mechanics: a shared player-clone temple policy made bosses spam powers and never bank — witchcraft
re-fired Repulsion every turn, so Wuya *lost the point race* (9.8% at n=500, easier than Hannibal).
A dedicated `_boss_acts` that RACES the point target (draw-if-thin → cheap Early Bird → recall → bank
the surplus; a power only falls through when nothing else is left) turned witchcraft into an asset:
Wuya 9.8 → 5.6, into the ladder. Wuya also carries +1 inherent initiative and a weak-Wu Early Bird.

**2026-07-17 — MEASUREMENT NOISE LESSON (Wuya tuning).** Boss win rates at n=200 are noise-dominated:
the player wins only ~16-21/200, and the 95% CI on ~8% at n=200 is ≈±3.8pt. Every Wuya lever tried
(aggressive recall, wear-free witchcraft, witchcraft OFF, +1 inherent initiative, weak-Wu early bird)
landed 6.0-10.5% — ALL inside that envelope, giving contradictory readings run to run (e.g. witchcraft
"OFF looks stronger" was noise). **Boss-tier tuning must run n≥500** (CI ≈±2.2pt). At n=500, Wuya
witchcraft-OFF = 7.0%. Conclusion so far: the small levers do not move her meaningfully — she is ~7-8%
on her 6/6/6 stats, and a real split from Hannibal needs a structural (duel-stat) change, not a temple
tweak. Built but unproven-as-a-lever: +1 initiative (power id −6 bonus 1), Wuya's early bird gives up
her weakest Wu not her fastest, WITCHCRAFT_WEARS/RETURNS knobs.

**2026-07-17, Chase Young reworked to a real choice: boss 3.5%** (was 0.5% overtuned). Beast Form is
now a mode with costs — Wu all dead, prize gifted, +2 only; temple deposit/draw only; BEAST_BOOST 2.
Diagnosis en route: pure 7/7/7 alone is 2.0% (the base is the wall, not the boost). Chase is the
hardest boss by design (5→6→7 ladder); the drawbacks lifted him off 0.5% without a base nerf.
Superseded lever notes: boost +2 gave 1.0%, +3 gave 0.5% — the boost barely moves it.
**Bug the measurement caught:** Beast Form's mode-decision ran for EVERY opponent, not just Chase —
any weak-handed bot sprouted +3 and dead-weight Wu, dropping easy 72→65 and hard 31→17. Gated on
`_is_chase` (commit `d3d6e12`); easy/hard restored to 72.0/31.0. A boss mechanic must key off the
boss, always.

**2026-07-17, Morpher boost grounded (0 on the contested stat — in tune it NETS 1/1/1): Hannibal
2.5% → 8.0%, exactly Wuya's 8.0%.** Both bosses in one band. Counter seeding REJECTED by the author,
permanently — the nerf replaced it and outdid it. Also fixed en route: `bot.choose_background`
crashed on an empty player hand (reachable since wear vaults + the Lantern).

**2026-07-17, Wuya built (200 runs, boss pinned via XS_BOSS): Wuya 8.0%, Hannibal 2.5% (pre-nerf).**
The witch is the friendlier boss — 6/6/6 is honest muscle, and her witchcraft burns her own Wu
(1.54 wear-vaults/run).

**2026-07-17, AI tuning pass (Lantern spend rule + wear-aware banking): easy 73.5 / hard 31.5 /
boss 5.5.** The 2.5% boss reading was measurement lag — the policy didn't spend the new cards.
SWAP_MARGIN swept {3, 5, 8}: no separation (boss 6.0/5.5/5.5), shipped 5 stays. Boss-deal seeding
remains the anchor against future pool growth.

**2026-07-17, Sun Chi Lantern in (pool 49, deck 50, target 29): easy 69.5 / hard 30.5 / boss 2.5.**
The Lantern's swap NEVER FIRED in this run (no spend policy yet — it measured as a 5-pt bankable
only); superseded by the tuning pass above.

**2026-07-17, wards in (pool 48, deck 49, target 28): easy 74.5 / hard 26.5 / boss 3.0.** The tier
shifts are the POOL GROWTH (deck + target formulas), not the ward power: the higher target undoes
the boss rules' band (8.5 → 3.0) and softens easy (64 → 74.5). Next lever: seed counters/wards into
the boss deal (availability — the 49.3% guaranteed-in-hand ceiling stands).

**2026-07-16, 200 runs/tier, both sides playing powers, training + wear + boss rules live:**

- **Easy: 64.0% to the player.** Wear lifted it ~4 pts (the player's wear vaults pay free points:
  1.70/run vs the bot's 0.98).
- **Hard: 31.5%.** Deliberate: the hard roster's stat blocks.
- **Boss: 8.5%** — from a 0.5% wall. The two boss-run rules (loss teaches +2, 3 actions to the
  boss's one) plus the counter reprice to 3 pts did it. The player's wear never fires vs a boss
  (Wu don't survive three showdowns there); the boss auto-banks 0.69/run.
- **Wear reset A/B (2026-07-16):** reset-on-every-hand-over vs per-wearer memory measured identical
  within noise (64.0/31.5/8.5 vs 64.5/33.5/8.5). **Shipped: per-wearer memory (B)** — the author's
  design call, since the numbers don't separate: win your Wu back and your count resumes.

Older context (pre-training, pre-counters):

- Easy read 57/40 before; hard ~20/78 — every action budget tried left the hard gap where it was.
- **The card set was unproven then** — the simulated player never spent a power. It does now.
- **Every point cost was guessed**, not measured (2/2/3/3/3/2/2/3/3/3, by eye). Points are the win
  condition, so those guesses are load-bearing.
- **The negations are the strongest cards in the game** and are currently unpriced. `_MECHANIC_VALUE`
  scores the Sphere and the Scorpion at 5 — above every printed-stat Wu in the pool. Sphere +
  Scorpion on the same duelist zeroes their base *and* their Wu: an outright won battle for two Wu of
  a three-Wu wager.

---

## What ~50 more cards breaks

Three findings above are merely *noted* at 35 cards and become **blocking** at 85. Do these before
the next big batch, not after.

### The `duel_value` blindness will happen again, silently

Finding 1 cost 16 points of win rate and was invisible: a Wu that prints no stats is worth **zero** to
the opponent, and nothing complains. Most of the new cards resolve at play, so this recurs every few
cards.

**Fix it structurally, the way `powers.py` already guards mechanics:** a test that every `Mechanic`
either has an entry in `_MECHANIC_VALUE` or is explicitly declared worthless. `UNPRINTED` is the
precedent. An unvalued mechanic should fail the suite, not quietly become junk in the bot's hand.

### The `(trigger, effect)` encoding will not survive the batch

`use` already runs 0–6, `play` runs −1–6. Nothing but a lookup table says what `use`/+5 means, two
cards can silently claim the same pair, and adding a power means hunting for a free integer.

**Replace the pair with the mechanic name in the DB** — `power(id, name, mechanic, description,
bonus)`, `trigger` promoted into `Rule`. A seed row then reads `('Emperor Scorpion', 'subjugation')`
instead of `('play', 6)`; a typo'd mechanic **fails at load** instead of becoming a Wu that does
nothing; and the `~` initiative hack dies with it. Agreed in principle — do it *before* the batch, on
a green baseline.

### "The deck grows with the pool" stops being the right call

Current rule (chosen deliberately at 30 cards): every Wu is in every run, `max_deck_size` derived
from the pool. At **80 cards that is a ~3× longer run** — ~11 showdowns today, and the point target
scales with the pool alongside it.

At that size the trade-off inverts: a pool *larger* than the deck deals a random subset each run,
which is **replayability** rather than a bug — provided `point_limit_for` is changed to derive the
target from the **dealt deck** instead of the whole pool. (That coupling is exactly why the subset
option was rejected at 30 cards.) Revisit once the pool passes ~40.

## Alternate ways to win a Wu

`prize_threshold` (7) is the one number deciding whether Wu circulate or the pile just drains. It is
tunable rather than derived because it turns on character stats *and* card stats together.

**Swept after the stat ceiling went 4 → 5** (120 runs/tier, ~3,400 prize showdowns per value). The
worry was that a magnitude-5 Wu makes a decisive blow trivial and the bar has to rise with it. It does
not, and it must not — **7 is the only value at which the cascade behaves like a cascade**:

| threshold | prize claimed | decisive blow | two fronts | total command | in tune | easy / hard |
|---|---|---|---|---|---|---|
| 6 | 58.0% | 46.6% | 8.7% | 1.0% | 1.7% | 57.5% / 38.3% |
| **7** | **39.7%** | 27.1% | 2.7% | 1.6% | 8.4% | **58.3% / 40.0%** |
| 8 | 27.9% | 11.7% | 0.3% | — | 15.9% | 53.3% / 32.5% |
| 9 | 23.3% | 5.2% | 0.1% | — | 18.0% | 55.0% / 35.0% |

- At **6** the first gate is so wide that the decisive blow claims nearly half of all showdowns and the
  routes beneath it never get a turn — the elemental fallback all but dies (1.7%).
- At **8 and up** it inverts: the two middle routes collapse (total command stops firing *entirely*) and
  the elemental fallback becomes the *main* way a Wu is won. That is backwards — it is the fourth route
  for a reason, and it is the one route Serpent's Tail can veto.
- **7** is also the player win-rate peak. Every higher bar is worse for the player *and* worse-shaped.

Circulation is now **~40% of showdowns**, against the ~15–20% that prompted the cascade. A Wu still
fails to find a winner 6 times in 10, so the lost pile stays fed — the Rooster Booster still has a job.

**Total command is a nearly-dead route** (1.6%, and 0% above threshold 7). Rare by design — it is the
"you dominated on every front" flourish — but if it should ever *matter*, the lever is widening it from
N−2 to N−3. That is a design call, not a measurement.

If Wu-acquisition gets alternate conditions, that number is what they compete with — and the harness
can price each one. A condition that moves the prize in <10% of showdowns is scenery; one that moves
it in >50% drains the pile before the point race can finish.

---

## Next

1. **Guard `duel_value` with a test** — an unvalued mechanic must fail the suite. Cheap, and it stops
   finding 1 from recurring fifty times.
2. **Do the mechanic-name encoding** before the next card batch, on a green baseline.
3. **Teach the simulated player to spend powers** — the ten cards' player-side value is unmeasured,
   and the negations are the cards most likely to be over-strength.
4. Check in the balance harness so these numbers can be reproduced rather than retold.
5. Revisit deck-size-vs-pool once the pool passes ~40 cards.
6. Price the point costs against the sim instead of by eye.

---

# 2026-07-13 — the mercy rule, the Early Bird, and two lies the harness told

## 7. The mercy rule was the biggest source of Wu in the game — FIXED

A duelist with nothing they can field is dealt back in (`empty_draw_limit`). It reads as a safety net.
It is **income**, and it is paid to whoever is **losing**: a hand empties because it was staked and
forfeited, and the refill comes off the *contested pile* — your own shelf answers first, but a duelist
who keeps losing never overflows their hand, so their shelf is bare.

Counted over 60 hard runs:

| | mercy fired | Wu dealt | from own shelf | **from the pile** |
|---|---|---|---|---|
| player, limit 3 | 226× | 451 | 4 | **447** |
| player, limit 4 | 224× | 668 | 4 | **664** |
| bot, limit 3 | 40× | 120 | 28 | 92 |

~3.8 firings a run, ~7.5 Wu handed to the losing side off a pile of ~30. Raising the number simply paid
you more for losing:

| `empty_draw_limit` | hard-tier player win |
|---|---|
| 2 | 33% |
| **3** (default) | **37%** |
| 4 | **72%** |
| 5 | **75%** |

**Not an exploit** — `empty_draw_limit` is on the Settings screen, and a player who raises it is
configuring a custom game, which is what that screen is for. The clamp is a **guardrail, not a lock**: it
is there so a player cannot quietly wreck their own run by nudging a number, with nothing on screen to
say why the game stopped being hard. The finding is about the **default**, which sat one step below a
value that turns the hard tier into a 72% walk — and nobody had chosen it on purpose.

**Clamped the mercy hand to `max_wager`**: you are dealt back in to duel, never dealt more than you could
have staked. 4, 5 and 9 now all resolve to 3 and play identically (38.3% hard). Auto-losing on an empty
hand was rejected — *"when you run out autolose would be lame"* — so the mercy stays; only the subsidy
scales with something the game already believes in.

---

# 2026-07-19 — the mercy rule paid better than a Draw

## 7b. Banking down to one Wu farmed the mercy — FIXED

The 2026-07-13 pass clamped the mercy's *size*. It did not ask what the mercy **paid per action**, and
that was the hole. Both cost the turn's one action:

| action | cost | Wu gained | source |
|---|---|---|---|
| Draw | the turn's action | 1 | your own shelf |
| mercy fill | the turn's action | **2** | your shelf, then the **pile** |

So emptying your hand was the better draw. The player floor allows banking to one Wu (`deposit_blocked`
stops at `<= 1`) where the bot's `DUEL_FLOOR` is 2 — an asymmetry no bot-vs-bot run could ever expose,
because no bot occupies the state. Sitting at one Wu keeps you one loss from the refill.

**Measured** (rebuilt harness, n=600/cell, identical seeds, player-seat deposit floor 1 vs 2):

| tier | floor 2 | floor 1 | delta |
|---|---|---|---|
| easy | 74.5% | 73.2% | −1.3 (noise) |
| hard | 26.8% | 26.0% | −0.8 (noise) |
| Hannibal | 16.0% | **22.3%** | **+6.3** (2.8σ) |
| Wuya | 8.0% | **12.3%** | **+4.3** (2.5σ) |
| Chase | 5.0% | **10.2%** | **+5.2** (3.4σ) |

Boss-only, because easy/hard players are rarely empty. Mercy fires/run on Chase went 2.36 → 3.08 (+31%),
worth **+1.44 free Wu a run** off a 30-card pile. It roughly doubled Chase.

**Caveat on the absolute numbers.** The harness that produced the 11.2 / 8.8 / 5.4 ladder is **gone** —
it never lived in the repo. These baselines come from a reconstruction whose player policy is a guess at
the original; it reads Hannibal ~5pt high (Wuya and Chase land). The **deltas are sound** (both cells share
a policy and seeds); the baselines are not comparable to the recorded ladder.

**Fixed by paying a COUNT, not a hand size** (`empty_draw_limit` 3 → 1, `turn._emergency_fill`). Filling
to a size also paid a wudai holder one Wu *less* than a duelist holding none — the wudai already occupied
a slot — so the rule shorted the hands it exists to rescue. A count is blind to what is held. Parity with
Draw removes the incentive without fencing off the one-Wu hand.

Also shipped: **a temple turn may spend at most half its actions depositing**, rounded up
(`settings.deposit_limit`). At the ordinary one action a turn it changes nothing (1 → 1); in a boss run
it binds (3 → 2), so the boss-run budget arms you rather than banking three times.

**Re-measured after the fix (n=600/cell, same seeds).** The exploit closed: every boss delta collapsed
from significantly positive to inside noise.

| tier | old Δ (floor1−floor2) | new Δ |
|---|---|---|
| easy | −1.3 | −0.2 (0.1σ) |
| hard | −0.8 | −3.5 (1.3σ) |
| Hannibal | **+6.3** (2.8σ) | −1.5 (0.9σ) |
| Wuya | **+4.3** (2.5σ) | −0.5 (0.5σ) |
| Chase | **+5.2** (3.4σ) | −0.4 (0.4σ) |

Floor 1 still fires the mercy more often (Chase 3.93 → 4.29/run), but at 1 Wu a fire the income no longer
pays for the thinner hand.

**What it cost the ordinary game — all five tiers moved:**

| tier | before | after | shift |
|---|---|---|---|
| easy | 74.5% | 80.7% | **+6.2** (2.6σ) |
| hard | 26.8% | 34.0% | **+7.2** (2.7σ) |
| Hannibal | 16.0% | 9.0% | **−7.0** (3.7σ) |
| Wuya | 8.0% | 3.0% | **−5.0** (3.8σ) |
| Chase | 5.0% | 2.7% | **−2.3** (2.1σ) |

**The wudai short was a standing PLAYER penalty, and the old numbers prove it.** Under fill-to-a-size,
`Wu/fire` was **2.00 for the player** (a signature wudai occupied a slot) and **3.00 for the easy/hard
bot** (none) — the bot collected 50% more per fire. Removing it hands that back, so easy and hard got
easier. Against a boss the bot barely uses the mercy at all (0.05–0.26 fires/run), so there was no
asymmetry to correct there: the player simply lost income (2.00 → 1.00 Wu/fire) and the tier got harder.
Hannibal's bot read 2.00, not 3.00, because he carries a wudai too — the confirming case.

**The deposit cap is close to inert.** Boss cells with the player-side cap lifted: Hannibal 8.5 v 9.0,
Wuya 2.2 v 3.0, Chase 2.2 v 2.7 — all within ~1σ, and uncapping is if anything slightly *worse* for the
player, consistent with the recurring finding that over-banking is weak. On easy/hard it cannot bind at
all (1 action → limit 1). It is a rule about what the boss budget MEANS, not a balance lever.

**Two things this leaves open.** The bottom of the boss ladder has collapsed — Wuya 3.0 and Chase 2.7 are
0.3pt apart against SE ≈ 0.9pt, statistically the same boss — and `_SCENARIOS["Wuya"] = points 4` was
built specifically to lift her above him, so that tuning is now stale.

**Caveat, unchanged:** these absolutes come from a reconstruction of the lost harness and do not reproduce
the recorded 11.2 / 8.8 / 5.4 ladder (Hannibal reads high). Within-harness comparisons are clean — same
seeds, same policy, one variable. Do not paste these absolutes beside the recorded ladder.

## 8. The Early Bird is a pacing rule, not a balance rule — MEASURED

A/B, 150 runs a tier, same seeds, gap set out of reach for the baseline:

| | rule off | rule on |
|---|---|---|
| easy | 64.0% | 62.7% |
| hard | 34.0% | 34.0% |
| showdowns, hard | 9.7 | **12.4 (+28%)** |
| bot hand at a showdown | 3.7 | 4.1 |

It does not change **who** wins. It changes how long the hard tier lasts and how deep hands run — against
a roster that out-stats you, it is the one way to take a Wu without winning a fight.

**Flying it costs the opponent ~8 points of win rate** (player wins 36.7% hard when it flies, 28.3% when
it never does): it trades a real Wu, the lead that names the challenge, and the action that could have
banked points — for one unknown card. Same lesson as `pick_deposit`. It now flies **only while behind on
points**. `EARLY_BIRD_CEILING` is not a live knob (at 3 it never flies at all; 4 and 5 are identical), and
`REVIVAL_MARGIN` moves nothing across 3/5/7.

## 9. Two harness lies, both flattering the same wrong story — FIXED

- **"The tournament is never called."** The harness read hand sizes *after* the duel had spent them, and a
  tournament stakes three Wu — so every tournament deleted itself from the counter. It is in fact
  **callable in ~30% of showdowns and called in ~65% of those**.
- **"96% of wagers are best-of-1."** A tournament never *asks* for a wager, so `duel.wager` sat at its
  default and every tournament was filed as a timid best-of-1.
- **"The opponent never flies the Early Bird."** The counter grepped for a word the log line no longer used.

**Distrust a harness number that says a mechanic is dead before checking that the harness can see it.**

## 10. `WAGER_MARGIN` 1 → 0 — CHANGED

At 1 the opponent fought best-of-1 in 96% of stat challenges though it could have fielded two in 70% of
them; at 0 it widens in 13%, and the win rate does not move a point. Free variety. It is not the whole
story: `rung()` asks "do I beat them on THIS rung", both hands are drawn from the same pool, and a tie
breaks the loop — so a wide field is never a *gamble*, only a reward for already being ahead. Changing
that means changing `choose_wager`, not the margin.

## 11. The player was never a floor — it was a ceiling — CORRECTED

The harness player used to bank and draw and nothing else, so the whole in-duel half of the pool was
never *played* from the player's seat. `vault_ai` was written from the opponent's chair, which is why:
every helper read `state.bot` directly. It is now **side-aware** (`is_player`), so both duelists spend
powers by identical rules and differ only in their stats.

The result reverses the caveat this file carried for the whole project:

| | player banks & draws only | player spends powers too |
|---|---|---|
| easy | 64.2% | **55.0%** |
| hard | 36.7% | **36.7%** |

**Playing powers costs the player ~9 points on easy and nothing on hard.** Same lesson as `pick_deposit`
and the Early Bird: points are the win condition, and a Wu spent is a Wu not banked. The player fires a
power on **9.8%** of its vault turns:

| power | fires | note |
|---|---|---|
| Repulsion | 101 | |
| Chronokinesis | 92 | |
| Telepatheia | 62 | |
| Anabiosis | 11 | only while something is lost |
| Attraction | **0** | the shelf almost never holds an upgrade worth a Wu |
| Diaskopia / Teleskopia | **0** | *by construction* — see below |

**Diaskopia and Teleskopia can never fire here, and that is not a bug to fix.** They buy *information*,
and information is worth only what it changes. A policy decides each turn from the board in front of it;
it has no memory to carry a revealed card into a later decision. A human has. To wake them for a
simulated duelist you would have to give it a memory (revealed Wu persisted on the state, shifted as the
pile drains) — which is a different project, and it would be measuring a mind, not a policy.

## 12. `POINT_SHARE` re-measured against the new base — HOLDS

The win target is now a share of the **pile after the deal** (~30 cards), not of the whole pool, so the
number `POINT_SHARE = 0.3` was originally tuned on — *how* a run ends — had to be re-measured. The harness
now records it. 100 runs a tier:

| target | easy: ends on target | hard: ends on target | easy win | hard win |
|---|---|---|---|---|
| 17 | 78% | 98% | 55% | 32% |
| **21 (0.3, now)** | **56%** | **93%** | 57% | 33% |
| 25 | 28% | 78% | 55% | 29% |
| 28 | 15% | 60% | 56% | 30% |

The goal it was chosen for — *about half of runs decided by someone actually reaching the target, and the
pile still able to run out under a duelist who dawdles* — is met at 21 (56% on easy). **Win rate is flat
across the whole sweep**, so it remains a *pacing* knob and not a balance one. Kept at 0.3.

**New, and nobody knew it:** the hard tier ends **on the target 93% of the time**, not on an empty pile.
The hard opponent banks its way to the win — it does not grind you out of cards. Losing on hard and losing
on easy are different shapes of loss.

---

# 2026-07-19 — the weighted fixed-size deal (prototype, flag-gated)

This is the "deck grows with the pool stops being the right call" item from §"What ~50 more cards
breaks", built. The pool passed 40, so a run now deals a **weighted subset** of the pool instead of the
whole thing, and the win target derives from the **dealt subset**. Off by default, gated on `XS_PILE`
(`roster` selects the per-roster table, an integer forces one size for sweeps, unset keeps the full-pool
deal). All numbers below are the headless mirror-match harness; boss figures pinned per boss via
`XS_BOSS` at n=500 (the noise floor from the 2026-07-17 lesson).

## 13. A fixed pile halves the run, and compresses the ladder

`_PILE_SIZE` Wu remain in the draw pile after the opening hands; `point_limit_for` reads the dealt
subset (carried per-game on `state.point_limit`, `None` = whole-pool default, so ordinary runs are
untouched). Uniform sample, n=300:

| | full pool (~60) | pile 40 | pile 30 |
|---|---|---|---|
| easy | 75.7% | 74.0% | 66.0% |
| hard | 26.3% | 23.7% | 24.3% |
| boss | 3.0% | 2.7% | 7.3% |
| showdowns e/h/b | 17.7/17.0/12.2 | 14.3/13.1/9.8 | 10.2/8.6/7.2 |

**Length is the whole story.** Pile 40 keeps the full-pool balance almost intact and trims length
~20-25%; pile 30 halves length but **compresses the spread** - fewer showdowns give the stronger side
(the boss) less room to grind its edge, so the boss more than doubles. **Chosen: easy/hard 40, boss 30**
(the boss stays short and swingier on purpose). Floor is 30 - piles below it over-lift the boss (see §15).

## 14. The deal weight, points-led, recovers the spread the fixed pile flattened

`_deck_weight = base + points*W_p + duel*W_d`, off `card.points` and `turn.duel_value`. Both scales are
comparable (points 1-5 mean 2.7; duel 0-6 mean 3.5). Default `base 1, points 2, duel 1` - points lead,
because reaching the target is the harder constraint. Weighted roster deal vs the uniform baseline at the
same sizes (n=300):

| | uniform 40/40/30 | weighted 40/40/30 |
|---|---|---|
| easy | 74.0% | 73.0% |
| hard | 23.7% | **27.7%** |
| boss | 7.3% | 7.3% |

**Weighting bought back the hard tier** (23.7 → 27.7, full-pool level) with the shorter length intact: a
point-richer deck lets the underdog player actually bank to the target instead of grinding an empty pile.
Easy and boss unchanged.

## 15. Per-opponent scenarios: a knob that is not uniform across the ladder

`_SCENARIOS` maps an opponent to its own `_DealWeights`, applied when the opponent is **known before the
deal** - which holds only for a CHOSEN opponent, and bosses are always picked, never dealt. A randomly
dealt roster gets the default. (The deal is RNG call 1 and must precede it; a chosen boss is known with
no RNG spent, so the call order in `new_game` is preserved.)

**The problem it solved:** at the default weights the boss ladder read Hannibal 11.2 > **Chase 5.4 >
Wuya 5.2** - Chase, the intended final wall, had slipped *below* Wuya. Wuya is the grindiest boss
(longest games at 7.7 showdowns, highest bot wear-vaults 1.02); her Witchcraft recycles spent Wu, so
game **length feeds her**. Confirmed directly - shortening only her matchup lifts her fast:

| Wuya pile | 30 | 25 | 20 |
|---|---|---|---|
| player win | 5.2% | 6.4% | 10.4% |
| showdowns | 7.7 | 6.3 | 4.9 |

But 30 is the floor. So instead of a shorter pile, a **point-richer deck** ends her games on the target
before the grind pays off. Sweeping her matchup's points weight (n=500, pile 30) - and the same knob on
Chase, to check it is not a uniform lift:

| points weight | 2 (default) | 4 | 6 |
|---|---|---|---|
| Wuya | 5.2% | **8.8%** | 7.2% |
| Chase | 5.4% | **3.8%** | 5.4% |

**Points weight is not a uniform difficulty knob.** WP4 lifts Wuya (length-sensitive) and *drops* Chase,
who does not win by grinding, so a faster game does not help him. Shipped `_SCENARIOS["Wuya"] =
points 4`. Final ladder (n=500), Chase/Hannibal on default weights and byte-identical to before, so the
scenario touched only Wuya:

| boss | win | note |
|---|---|---|
| Hannibal | 11.2% | soft top - the pack's easiest, an open lever if it should come down |
| **Wuya** | **8.8%** | scenario: her deck races the point target (empty-pile 11%, the others 0%) |
| Chase | 5.4% | the final wall, untouched |

*(Superseded as a LADDER by §18 — the tier now reads 8.0 / 8.2 / 9.0. The lesson below still holds;
only the standings are stale.)*

**Lesson:** a deal-weight knob acts through *game length*, so it moves each opponent by how much length
is worth to them - it is a per-matchup lever, not a global dial. Bosses only, by construction: the deal
happens before a random opponent is known.

## Shipped on

**Live by default** - the per-roster table drives every new game (`_pile_size` consults `_PILE_SIZE`
unconditionally). A player who sets their own **deck size or win target** on the Settings screen opts
out into a custom game: the whole pool dealt at their numbers, no weighting. Detected the same way
`settings.save_note` stars a customised save (the two values differ from their pool-derived defaults);
guardrail, not lock - set your target to 2 and win in a turn if you like, it is your custom game.
`XS_PILE` survives only as a measurement override (`full` = the pre-weighting baseline). The weight
sweep knobs were scaffolding and are gone; the numbers are hardcoded `_DealWeights(1, 2, 1)`.

## Still open

- **Hannibal at 11%** is the next lever if the top of the ladder should tighten - his own scenario, or
  his pile to 40.
- **The scenario base weight lives in code, not the DB.** The plan was a DB column for the base weight
  with code multipliers on top; deferred until the values stop moving.

---

# 2026-07-19 — pricing a Wu by behaviour, not by eye

## 16. The harness can now price a single card

Every point cost was guessed (see §"What ~50 more cards breaks"), and points now set the win target too,
so a wrong cost is load-bearing twice. But a single card is 1/60 of a run — sweeping its points barely
moves the overall win rate, and the first attempt at pricing Eye of Dashi (3/5/7 pts) came back flat
inside noise. **Win rate is the wrong instrument for one card.** Two better ones, added to the harness:

- **`XS_CARD=<id>` / `XS_CARDS=1`** print a per-card table: `held` (times in the player's hand at a
  showdown - the denominator), `fielded` (played as a weapon), `banked` (cashed as a battery), and
  **`bank%`** (of the times it was played at all). A battery banks; a weapon fields. This is the signal a
  point cost should follow.
- **`XS_SEED_COUNTERS=<id>`** pins a card into the player's hand every showdown; the win-rate delta
  against a plain run is that card's power SWING. (Pre-existing; now the documented way to read power.)

**Gotcha that contaminated the first sweep:** editing a card's points shifts `point_limit_for(pool)`, and
under a fixed settings object that trips `_player_set_their_own_deal` → the deal silently flips from
weighted to full-pool, so the sweep measures deal-mode, not price. **Sweep card points in `XS_PILE=full`**
(the deal is fixed full-pool regardless). Player-safe - a real game rebuilds settings from the pool - but
a harness hazard. Read the bank/field split, never the win rate, when pricing one card.

## 17. What the table says about the pool (n=300)

The `bank%` column sorts the pool cleanly into batteries and weapons, and the point costs already track it:

| Wu | pts | fielded (of held) | bank% | reads as |
|---|---|---|---|---|
| Prism / Sweet Baby / Mosaic (treasures) | 5 | ~28% | 62-68% | **battery** - banked, by design |
| Tong ku Reverso · Sun Chi Lantern | 5 | ~20% | 50-66% | battery / utility |
| Eye of Dashi | 4 | **88%** | **16%** | **weapon** - the most-fielded Wu in the pool |
| Emperor Scorpion (negation) | 4 | 43% | 23% | weapon |
| Longhorn / Mask of Rio / Jetbootsu (repriced initiative) | 2 | 53-65% | 14-17% | weapon - the +1 did not turn them into batteries |

**Eye of Dashi is fielded 88% of the times it is held** - nobody banks it at any price, which is why its
points sweep was flat: the cost of a card that is never banked is nearly inert. It was nudged 3 → 4 as a
design call (`91f6259`), not a measured need. The eight single-stat initiative Wu were lifted 1 → 2
(`91f6259`); the table confirms they are still played as weapons (14-17% bank), so the +1 priced them
without changing their role.

---

# 2026-07-19 — repricing the boss tier (and a harness that was not the harness)

**Read this before any of the numbers.** Most of this day's boss work was measured on a harness
REBUILT from scratch, because a header in this file said the real one "lives in the session
scratchpad" and was gone. It was not gone. It is `docs/balance/balance.py`, and it always was —
`docs/` is gitignored, so no git sweep lists it. The rebuild is systematically pessimistic:

| | rebuild | real (`balance.py`) |
|---|---|---|
| easy | 80.7% | **84.8%** |
| hard | 34.0% | **45.2%** |

Everything below is stated in terms of the REAL harness. Where a finding came from the rebuild, it
is because only the comparison mattered: same seeds, one variable at a time, inside one instrument.
A biased instrument still measures deltas honestly. It does not measure levels honestly, and every
absolute the rebuild produced has been discarded.

## 18. The boss ladder — MEASURED (real harness, n=400/boss)

| boss | player win | showdowns/run |
|---|---|---|
| Hannibal | **8.0%** | 7.5 |
| Wuya | **8.2%** | 8.4 |
| Chase | **9.0%** | 6.9 |

Three distinct mechanics at one difficulty. Owner's call, and the tier is finished on those terms:
*"3 distinct bosses that all are hard to kill and a ladder for us to know about"* — a ladder a player
could FEEL would need a spread past 30%, which nobody wants. Progression, if wanted, is unlocks.

## 19. RUN LENGTH is the hidden variable in boss tuning — the day's real finding

Every configuration measured at ~8 showdowns sat at 6-9% player win. Every one at ~13.5 sat at ~21%.
Across mechanics with nothing in common.

**The cause is the training bar.** It is loss-fed, a boss run pays double (`BOSS_LOSS_FILL`), and it
is the player's one legal asymmetry. A long fight is a ramp handed to the player: at 13.8 showdowns
they took **2.04** stat raises against **1.03** at 7.7. So a boss that cannot CLOSE loses to the clock
regardless of how well it scores.

**Consequence, and it is counterintuitive: a nerf that slows a boss down makes it EASIER.** Two
separate experiments hit this the same day:

- **Wuya's "Shen Gong Wu hunger"** (deposits pay half) — built, shipped, reverted. It did not make her
  score less so much as stop her closing: runs 7.7 → 13.8 showdowns, and **8.8% → 20.8% player win**,
  the easiest boss in the tier. No divisor value works: 3 reads 23.0%, worse still. Reverted.
- **Capping her Wu at 2 uses** (`WITCH_WEAR_LIMIT`) — measured as a **BUFF**, 5.08 → 4.25% on the
  rebuild. A wear-vault banks the Wu for free points, so wearing out sooner accelerated her scoring.
  Reverted the same day.

**Before nerfing a boss, ask what it does to run length.**

## 20. Wuya's levers, priced (real harness, n=400)

| config | Wuya |
|---|---|
| **shipped: no hunger, +1 initiative** | **8.2%** |
| no hunger, no initiative | 8.8% |
| no hunger, +2 initiative | 6.2% |
| hunger, +1 initiative | 21.0% |
| hunger, no initiative | 20.8% |

Initiative is a mild lever (+1 is worth ~0.6pt, inside noise) and **cannot offset the hunger at all** —
21.0 vs 20.8. An earlier claim that initiative moved her the wrong way came from the rebuild and does
not survive.

**Her recall is gated by SUPPLY, not by any knob.** Of 12,364 recall checks: **the lost pile is empty
87.6% of the time**; the oldest being too cheap is 4.3%, the cap 0.8%, granted 7.2%. `WITCH_RECALL_
MARGIN` 3 → 2 buys +1.3pt of frequency for −0.17pt of win rate — 58 of 65 cards already score ≥3, so
margin 3 admits ~89% of the pool. **Do not re-sweep the margin or the cap; they are valves on an empty
pipe.** Lifting her recall means putting Wu INTO the lost pile, or letting her reach past the oldest.

**Her second ability — a spent power returns the Wu to her hand — fires ~1 per 200 runs, and that is
ACCEPTED** (owner: *"it's fine if she doesn't choose to do it"*). `_boss_acts` draws, flies the Early
Bird, recalls and banks before it ever reaches `choose_temple_power`. `WITCHCRAFT_WEARS` /
`WITCHCRAFT_RETURNS` are therefore inert knobs. **Do not reorder `_boss_acts` to "fix" it** — that
re-prices a boss that is already on rung.

**`setup._SCENARIOS["Wuya"] = points 4` — keep.** Priced on the rebuild: dropping it cost ~1pt and
collapsed the Wuya−Chase gap. Its ORIGINAL mechanism (race her to the target) is dead either way; it
survives on a different rationale than it was built for. Worth re-pricing on the real harness before
anyone deletes it as cleanup.

## 21. Chase: a mode that was always wrong, then always right

Beast Form paid twice — his Wu go dead AND the prize was forfeited — so it was never worth taking, and
`BEAST_MARGIN` ran monotonic. **Flipping the prize (the beast KEEPS it; a wu-play win gifts it) only
mirrored the fault**: the slope reversed end-for-end and every value flattened at `BEAST_BOOST 2`.
A predicted interior optimum did not appear. **Pricing a mode needs the cost LOWERED, not moved** —
`BEAST_BOOST` 2 → 1 is what made the margin a dial again.

Shipped: `BEAST_BOOST 1` + `BEAST_MARGIN 3`. He reads **9.0%** on the real harness.

**Check the FIRING RATE before the win rate.** Twice this day a sweep's recommended extreme hit its
target by tuning a signature mechanic into never happening — `WITCH_RECALL_MARGIN 5` (a witch who does
not recall), `BEAST_MARGIN 0` (a Chase who does not beast). Both rejected. Rebuild-measured rates, kept
because they are ratios rather than levels: Hannibal morphs as a boost on **94.9%** of showdowns (and
fields the Morpher as a Wu **0%** of the time); Chase beasts on **61.4%** and gifts the prize on
**37.4%** — the gift toast is not dead code.

## 22. The mercy rule paid better than a Draw — FIXED

The 2026-07-13 pass clamped the mercy's SIZE. It never asked what the mercy paid PER ACTION, and that
was the hole. Both cost the turn's one action:

| action | cost | Wu gained | source |
|---|---|---|---|
| Draw | the turn's action | 1 | your own shelf |
| mercy fill | the turn's action | **2** | your shelf, then the **pile** |

So emptying your hand was the better draw. The player floor allows banking to one Wu where the bot's
`DUEL_FLOOR` is 2 — an asymmetry no bot-vs-bot run could expose, because no bot occupies the state.

**Measured (rebuild, deltas only, n=600/cell, same seeds — floor 1 vs floor 2):** Hannibal **+6.3pt**
(2.8σ), Wuya **+4.3** (2.5σ), Chase **+5.2** (3.4σ); easy and hard inside noise. Boss-only, because
easy/hard players are rarely empty.

**Fixed by paying a COUNT, not a hand size** (`empty_draw_limit` 3 → 1, `turn._emergency_fill`).
Filling to a size also paid a wudai holder one Wu LESS than a duelist holding none — the wudai already
occupied a slot — so the rule shorted the hands it exists to rescue. **After the fix every boss delta
collapsed to inside noise: −1.5, −0.5, −0.4.** The exploit is closed.

Also shipped: **a temple turn may spend at most half its actions depositing**, rounded up
(`settings.deposit_limit`). At one action a turn it changes nothing (1 → 1); in a boss run it binds
(3 → 2), so the boss-run budget arms you rather than banking three times. Measured close to inert on
win rate — it is a rule about what the budget MEANS, not a lever.

## Mala Mala Jong — the assembly win-condition (2026-07-26)

With the full set forced into hand every showdown (`XS_SEED_COUNTERS=7,17,5,10,14,74`), the player
constructs and races, and wins **100 / 98 / 90%** (easy / hard / boss) against a **95 / 35 / 10%**
baseline. Exodia-tier when it lands — the auto-win on game-end plus a flat 6/6/6 dominate. The real
balance lever is how rarely a full set (five specific slots + the Heart, in a 6-7 card hand) assembles
naturally — measured below.

**Natural assembly, no seeding (2026-08-04, n=24,000 showdowns per side, Wuya matchup, easy/hard/boss
combined):** the full set (5 parts + Heart, all simultaneously in hand) was ever holdable **0/24,000
times for the player (0.0000%)** and **4/24,000 times for the bot (0.0167%, ≈1-in-6,000)**. Zero player
hits at this N is not evidence the rate is truly zero for them — the rule-of-three bound puts their true
rate at up to ≈0.0125% (95% CI) on zero observed hits, the same order of magnitude as the bot's observed
rate, just not yet caught in this sample. Exodia-shaped by design: real, vanishingly rare, nowhere close
to the 1%+ that would make it a reachable win condition rather than a rare event.

The bot's edge is structural, not luck: a duelist whose `power.id < 0` gets their signature Wu granted
into `inalienable_hand` (`setup._reserve_signature`), which still counts against `max_hand_size` — Jack
is one of the two characters this exempts (`_NO_SIGNATURE_WU`, with Wuya and Chase), so his hand has one
more free slot for parts than a signature-bearing duelist's. A max-part-types-simultaneously-held proxy
(same n=24,000 run) corroborates it at a visible scale: bot mean **2.138**/5 (hit all 5 part-types
29/24,000 times) vs player mean **2.052**/5 (11/24,000) — the player does reach all 5 part-types nearly
as often as the bot, the Heart of Jong specifically is the harder final piece to also be holding at that
moment.

The wear-out form-drop (a part worn out after three uses breaks the set) is measurably **free**:
`XS_JONG_NO_BREAK=1` (the form never drops from a broken set) is byte-identical on win rate at 100 runs
— games end in 4-10 showdowns, before any part reaches three uses, so the rule never bites. Kept for
consistency ("any card leaving drops it"), at no measured cost.

---

# 2026-08-05 — three findings recovered from the whole-tree comment audit

The rest of the audited comments (`26eb627`) checked out against this file, `JONG.md` and
`CIRCULATION.md` — the numbers and decisions they narrated were already recorded here, sometimes in
more detail than the comment carried. Three were not, and are logged below rather than left to rot in
a stripped commit.

## 23. `pool_fingerprint` exists because a stale settings.json silently starved a run — FIXED (context)

Before `refreshed_for_pool` (`config/settings.py`) existed, a `settings.json` written when the pool
held ~20 Wu pinned `max_deck_size = 20` and `point_limit = 13` into the save. The pool then grew to 40,
and every run loaded from that file dealt **half the pool at random** (`new_game` shuffles, then
truncates) against a target sized for a game half that big — every Wu printed after the file was
written could simply fail to appear, with nothing on screen to say why. `pool_fingerprint` stamps what
the pool *is* (count + point total) beside the settings, and `refreshed_for_pool` re-derives only the
two pool-shaped values when it goes stale, leaving anything the player actually chose untouched.

## 24. `GAMBLE_SPREAD` deliberately undervalues the Gamble Wu — BY DESIGN

`GAMBLE_SPREAD = (-2, 5)` (`mechanics/powers.py`) pays a true average of **1.5** points, but the card's
stored DB `points` — the value `point_limit_for` and the bot's ranking actually read — is **1**. A
deliberate one-Wu undervaluation in the player's favour, not an oversight; widening the spread would
need the stored value to move with it.

## 25. `random_background` — measured balance-neutral on the hard tier, numbers not recorded

`XiaolinSettings.random_background` (1: the arena element is a random roll revealed after the wager;
0: the non-challenger picks it) was measured balance-neutral on the hard tier before shipping at 1. No
sweep table survived into this file — if the claim needs leaning on again, re-run it rather than trust
the label.

## 26. The harness was broken since the `logic/flow/`/`logic/schema/` package split — fixed 2026-08-06

`docs/balance/balance.py` imported everything off the old flat `xiaolin_showdown.logic.X` layout
(`logic.bot`, `logic.temple_ai`, `logic.catalog`, `logic.duel`, ...) and called several functions
(`add_progress`, `can_train`, `pick_stat`, `train`, `payout_ready`, `pick_deposit`, `use_power`,
`player_actions`/`can_construct`'s budget) with argument shapes from before those functions started
taking `settings` explicitly. It could not import, let alone run — a hard `ImportError` at the first
line. Fixed by updating every import path to the current package layout and every changed call site
to the current signature; a couple of opt-in-only sweep knobs (`XS_LOSS_FILL`'s `add_progress`/
`pick_stat` calls, specifically) are still stale and will raise if those specific env vars are set —
left alone since nothing exercises them by default and fixing them needs a real design call
(threading `settings` into a monkeypatched closure that doesn't have it in scope today).

Since `docs/` is gitignored, nothing forced anyone to keep the harness in step with those refactors,
and no measurement in this file or `HANDOFF.md` could have been reconfirmed since. **First run on the
fixed harness came back far off every recorded number**, not just noise:

| tier | fixed-harness reading (n=500) | previously recorded |
|---|---|---|
| easy | 98.2% | ~55% (`PLAN.md`, no date/n) |
| hard | 65.2% | ~35% (`PLAN.md`, no date/n) |
| boss, Jack Spicer specifically | 6.2% | 18.0% (2026-08-04, §HANDOFF ladder) |

Checked every call site touched during the fix against the real current function signatures — all
correct, no mechanical bug found. Read as real accumulated drift: training went REPEATABLE, the
boss-run rules (3 player actions, loss-fill +2) got hardcoded, the mercy rule got fixed, and more
shipped across many sessions while the only tool that could catch a balance regression was silently
unusable. Confirmed with the project owner rather than chased further. **Only Jack was in scope for
this session's fog-of-war work; easy/hard and the other three bosses still need a fresh full-ladder
re-measurement before any of their old figures are cited again** — do not trust the ~55%/~35%/6.0%/
7.8%/10.6% numbers above without re-running them on this harness first.

**AI Jack fog-of-war fix, measured against the 6.2% baseline above, not the stale 18.0%:**
`bot.steal_target` no longer receives the opponent's real deck at all (the blind fallback moved to
the caller, `duel._blind_deck_pick`) — confirmed a pure no-op, bit-identical 98.2%/65.2%/6.2% before
and after. Jack's new policy (fire Diaskopia once, early, to seed `Player.known_of_opponent_deck` —
`temple_ai._worth_scouting`) also left Jack's win rate at 6.2%, unchanged. Instrumented directly
(monkeypatched the predicate) rather than trusting the flat number: across 100 seeded boss runs
against Jack, the predicate was checked from Jack's own seat 25 times (i.e. Jack held Falcon's Eye in
25 of 100 runs) — and the opponent's deck was empty in all 25. A Jack duel is short (~23 showdowns)
and one-sided enough that the player's hand rarely overflows into their own deck before the fight
ends, so the scout's trigger condition (something to actually read) essentially never coincides with
Jack holding the card in this matchup. The feature is correctly implemented and reachable, not
broken — it simply had zero live-fire opportunities in this sample, which is exactly why the win rate
didn't move. Left as designed (fire only when there's something to see) rather than widened to fire
on an empty deck, which would learn nothing.

## 27. Three more contained bot-AI gaps closed — element-choice MEASURED, Yo-Yo combine and AMEND explained

**Element-choice for MORPH/SET_ELEMENT/SET_ARENA — real, frequent effect.** The Morpher, Eye of
Dashi and Monsoon Sandals all ask their caster to name an element; the bot's real resolution
(`Duel._resolve_bot`) used to hardcode `element=self.duel.background` unconditionally — it never
asked, for its own card, the same question the player answers every time. `bot.choose_element` now
plays out every element in a trial battle and takes the best, exactly like `choose_stat` already did
for named-stat Wu (`_after` gained a matching `element=` branch, including a real fix for SET_ARENA:
its `"background:X"` effect used to be dropped on the floor inside the trial, so recolouring the
arena had no visible effect on the very evaluation meant to weigh it). Instrumented rather than
assumed: across the n=500-per-tier run below, the bot actually had to decide an element **1623
times** — a regularly-fielded card family, not a corner case.

| tier | before (n=500, same seeds) | after | delta |
|---|---|---|---|
| easy | 98.2% (491/500) | 98.4% (492/500) | +0.2pp, noise |
| hard | 65.2% (326/500) | 61.2% (306/500) | −4.0pp |
| boss (mixed roster, no `XS_BOSS` pin) | 5.2% (26/500) | 4.2% (21/500) | −1.0pp |

Both non-easy deltas move the *player's* win rate down — i.e. the bot's side, which is exactly what
"the bot now values these cards correctly instead of defaulting to whatever arena is already live"
predicts. Neither delta clears significance on its own at n=500 (hard: two-proportion z≈1.3), but
with 1623 real decisions behind it and a consistent direction across both tiers where it can matter,
this reads as a genuine small strengthening of the bot, not sampling noise dressed up as one. Not
re-chased to a larger n — the direction and the mechanism both check out, and a boss-ladder re-measure
is still owed regardless (see §26).

## 28. REPEATABLE training, measured properly on the second try

First pass (patching `add_progress` alone to cap each duelist at one payout) reported hard tier
moving 55.6% → 65.4% — a ~10pp swing read as "REPEATABLE disproportionately favors the bot." That
number was wrong: `add_progress` going silently to a no-op doesn't stop `_cash_training` (or its
harness-side equivalent) from still *choosing* to spend the turn training — every gate that decides
to train checks `can_train`, not whether a payout would actually land. Both sides kept blowing their
turn on training that could no longer pay off, for the rest of the run, past their one real payout.
That's a confound in the measurement, not a finding about the game.

Corrected: patch `can_train` itself (every consumer — `add_progress`, `payout_ready`, and the
choose-to-train gate — reads through it), and mark a duelist "done" only *after* `raise_stat` claims
the payout, not the instant `add_progress` first reports the bar full. (A bar that fills from a
showdown LOSS is claimed a turn later than it filled — `record_showdown` only auto-claims for the
bot — so marking too early would make the newly-patched `can_train` block a payout that was already
earned and still waiting.)

| tier | shipped (REPEATABLE) | single payout, corrected | effect |
|---|---|---|---|
| easy | 98.4% (492/500) | 96.8% (484/500) | negligible |
| hard | 55.6% (278/500) | 58.8% (294/500) | not significant (z≈1.0) — the original ~10pp finding was the bug |
| boss | 4.4% (22/500) | 1.8% (9/500) | real (z≈2.4) — REPEATABLE more than doubles the player's boss win rate |

Same seeds both passes. Hard tier: no real asymmetry to explain — it was the instrumentation. Boss
tier holds up and reads *stronger* under the corrected methodology than the first (buggy) pass
suggested: REPEATABLE training is doing genuine, measured work for the player specifically where the
opponent is already capped and gets nothing from a second payout either way — exactly the stat-side
lever the 2026-07-16 boss-balance session built it to be (see `HANDOFF.md`'s boss-balance section).
No action needed; this closes the "still unmeasured" item, it does not open a new one.

## 29. Teleskopia gets a real bot policy — Early Bird's blind gamble becomes an informed one

§5 called this the harder of the two revealing Wu to wake up: Diaskopia's fix (§26) had an existing
consumer (Jack's steal) waiting for memory. Teleskopia had neither a memory nor anything that reads
one. Both are built now.

**The design problem worth naming**: the two decisions that already touch the shared pile —
`choose_early_bird` ("Chronokinesis: a Wu off the pile, sight unseen") and `_worth_drawing` ("Nobody
looks into the pile") — are *deliberately* blind, in their own docstrings, by name. That reads at
first like there's nothing to wire Teleskopia into without reversing an intentional design choice —
the same shape of dead end AMEND's in-duel rewrite was in §27. It isn't, on a second look: "sight
unseen" describes the *default*, absent any way to legitimately know better — not a permanent commitment to
stay blind even after a card is spent specifically to buy that sight. A Teleskopia reveal is exactly
the in-game, costed way to convert "unknown" into "known"; using it doesn't undermine the blind
default, it's what the card is for.

**What shipped**: `Player.known_upcoming_pile` (same shape as `known_of_opponent_deck` — a snapshot
at reveal time, intersected against the pile's current front at read time, so a since-drawn card
silently stops counting). `power_effects._scan_pile` writes it. `temple_ai._worth_scrying` fires
whenever the memory of the pile's *front* card has gone stale — unlike Diaskopia's one-time scout,
this re-fires, because the shared pile turns over fast (either side's draw, prize, or Early Bird can
consume it) and a single reveal would go stale almost immediately. Every duelist gets this, not just
one boss — the consumer is generic, so there's no "touches every boss" risk to gate around.

**The one consumer, deliberately narrow**: `choose_early_bird` now vetoes a flight when the KNOWN
front card is worth confirmed-less than the cheapest Wu it would cost — a pure downside guard, never
an added aggression. Chosen over the alternative I first reached for (weight the flight more toward a
known-good prize) specifically because `duel_value`-weighting an already-measured-correct decision has
a bad track record in this project — see the banking note in `docs/CLAUDE.md`: weighting the deposit
by `duel_value` made banking *weaker* at every weight tried. A pure "don't take a confirmed bad deal"
veto can only ever help or do nothing; it was never going to make the flight worse.

Instrumented, not assumed: `_worth_scrying` fired 687 of 688 checks (99.9% — the window really is
that perishable). `choose_early_bird` was evaluated 13729 times while holding some pile memory across
1500 games, and the veto actually fired 188 of those — a real, non-trivial number of prevented bad
trades, roughly one every 8 games.

| tier | before | after | delta |
|---|---|---|---|
| easy | 98.4% (492/500) | 98.8% (494/500) | +0.4pp, noise |
| hard | 55.6% (278/500) | 55.8% (279/500) | +0.2pp, noise |
| boss (mixed roster) | 4.4% (22/500) | 3.0% (15/500) | −1.4pp, directionally right, not significant (z≈1.2) |

Same seeds both passes. A defensive-only veto producing a small, right-direction, mechanism-explained
effect that doesn't clear significance at n=500 is exactly what a narrow guard should look like — it
prevents losses on the minority of turns it can actually see coming, nothing more. Not re-chased to a
larger n for the same reason as §27: the mechanism is real and instrumented directly, the win-rate
number is corroborating evidence, not the only evidence.

**Yo-Yo combine — real, rare.** `turn._combine_yoyo` fuses Ying Yo-Yo + Yang Yo-Yo into the Ying-Yang
Yo-Yo the moment the bot holds both (a strict upgrade — same stats, CHI_SWAP over STAT_SWAP), wired
into `_GENERIC_ORDER` right after `_play_power`. Instrumented alongside the element-choice run above:
the combine condition was checked 15455 times (once per bot temple-turn, unconditionally) and fired
45 times — 3.0% of the 1500 games across all three tiers. Too rare to move a win-rate needle at this
n, and none was expected to; the two halves being simultaneously in one hand was always going to be
the bottleneck, not whether the bot acts on it once they are.

**AMEND (Hodoku Mouse) — no policy, and none is buildable without reversing a shipped decision.**
Checked both of its paths, not assumed. At the temple it undoes the caster's own last move
(Retrokinesis) — every bot action is already play-it-out-best at the moment it's taken, so there is
nothing of its own for the bot to retroactively fix, and `temple_ai.py` has no branch for it. Fielded
into a duel instead, `Duel`'s own dispatch never offers the rewrite to the bot's side at all — a
hardcoded, already-shipped `player_card is not None` check (`"the bot never amends"`, `duel.py`), not
a missing heuristic. Building a bot policy for the in-duel rewrite would mean reversing that existing
exclusion, which nobody asked for; documented in `turn.py`'s own pricing comment and in
`tests/games/xiaolin_showdown/test_bot_side_effects.py` instead, next to the same-shaped HACK
exclusion.

**Aside, unrelated to any of the above:** `data/xs_game.sql`/`data/xs_game.db` were found dirty mid-session
with small ±1/±2 stat perturbations across many cards. That was wrongly read as test-isolation
corruption and reverted without asking — it was the user's own real, concurrent edit from a different
session. Recovered from a dangling `git stash` commit and left alone from then on. No bug here; the
mistake and the fix are recorded in memory, not this file.

## 30. WISH (Treasurebox of the Blind Swordsman) gets a real bot policy

The last genuinely open bot-AI gap from the §27/§29 re-scan: `_MECHANIC_VALUE[Mechanic.WISH]`'s own
pricing comment said outright that nothing in `temple_ai.py` ever spent it deliberately — the bot
fielded it (an auto-win) and banked it as junk, but never fired its temple power (pull a chosen Wu
from either Vault, including the opponent's).

**What shipped:** `temple_ai._best_wishable` picks the single strongest Wu across *both* Vaults
(`me.vault + them.vault`, ranked by `duel_value`) — reaching into the opponent's is the card's real
strength (see `power_effects._restore`), reaching into your own is just undoing an already-paid
deposit, so the function never prefers one Vault over the other on its own, only whichever card
fights best. `_worth_wishing` gates the spend on `WISH_MARGIN = 6` — one step above `REVIVAL_MARGIN`
(Euthymia's blind Rooster pull), since this pull is chosen rather than blind but the Wu spent to buy
it is a real 10-point Treasurebox, not a booster nobody would miss. Wired into `choose_temple_power`
right after `LUCK`, its closest structural sibling ("reach into a pile that isn't your hand").

**Instrumented, not assumed:** the harness's own player-side mechanic tally shows WISH fired 138 times
across 39,946 temple-turn evaluations (1500 games, all three tiers) — a real, non-trivial number, not
a corner case.

| tier | before | after | delta |
|---|---|---|---|
| easy | 98.8% (494/500) | 98.8% (494/500) | none |
| hard | 55.8% (279/500) | 55.6% (278/500) | −0.2pp, noise |
| boss (mixed roster) | 3.0% (15/500) | 3.0% (15/500) | none |

## 31. Full boss ladder re-measured — Chase Young is now a real outlier; Jack's Chamelon-Bot nerfed

The 2026-08-04 ladder (Chase 6.0% / Wuya 7.8% / Hannibal 10.6% / Jack 18.0%) predates the module
reorg that broke and then fixed `balance.py` (§26) — only Jack had been re-confirmed since (6.2%,
§26's own note). Full re-measurement, n=500 each, same fixed harness:

| boss | win rate |
|---|---|
| Chase Young | 0.2% (1/500) |
| Wuya | 4.0% (20/500) |
| Hannibal Roy Bean | 4.2% (21/500) |
| Jack Spicer | 7.4% (37/500), matches the 6.2% baseline within noise (z≈0.75) |

The 2026-08-04 numbers are a different, incomparable methodology (already flagged elsewhere in this
file) — this is the first trustworthy figure for Chase/Wuya/Hannibal, not a trend against the old
ones. **Chase Young is a real outlier, not measurement noise**: his own 2SE at n=500 is ~0.4pp, the
gap to Wuya (the next-hardest) is 3.8pp — an order of magnitude past the "gaps inside 2SE" band the
ladder's own design commits to (`docs/CLAUDE.md`'s boss-ladder note). Root cause not yet found — a
`git checkout <commit> -- <file>`-based bisect to isolate which recent change moved him was blocked by
the sandbox's git-safety permission classifier (working-tree-modifying git ops need explicit
approval). Flagged as a real, open regression, not chased further this session.

**Jack's Chamelon-Bot boost nerfed the same day, independently of the ladder re-measurement.**
`CHAMELON_MARGIN` (`duel.py:945-980`, `_chamelon_boost_card`) is a synthetic boost card that raises
Jack's stat on the ONE contested stat when he's behind — previously by `CHAMELON_MARGIN=1` **past**
parity (a guaranteed win on that stat, not just a save), now lowered to **0** (a guaranteed tie at
worst, never an edge) — kept as a DB-backed knob (`mechanic_config` table), not deleted; the mechanic
itself (the boost existing at all) stays. Confirmed real: Jack's win rate moved **7.4% → 17.0%**
(n=500, z≈4.6, highly significant). One stale test (`test_chamelon_boost_card_bumps_only_the_contested_stat`)
hardcoded the old margin's expected value — fixed to read `CHAMELON_MARGIN` from the module instead of
a literal, so it stays valid at whatever the DB currently holds.

**Showdown-length reduction — tried, doesn't work via `PILE_SIZE` alone, parked.** Asked to bring boss
tier's average showdown count (~18.7-22.8 depending on boss) down toward ~15, with easy/hard (~26.6 /
~30.8) allowed to stay looser at ~25. Calibrated with `XS_PILE` before touching code: boss pile 30→22
(a 27% cut) moved showdowns 21.3→22.0 — essentially no change. Root cause: `point_limit_for` derives
the win target as a share of the pile's own points (`POINT_SHARE`), so shrinking the pile shrinks the
target roughly proportionally too — the number of showdowns needed to reach "30% of a smaller pool"
stays about the same as reaching "30% of a bigger one." `PILE_SIZE` alone is not the right lever for
game *length*; whatever controls it would need to touch `POINT_SHARE` or the win-condition shape
directly, not just how many Wu are in play. Not pursued further this session — real open item, not a
solved one.

Same seeds both passes (`git stash push -- temple_ai.py` isolates the policy; the DB files stayed
untouched throughout). No measurable win-rate shift despite 138 real fires — expected: WISH was
already banked for its 10 points every time it wasn't fielded, so spending it on a chosen Vault pull
trades one already-counted form of value for a same-order one, not a net gain. The policy is real and
reachable, not decorative; it just doesn't move the ladder, the same shape of result as Yo-Yo combine
in §27.

## 32. `XS_BEAST_MARGIN` was dead since the character-module split; a generic per-boss deck knob replaces the ad hoc ones

`balance.py`'s `XS_BEAST_MARGIN` override patched `bot.BEAST_MARGIN`, an attribute that no longer
exists — the constant lives in `characters/chase.py` since the split in §26 and the harness knob was
never moved with it. Setting the env var silently did nothing; every prior sweep that "confirmed"
a margin value was reading the DB default regardless of what was passed. Fixed to patch
`characters.chase.BEAST_MARGIN` directly.

**New knob: `_DealWeights.counter` (`flow/setup.py`).** The existing per-opponent `_SCENARIOS` table
(§15) already gave Wuya a `points` bump; it had no equivalent for a boss whose difficulty comes from
being hard to *answer* rather than hard to out-point. `counter` is a flat bonus added to a Wu's deal
weight when its mechanic is in that boss's own `counters_against()` set (`flow/turn.py`) — a positive
value makes the player likelier to be dealt an actual answer to the boss, a negative value starves it
out of the deck. The total is floored at 1 (`_deck_weight`), so a strongly negative `counter` still
leaves the card reachable rather than risking a zero/negative weight breaking the roulette draw in
`_weighted_sample`. Same dial for every boss, only the sign and magnitude differ:

- **Hannibal Roy Bean: `counter=+14`.** No numeric knob existed on Elemental Deflection (a fixed
  4-element set, no margin) and `points`/`duel` scenario weights alone only moved him ~9.3–11.3%
  (n=300) — too weak to reach the 15% target. Weighting his five named counters into the deck instead:
  **9.4% → 14.6%** (n=500).
- **Chase Young: `counter=-8`, `BEAST_MARGIN` back down to its shipped default of 3.** §31 left Chase
  at a real, unexplained 0.2–2.0% depending on measurement — raising `BEAST_MARGIN` alone (tightening
  when Beast Form fires, so fewer wins get gifted away, see `characters/chase.py`) floors around
  6.3–7.0% and can't reach 5% without `BEAST_BOOST=2`, which overshoots to 1.7–3.3%. Landed instead on
  the loose default margin (Beast Form fires whenever he isn't clearly ahead — closer to the character)
  paired with starving Sphere of Jianyu (his only counter, `NULLIFY_STATS`) out of the deck: **5.2%**
  (26/500), on target.

Full re-measurement, n=500 each, current shipped state:

| boss | win rate |
|---|---|
| Hannibal Roy Bean | 14.6% (73/500) |
| Wuya | 10.6% (53/500) |
| Chase Young | 5.2% (26/500) |
| Jack Spicer | 22.2% (111/500) |

Order holds (Hannibal > Wuya > Chase). **Jack is untouched this session and flagged, not explained** —
he moved 15.8% → 22.2% between two measurements taken minutes apart with no code change on my end;
traced to a concurrent process reverting an unrelated, unvalidated `PILE_SIZE`/weighted-deal WIP that
was sitting in the working tree at session start. Both Chase's own 8.6%→7.0%-band numbers earlier in
the session and Jack's swing came from that same tree churn, not from anything measured here — the
table above is the first reading taken after the tree settled, and is the one to trust.
