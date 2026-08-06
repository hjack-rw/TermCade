# How a Wu changes hands

Three rules together decide whether Wu circulate or leave the game: the prize cascade
(`logic/mechanics/prize.py`'s `PrizeRoute`), the Early Bird (`logic/flow/temple_ai.py`), and the
Rooster Booster / lost pile (`Mechanic.LUCK`, `XiaolinState.lost`). The bot plays all three by the
same rules as a player — the Early Bird and the Booster are both reachable by `vault_ai.py`/
`temple_ai.py`, and `_award_prize` is shared code, not duplicated per side.

Before these shipped, the prize moved in only ~15–20% of showdowns and the Wu nobody won was
destroyed outright. Today, circulation is ~40% of showdowns (measured history:
`docs/design/BALANCE-HISTORY.md`, "Alternate ways to win a Wu").

---

## The prize cascade — four ways to claim the revealed Wu

The winner does not automatically take the revealed Wu. Four routes are tried in order, on **each
battle's own three end values** (`Side.result`), taking the first that qualifies. With
`N = prize_threshold + 1` (8) — `prize_threshold` kept its meaning through this change, so the
Settings screen didn't need to:

| #   | route                       | test                                        |
| --- | --------------------------- | ------------------------------------------- |
| 1   | **a decisive blow**         | one stat `>= N`                             |
| 2   | **a broad win**             | two stats `>= N-1`                          |
| 3   | **total command**           | three stats `>= N-2`                        |
| 4   | **in tune with the ground** | elemental surplus `> 0` across the showdown |

**Route 4** sums `element_score(card.element, background)` over the winner's contributing Wu, across
every battle: +1 for a Wu of the ground's element, −1 for its opposite (and for metal on any coloured
ground), 0 otherwise. **A Serpent's Tail vetoes it** — if the ground has stopped resonating, nobody
was in tune with it.

Metal is at a permanent disadvantage on route 4, and that is correct: 21 of 30 pool cards are metal,
and route 4 is the _fourth_ fallback. It belongs to the elemental Wu.

**Which route actually claims the Wu** (Easy / Hard):

| route                      | share         |
| -------------------------- | ------------- |
| lost                       | 63.8% / 52.0% |
| 1: a decisive blow         | 18.3% / 28.1% |
| 4: in tune with the ground | 10.4% / 12.4% |
| 2: two stats               | 6.0% / 4.6%   |
| 3: all three               | 1.5% / 3.0%   |

Route 4 is the second-biggest, and the only one a player can _aim at during the showdown_. Route 3 is
below the "worth having" line (<10%) and stays anyway: total command should be rare.

### The tournament is the prize play

The cascade reads all three stats of _each_ battle. A stat challenge is one battle (and the wager is
one Wu 95% of the time), so it offers 3 numbers. A tournament is three battles: **9 numbers**.

|                | share of showdowns | prize moves       |
| -------------- | ------------------ | ----------------- |
| stat challenge | ~83%               | 31.4% / 45.9%     |
| **tournament** | ~17%               | **59.2% / 58.9%** |

A tournament costs three Wu against a wager that is usually one — triple the commitment, roughly
double the prize chance. That is a fair trade and it gives the challenge choice a meaning it never
had: **call a stat challenge to protect your hand; call a tournament when you want the Wu.**

It is also a flywheel: more circulation means bigger hands, so tournaments (which need three Wu a
side) become callable more often, which drives more circulation.

For the pre-cascade baseline, the incremental route-by-route sweeps, and the dead ends along the
way, see `docs/design/BALANCE-HISTORY.md`, "Alternate ways to win a Wu" (local-only).

---

## The Early Bird Gets The Worm

Gated on the ±2 initiative Wu that back it (`logic/flow/temple_ai.py`, `EARLY_BIRD_GAP = 3`) —
distinct bonuses stack, so a ±1-only pool could never reach the gap.

**The rule.** At the vault, when your initiative exceeds your opponent's by **3 or more**, you may
spend the turn's action to take the next Wu off the pile **into your hand, with no showdown** — and
you surrender one initiative Wu of the highest magnitude you hold (**you choose which**).

**Why it replaces the showdown.** A Showdown exists _because two hands closed on the Wu at once_. If
you were decisively faster, there is no second hand on it and nothing to fight over. A rule where you
outrun your opponent and then still duel them contradicts the fiction of why duels happen. It also
keeps the pile draining at one Wu per turn, which the rest of the ruleset assumes.

**Why it self-corrects.** The rule turns on the _difference_. A `+2` lifts you; a `−2` in your hand
drags _them_ down. Surrender either and the gap shrinks by exactly 2 — so it brakes identically
whichever you give up, and the choice (keep the speed, or keep the sabotage) is purely tactical.
One action a turn means you cannot chain it.

**What it makes initiative into.** A resource. Distinct bonuses stack and equal ones do not, so
collecting initiative means collecting _different values_ (`+1` and `+2` = `+3`). That dedupe rule has
been a curiosity in `scoring.initiative` since the beginning; this gives it a job.

**And it gives the information Wu a job.** Diaskopia and Teleskopia inform no decision the opponent
makes today — knowledge with no decision behind it is worth nothing (see `vault_ai.py`). The Early
Bird _is_ that decision: knowing what sits on top of the pile is exactly what tells you whether taking
it is worth more than fighting for it. Look, then decide whether to take it or duel for it.

**The trade.** A certain Wu with no upside, against a contested Wu with four ways to win it and the
chance to take their stakes. You make it when you think you would lose the fight — the fast, weak
hand outruns the strong one instead of dying to it.

---

## The Rooster Booster, and the lost pile

Wu that no one wins are **lost, not destroyed.** They go to a shared **lost pile**
(`XiaolinState.lost: list[Card]`), persisted in the save —
`games/xiaolin_showdown/lore/02-the-showdown.md` argues a Wu out of play resurfaces for somebody
else, and this makes it literally true.

**Rooster Booster** (`item`, 0/0/0, metal): spend it at the vault to bring the **oldest lost Wu** back
into play, into your hand. Gated when the lost pile is empty, like the other revealing Wu.

**Oldest, not random, and not your pick.**

- _Not random_, because `powers.py` says so, in capitals: the gamble Wu is the **only** card in this
  game that rolls, and a second one makes the first ordinary and the promise false. A random draw from
  a _public_ lost pile is worse than a hidden roll — it is a slot machine with the reels showing.
- _Not your pick_, because taking anything you like out of half the cards ever lost is too strong.
- **Oldest** makes the lost pile a queue **both duelists can read**. Everyone knows what the next
  Booster will fetch, so it is plannable in the open, and if you both hold one it is a race for who
  fires first. A hard choice, not a lookup.

It recovers a Wu whoever lost it — Wu die in showdowns, not to a person. The Wu your opponent failed
to take hard enough, you pick up later.
