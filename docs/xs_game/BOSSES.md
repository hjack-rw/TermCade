# Bosses

The boss roster — a difficulty above hard. **Each boss is a different mechanic family**, so each
tests a different player skill; you don't grind the same fight harder.

## The roster

| Boss | Archetype | Mechanic |
|---|---|---|
| **Hannibal Roy Bean** | elemental | wudai Morpher + metal resonance (boost grounded: nets 1/1/1 in tune) |
| **Chase Young** | stat | 7/7/7; Beast Form (+1 on the contested stat, his Wu score nothing); a WU-PLAY win gifts the prize, the beast KEEPS it |
| **Wuya** | Shen Gong Wu | 6/6/6 witchcraft: spent Wu return worn; recalls the oldest lost, 3 a run; +1 initiative |
| **Jack Spicer** | bots | constructs, steal, mode-swaps, a majority-of-3 Brawl, a flee, a training lever |

## Current ladder

| tier | player win | showdowns/run |
|---|---|---|
| Easy | **92.4%** | 14.6 |
| Hard | **47.0%** | 14.2 |
| Hannibal | **14.6%** | 8.2 |
| Wuya | **10.6%** | 9.2 |
| Chase | **5.2%** | 7.5 |
| Jack Spicer | **22.2%** | 8.8 |

Easy/Hard deal a random roster (no boss picker, no scenario weighting — see "Bosses are picked, not
random" below) and are tracked here as the baseline the boss tier sits under.

Chase/Wuya/Hannibal are all harder than the hard tier, deliberately — **three distinct mechanics at
one difficulty**, not a ladder to flatten toward each other.

**Jack sits apart from that trio by design** — the intentionally weakest boss, both in the mechanic
(bots are an obstacle he causes the opponent, not a self-buff) and the numbers.

Full measurement methodology and history: `docs/design/BALANCE-HISTORY.md`.

---

## Jack Spicer — bots

**Heylin, 3/3/7.** The 7 is the intellect wall — hard to beat on int by design (magnitude 5 is the
normal ceiling; a boss is allowed past it). When he holds priority he names intellect and fights at 7
base, doubled on the contested stat.

### The bots — one chassis, five effects

Metal **resonates** on a metal ground (buff), **suffers** on every other one (debuff — metal has no
true opposite), so background choice is the counterplay to the kit. Jack is a trickster, not an open
fighter: the bots are an obstacle he causes the opponent, never a help for himself — a self-buff has
to come from an ordinary Wu in hand instead, Jack-Bot itself only ever curses.

| Bot | Effect |
|---|---|
| **Jack-Bot** | permanent wudai boost, always curses the opponent −1/−1/−1 metal, one of 4 rotating flavour names, never twice in a row |
| **AI Jack** | normal duel + steal the opponent's strongest hand Wu (random deck card if the hand is empty); mode and theft both resolve at commitment, before either side has fielded a Wu; fires only when Jack leads |
| **Chamelon-Bot** | a boost, not a base override — raises Jack's stat on the one stat this battle contests, never below his own, never touching the other two; fires whenever the player leads |
| **Jack-bots Attack!** | a "Brawl" — never named, never a tournament. Jack fights as a 3/3/3 metal construct; each side independently wagers 0-3, blind to the other. Winner takes the prize outright, no prize-cascade ladder |
| **Flee** | fighting as himself only, Jack concedes a showdown he has already lost: he keeps his own wager, nothing else changes — the prize still resolves through the normal cascade; capped at 3 free flees a run |

**Mode decision**: Attack! rolls first. Missing that, priority decides which stand-in is on the
table — Chamelon-Bot whenever the player leads (unconditional), AI Jack when Jack leads (gated so he
cannot spam a stand-in two showdowns running — Chamelon-Bot may still fire every showdown the player
leads).

### Training

He is the only boss for whom the training bar's loss-fill does anything: force/agility sit under the
stat cap unlike the other three (already maxed on every stat). One loss fully fills his bar and pays
out immediately. Force alone stops one short of the cap; agility trains to the full cap like any
dragon. Fully trained he tops out at **4/5/7**: agility genuinely matches a dragon's own, force stays
a permanent real gap.

**Economy:** Jack-Bot permanent; AI Jack/Attack! one-use each per showdown they fire; flee capped at
3 per run.

**Flavour split:** Jack's own character power reads "Jack Spicer, evil boy genius, built himself a
robotic army to fight his battles for him. Versatile and ALMOST infallible." — the card's own power
(same mechanic, named "Robotics") reads "Customary robots created and used by Jack. Building them
comes naturally to him."

### Counters — four keyed answers, all METAL ITEM

- **Denshi Bunny** — vs Jack shown as a bot (AI Jack, Attack!): auto-wins the showdown outright,
  since Jack himself was never the one fighting. Vs Chamelon-Bot: nullifies its boost instead — Jack
  IS fighting, just without the denial. Vs Jack-Bot's curse: nullifies it too. Mala Mala Jong is
  fully immune.
- **Sands of Time** — takes the opponent's strongest hand Wu, or a random deck card if the hand is
  empty. Open to whoever plays the card, not gated to Jack.
- **Shard of Lightning** (aka "Thorn of Thunderbolt") — +1 to the stat this battle contests per metal
  Wu on the table (either side, boosts and inert curse mirrors alike), -1 per non-metal one; the
  arena counts the same way once decided. Uncapped either way, balanced by the -1 penalty rather than
  a ceiling.
- **Ying Yo-Yo / Yang Yo-Yo** — names a stat, swapped between the caster's Character and the
  opponent's for the rest of the showdown. Also flips the caster's own affiliation for the rest of
  the run, toggled by playing another Yo-Yo. **Jack is the exception**: flipping him swaps Evil Jack
  with Good Jack (deliberately dumber, 4/4/4 base) instead of a plain affiliation flip. Jack can't
  deploy any bot form while worn as Good Jack.
- **Ying-Yang Yo-Yo** — built only by combining both halves at the temple (spends the turn's
  action); excluded from the draw pool entirely, so it is never dealt. Same stat swap as the halves,
  but the affiliation flip targets the opponent instead of the caster. Held (not played), it offers a
  separate temple power to flip the caster's own affiliation back — exiled for good either way, win
  or self-correct.

### Bot-AI

Jack's bot opponent banks any of his five counters the instant he holds one — stolen or drawn — ahead
of the normal points-first deposit rule, and prefers stealing a counter Wu outright over a
numerically stronger ordinary one. It also plays counter Wu it holds *for their effect* rather than
just their printed stats: a Shard of Lightning is fielded for its live table bonus, a Steal/Seize
card is preferred over a stat-better pick when doing so doesn't cost the fight or its prize. The moment
he's worn as Good Jack and holds the combined Ying-Yang Yo-Yo, he spends the temple action to flip
back — unconditional, since Good Jack forfeits every one of his bot forms while worn.

---

## Hannibal Roy Bean — elemental

**Heylin, 5/5/5.** His power is **Elemental Manipulation**: he holds **Moby Morpher** as a wudai —
always in hand, boost-only, unlosable — and deflects the elements, so his own Wu ignore the arena's
drag. The wudai mechanic makes a morph a **boost**, not just a play: a flat 1/1/1 of its chosen
element, and Hannibal always picks the arena's own element, so he is permanently in tune (+1/+1/+1
and a guaranteed elemental bonus, on a 5/5/5 body). Fielded from the pool (not his own inalienable
copy) it keeps its plain 2/2/1 shape.

