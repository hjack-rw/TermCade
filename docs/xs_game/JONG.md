# Mala Mala Jong — the assembly win-condition

**Built and shipped.** The Heart of Jong (card 74, `ANIMATE`) seeds the mechanic described below,
implemented in `games/xiaolin_showdown/logic/characters/jong.py`.

Mala Mala Jong is not a fielded Wu — it is a **character transformation** a duelist earns mid-run by
holding a full set of body parts. It converts the run into a race: transform, then reach the end of the
game in the form, and win outright.

## The parts

The card `type` column (`head/torso/arms/boots/amulet`) **is** the assembly slot — one Wu of *each*
type, any Wu of that type counts. The slot is otherwise cosmetic; **do not repurpose it**. Counts in the
pool (the difficulty dial — torso is the gate):

| slot | count |
| --- | --- |
| amulet | 7 |
| arms | 6 |
| head | 5 |
| boots | 4 |
| torso | 3 |

Ramp: **3 / 4 / 5 / 6 / 7** (torso→amulet), shipped. Shroud of Shadows was demoted `amulet`→`item`
to land amulet at 7.

## Assemble — the temple power "Construct Mala Mala Jong"

**Gate:** hold one Wu of each of the five slot-types **and** the Heart of Jong, all in hand. Then a
temple power appears. Spending it:

- **The character becomes Mala Mala Jong** — stats **6/6/6** (Wuya-tier; Chase is 7/7/7), name and
  affiliation shown as `construct`. Underneath the real affiliation (xiaolin/heylin) is kept: the
  boss-training asymmetry, the roster tier and the `{spirit}` faction pool still see the *real* duelist
  (still Omi, etc.), not "Mala Mala Jong". The `construct` is a costume.
- **`{fear}` and `{desire}` are the exception — they read the construct.** While in form the pools key
  off "Mala Mala Jong", not the duelist underneath: a Shadow of Fear played *on* Jong summons **Jong's**
  fear, a `{desire}` summon Jong casts conjures **Jong's** desire.
  - **Fear:** `the Shen Gong Wu Vault` — he dreads being disassembled and forgotten.
  - **Desire:** branches on the real side under the costume — Xiaolin → `World Peace`, Heylin →
    `World Domination` (placeholder; off-theme against a pool of beings, and near-unreachable in form
    since the Cat's Eye is purged on construct). So `{desire}` keys to Jong, then Jong reads the real
    affiliation to pick which.
- **Hand purge:** keep the five body parts **and** any wudai weapons; every *other* Wu in hand is
  deposited (→ points).
- **The Heart goes out-of-play** — it powers the form and cannot be restored or recalled by anyone while
  Jong is active.

**Xiaolin are harder to build it.** The set is six cards (5 parts + Heart) and `max_hand_size` is 6 — a
full hand with no slack. The **Third-Arm Sash** (`hand_size`, +1 → 7) is a Xiaolin's only way to hold
the full set with room to assemble it. *(Confirm the exact hand-math at build: whether 6 is a hair too
tight, or the heylin side simply has the room. The intent is: Xiaolin path runs through the Sash.)*

## The locked state (until game end or form-drop)

- No new Wu into hand or deck · no drawing · no swapping.
- Every **won** Wu **auto-deposits** (→ points, never kept). The hand only shrinks.
- Wudai weapons stay in hand but **Jong cannot use them**.
- **The form holds only while the set is whole.** Any card leaving Jong's hand — a lost wager, a steal,
  a Bounce/Repulsion, a Transfer, a discard — **drops the form**. Powers that remove or move his cards
  are the counter class.

## A showdown as Jong

- Base **6/6/6**, and the body parts he wagers **stack on it normally** — base + fielded Wu, like any
  duelist. Up to **3** parts, so a full wager is 6/6/6 *plus* three parts' stats.
- Boosts **only** with the Heart of Jong — as *itself*, **1/1/1, element metal, one battle** (not the
  ANIMATE summon form). A boost-type part (e.g. Wushu Bracelet) can therefore only be **wagered** as a
  Wu, never boosted.
- **Emperor Scorpion played on him → auto-wins that battle.** The hard counter (it disables Wu
  constructs; its DB text already names Mala Mala Jong).
- His fielded Wu are otherwise still nullifiable normally.

## Winning and losing

- **Game ends while in the form** — *either* duelist reaches the point limit → **you auto-win.** This is
  the whole point: transform, then race the game to its close.
- **Jong loses a showdown (or the set is broken)** → the **form drops**, the duelist reverts to their
  real character, and the **winner takes the wagered parts + the Heart of Jong** (the Heart re-enters
  play in the winner's hands, released from out-of-play).

## The Heart of Jong — one card, two contexts

Same Wu (card 74); what it does depends on how it is played. It is never a "normal" Wu play by intent —
its jobs are the boost and the Jong construct — but it *can* be fielded.

- **Fielded as a Wu (card slot):** a middling **2/2/2**, element metal, its own name. Weaker than boosting
  it — no summon, no arena element.
- **Boosted (normal use):** adds a **separate summon** into the battle — the arena-element form
  (Raksha/Cyclops/Bird of Paradise/Gigi/T-Rex), **3/3/3**, in the arena element (so metal arenas lift it).
  It is a *separate fighter*, not an amplifier: the board shows it with **`&`**, never `+`. Boosting it
  lets the **opponent field one extra Wu** in that battle — but this Wu is **not part of the wager, it is
  balance**: it scores, yet it is **never staked** (it cannot be lost even if that side loses), it is
  **optional** (take it or pass), and it applies only if they *have* a spare Wu. So the wager loop is
  untouched — this is an off-wager fielding. The Heart can be boosted **alone** (no committed Wu) → the
  summon fights solo.
  - **Tournament:** per battle — boost the Heart in all three and the opponent gets an optional extra in
    each.
- **As Jong's boost:** **1/1/1 metal**, as itself (no summon). The opponent-+1-Wu combo does **not** apply.

## Both sides build it

Anyone can construct Jong — the player or the bot. A boss is already 6/6/6, so for them it is lateral
(and costs their hand); for a Xiaolin it is a genuine power spike gated behind the Sash.