**Countered by combination, not any single card** — one counter alone is weak, but the full
five-counter set held every showdown takes him from near-zero to about even odds. The five: **Star
Hanabi** (negate a boost's stats), **Lunarkinesis / Celestial Dial Locket** (reverse the elemental
bonus), **Kuzusu Atom** (force metal), **Eye of Dashi** (set your own element), **Monsoon Sandals**
(recolour the arena). In the pool, drawn naturally, the full set is rare enough that its effect
barely shows — availability, not power, is what keeps him hard.

**Bot-AI**: Hannibal banks one of his five counters outright the instant he holds one, getting it out
of the player's reach ahead of the normal points-first deposit rule. He has no steal power, so only
the deposit half applies to him. His own five counters are also weighted to be dealt more often, so a
run against him is more likely to actually offer the player an answer.

---

## Chase Young — stat

**Heylin, 7/7/7, and he refuses the Wu.** His power is **Beast Form**: a per-showdown choice between
two modes.

- **Beast Form ON** — a stat boost to one contested stat (once a fight; a tournament boosts only one
  of the three legs). His Wu are ALL dead — wagered, never wielded, no offence/curse/boost line.
  **Keeps** the prize on a win.
- **Beast Form OFF** — an ordinary duelist, Wu score normally. 
  **Gifts** the prize to the duelist he
  beat on a win ("The Good Guys Finish Last") — the cost of not beasting.

He beasts when his lead on the tightest contested stat is under a margin, else stays an ordinary
duelist. At the temple he only draws or deposits — no powers, no Early Bird ("meddles in no mortal
affairs").

**Counter: Sphere of Jianyu** — a general pool card that zeroes a side's own character stats
entirely, exactly the contribution Beast Form ON lives on (his Wu already score nothing in that mode,
so it isn't touching a second line of offence). He has no steal power, so only the deposit half of
the "wary of counters" bot behaviour applies to him, and his one counter is weighted to be dealt less
often than it would be naturally — deliberately rare, so beating him stays about finding that one
answer.

---

## Wuya — Shen Gong Wu

**Heylin, 6/6/6, +1 initiative.** Built on **Witchcraft**: a Wu she spends on its power comes back to
her hand worn (a third use vaults it), and a temple action **recalls the oldest lost Wu**, a limited
number of times a run, when its value clears a minimum. She also has a weak-Wu Early Bird.

**Recall is gated by supply** — the lost pile is empty most of the time, so she recalls in under half
of all runs; there is nothing that reliably fills the pile faster.

**Her second ability (a spent power returning the Wu) fires rarely** — a boss run usually resolves
through drawing, the Early Bird and banking before it ever reaches the power-use branch.

**No keyed counter today.** One pool card's flavour text names her directly — Mosaic Scale Puzzlebox
("Traps spiritual bodies, such as Sibini or Wuya") — but its mechanic is a plain deposit-value effect,
nothing active against her Witchcraft. No other card targets a spent Wu returning worn, the lost-Wu
recall, or her initiative bonus.

---

## How bosses differ from an ordinary opponent

- **Bosses are picked, not random.** Easy and Hard deal a random opponent; a boss is chosen on
  purpose, because each is a distinct mechanic worth choosing rather than stumbling into.
- **Pick-one-and-fight, not a gauntlet.** Each boss is a standalone run. Beating all four is "100%
  the game."
- **Boss-run asymmetry favours the player, but stays inside the normal rules** — never raw duel
  stats (that would break the magnitude-5 cap everything else respects). The legal asymmetry is the
  training bar: a loss teaches the player faster against a boss than an ordinary opponent, and the
  player gets more temple actions a turn than the boss does. Most bosses sit at the stat cap already
  and can never collect any training at all — Jack is the one exception, see his Training section.
- **Rewards and unlocks are deferred** — beating a boss doesn't yet unlock anything; that needs a
  stored save record this project doesn't have yet.
