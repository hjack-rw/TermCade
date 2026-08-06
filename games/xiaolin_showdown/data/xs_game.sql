-- The Xiaolin Showdown card catalog — every Wu, power, character and place in the game.
--
-- This file and `xs_game.db` hold the same rows, and each can be rebuilt from the other. Edit
-- WHICHEVER IS EASIER — a card table is far nicer to work in through a DB browser than as forty
-- columns of INSERT — then regenerate the other one:
--
--   edited the .sql  ->  python build_cards.py   (writes the .db)
--   edited the .db   ->  python dump_seed.py     (writes this file)
--
-- Both are committed: the seed so a new Wu is a readable line in a diff, the .db because the
-- packaged exe and the wheel bundle it as package data and neither runs a build step. Two committed
-- files can drift, so `test_seed.py` fails the moment they disagree — run the matching script and
-- commit both. A dump is byte-stable (rows ordered by id), so a rerun never churns the diff.
--
-- Card ids are contiguous and load-bearing, in two ways:
--   * `setup.new_game` deals the draw pile from ids FIRST_DECK_CARD..N, indexing the card list
--     by id — a gap deals the wrong card.
--   * A character is granted its signature Wu by `card.id == abs(character.power_id)`. Cards 1-4
--     *share* that power (Omi is the Dragon of Water). Moby Morpher (card 5) and Jack-Bot (card 0)
--     do not: Hannibal's own power is "Free Allomorphia" (-5), the Wu's is "Allomorphia" (30); Jack's
--     own power is "Jack-Bot" (-8), the Wu's is "Robotics" (0) — the character holds the Wu, it is
--     not the Wu, so both are resolved by mechanic in `setup._reserve_signature`, not by id.
-- Every card and power id 5+ (and 1+ for powers) is also grouped by mechanic, ascending — every Wu of
-- the same mechanic sits together, so a browser scanning by id reads it as one balance pass. A new Wu
-- of a mechanic already in the table is a REGROUP, not a bare append: renumber it in next to its
-- siblings and shift every id after it forward by one, on both `card` and `power`, updating every
-- hardcoded reference (see `tests/games/xiaolin_showdown/card_ids.py` and the signature/save-file
-- notes above — a save on disk stores raw ids with no remap layer, so a renumber invalidates old
-- saves). A new MECHANIC's first Wu still just appends at the end, since there is no group yet to
-- join. The negative ids (dragon/boss signatures) are a separate space and never move. Card 0 (Jack's
-- own wudai) and power 0 (its `bot` power, "Robotics") are an exception inside the mechanic-grouped
-- run: reserved, the way power -8 already was, so Jack's card sits where a player instinctively looks
-- for "the character's own Wu" first. Power 84 ("blank", `filler`) is the true no-power placeholder
-- six ordinary Hard-roster opponents (Tubbimura, Katnappé, Salvador_Cumo, Vlad, Le_Mime, PandaBubba)
-- point `power_id` at — it is NOT card 0's power, and must never collide with a real mechanic's id
-- (`Mechanic.BOT` id 0 is real; power 84 fires nothing, per `mechanics.powers.RULES[Mechanic.FILLER]`).
--
-- A power NAMES its mechanic, and `mechanics.powers.RULES` says what that mechanic does, when it
-- fires, and what it tells a player. A name nobody implemented fails at LOAD (`Mechanic(row)`),
-- rather than becoming a Wu that quietly does nothing. There is no trigger column and no effect
-- integer: when a power fires follows from what it is.
--
-- `mechanic_config` holds the numeric balance knobs a mechanic applies — a card mechanic's, to every
-- Wu that carries it (the Gamble's payout spread, the Morpher's dip, the Heart's boosted/fielded
-- stats), or a character's own power, whatever shape it takes (Beast Form's boost AND its trigger
-- margin; Wuya's witchcraft recall margin/cap and her own Early Bird gap; Jack's whole `bot` persona
-- system — stat, flee cap, Attack!'s odds and momentum — everything he *is*, not just what he prints).
-- Excluded: `flow.temple_ai`'s generic opponent heuristics (ATTRACTION_MARGIN and friends) — those
-- gate the bot's use of any Wu carrying a mechanic, not what one character's own power does, and stay
-- code. `mala_mala_jong`'s construct stats sit under the synthetic key `jong` — no power names it (it
-- is 5 typed Wu plus the Heart, not a single mechanic), but it is still made of cards, so it belongs.
--
-- Read once at import by `mechanics.powers` (`flow.duel` re-exports `BEAST_BOOST` from there so the
-- DB is read in one place; `characters.chase/jack/jong/wuya` import their own knobs from it the same
-- way) — editing a row here changes the number everywhere it is quoted, text included, with no code
-- change. A row for a mechanic nothing reads is inert, not an error. `key` distinguishes multiple
-- knobs on one mechanic (Gamble's `low`/`high`); `MORPH_CONTESTED` stays derived from `morph.aside` in
-- code, not its own row, since it is not an independent number (see `mechanics.powers`).

-- ----------------------------------------------------------------------------
CREATE TABLE "power" (
	"id"	INTEGER,
	"name"	TEXT,
	"mechanic"	TEXT NOT NULL,
	"description"	TEXT,
	"initiative_bonus"	INTEGER NOT NULL DEFAULT 0,
	"summon"	TEXT,
	"train_step"	INTEGER NOT NULL DEFAULT 0,
	PRIMARY KEY("id")
);

INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (-8, 'Jack-Bot', 'bot', 'Jack Spicer, evil boy genius, built himself a robotic army to fight his battles for him. Versatile and ALMOST infallible.', 0, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (-7, 'Beast Form', 'beast_form', 'Going over to the dark side, Chase became infused with the power of a Heylin Demon. He refuses however to meddle in mere mortal affairs.', 0, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (-6, 'Witchcraft', 'witchcraft', 'Wuya''s connection to the Shen Gong Wu runs both ways. She can call the lost Wu back into her hand, three times in a run, and a Wu she spends on its power returns to her hand. But the hunger that finds them is never fed.', 1, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (-5, 'Elemental Manipulation', 'morph', 'Given his condition of being a literal Heylin Bean, Hannibal took a hold of Moby Morpher and never let it go - so he wields it as a free Wu. He is also capable of Elemental Deflection.', 0, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (-4, 'Dragon of Earth', 'dragon', 'User has access to basic Earth-based attacks, and moves.', 0, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (-3, 'Dragon of Fire', 'dragon', 'User has access to basic Fire-based attacks, and moves.', 0, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (-2, 'Dragon of Wind', 'dragon', 'User has access to basic Wind-based attacks, and moves.', 0, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (-1, 'Dragon of Water', 'dragon', 'User has access to basic Water-based attacks, and moves.', 0, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (0, 'Robotics', 'bot', 'Customary robots created and used by Jack. Building them comes naturally to him.', 0, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (1, 'Retrokinesis', 'amend', 'Winds a recent moment back a heartbeat, undoing the user''s last action so a mistake can be taken back and made afresh.', 0, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (2, 'Anthropomorphism', 'animate', 'Brings inanimate or dead objects to life - but only while it is active, a life on loan so to speak. Used to create powerful constructs like Mala Mala Jong.', 0, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (3, 'Power Augmentation', 'boost', 'Could greatly enhance the powers of other Wu that the user is holding. It combines with it, making it count as one in a duel.', 0, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (4, 'Repulsion', 'bounce', 'Allows the user to telekinetically push targeted objects (opposite of the Glove of Jisaku).', 0, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (5, 'Hydrokinesis', 'buff', 'Releases a large flood of water, that can also be frozen into ice.', 0, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (6, 'Ying-Yang World Access', 'chi_swap', 'Allows the user to travel into the Yin-Yang World. Can change someone else''s Chi at will.', 0, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (7, 'Metallaxis', 'cleanse', 'Transforms an object''s alchemical properties by changing its atoms - turning it to inert metal for example.', 0, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (8, 'Astrapokinesis', 'conduct', 'Shoots out thunderbolts. Can be used as a powerful energy source.', 0, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (9, 'Thyellokinesis', 'double_element', 'Allows the user to generate or manipulate strong winds and tornados (leting its user to become a walking hurricane), but the sword itself cannot be used for physical attacks as it phases through enemies.', 0, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (10, 'Klonogenesis', 'double_training', 'Multiplies the user into as many as nine people, but it also divides up the user''s skills (and mental prower is a skill) among all the clones.', 0, 'Clone of {caster}', 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (11, 'Polymorphia', 'dragon', 'Transforms into any weapon the user requires.', 0, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (12, 'Chronokinesis', 'draw', 'Freezes anything it is pointed at in time and place for a short while.', 0, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (13, 'Oxyderkia', 'enhanced_vision', 'Alows for different kinds of vision (thermal or even sound).', 0, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (14, 'Attraction', 'fetch', 'Allows the user to attract any object toward themselves, including other Shen Gong Wu.', 0, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (15, '? ? ?', 'gamble', '? ? ?', 0, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (16, 'Electrokinesis', 'hack', 'Transforms the user into electricity, meaning they can possess and control technology.', 0, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (17, 'Temporary Appendage', 'hand_size', 'Acts like an extendable, strong, and durable third arm. Its moves are somewhat independent from the wearer, but always obey their commands.', 0, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (18, 'Furious Charge', 'initiative', 'Bull horn that when blown blasts the user at rapid speeds forward at their target (aka a "DASH-i").', 1, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (19, 'Levitation', 'initiative', 'Allows the user to defy gravity, which enables them to walk vertically on walls and even float minimal above ground.', 1, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (20, 'Camouflage', 'initiative', 'Helps its user blend into their surroundings like a chameleon.', 1, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (21, 'Mégathoskinesis', 'initiative', 'Shrinks targeted objects or people to the size of a grain of rice. The size change is not permanent and requires the user to keep a hold of the Wu.', 1, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (22, 'Tongue Twister', 'initiative', 'Makes the user''s enemies babble nonsense non stop. The effect prevents them of taking coherent actions.', -2, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (23, 'Self-conscious Rope', 'initiative', 'Rope that can fulfill simple orders, behaving like a snake while at it. Apart from that it possess all the abilities of an ordinary rope.', -1, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (24, 'Extendable Tendrils', 'initiative', 'It shoots a stream of hair from the comb''s teeth at the intended target and binds it. However, it requires complete focus from the user as you need to control each hair separately.', -1, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (25, 'Méllissakinesis', 'initiative', 'When opened, unleashes a swarm of insects (e.g. ants, flies, bees) at a desired target.', -1, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (26, 'Metáxikinesis', 'initiative', 'Allows the user to fire strands of spider-like silk. The user himself is immune to its stickiness, but opponents will be rendered immobile for a short while. Can also be used to swing from place to place on the slik string.', -1, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (27, 'Astrapokinesis', 'initiative', 'For as long as the coin is in the air the user moves at the speed of light, and everything else is standing still.', 2, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (28, 'Supersonic Flight', 'initiative', 'Carries its user at supersonic speed.', 2, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (29, 'Invisibility', 'initiative', 'Renders its user unseen.', 2, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (30, 'Reality Cutting', 'initiative', 'Cuts through anything, reality included: a clawed portal opens onto any place the user names, and stays open a short while – long enough that others may follow, until reality mends itself.', 2, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (31, 'Blinding Glare', 'initiative', 'Throws up a glittering sphere of light that nobody can look away from and nobody can see past.', -2, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (32, 'Stupefaction', 'initiative', 'Releases a purple gas that leaves its victims confused and foolish, or drops them into a deep sleep outright.', -2, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (33, 'Efiáltiskinesis', 'initiative', 'Walks into a sleeping mind and gives its worst fear a body. It has no hold on anyone awake.', -2, '{fear}', 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (34, 'Shadowstep', 'initiative', 'Allows the user to jump between shadows or dark places.', 2, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (35, 'Vaporization', 'initiative', 'Lets its user turn into a cloud of dust or even liquid, able to pass through narrow openings. It can also create the type of gas or liquid at will.', 1, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (36, 'Elasticity', 'initiative', 'Allows the user''s body to stretch and twist like rubber, making them extremely flexible.', -1, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (37, 'Arktophylaxia', 'initiative', 'Wraps its user in a polar bear fur suit that withstands extremely cold temperatures and resists physical damage.', -2, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (38, 'Avian Flight', 'initiative', 'Grants the user the power to fly like a hawk.', 2, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (39, 'Hyperjump', 'initiative', 'Allows the user to jump incredible heights and distances like a kangaroo.', 1, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (40, 'Myiomorphosis', 'initiative', 'Transforms the user into a tiny fly, also giving them a craving for sugar.', -1, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (41, 'Nyktoskopia', 'initiative', 'Lets its user hang upside down like a bat without nausea, and lets them see well in darkness.', -2, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (42, 'Superhuman Strength', 'innate', 'Allows the user to punch with incredible force, capable of creating shock waves during the impact.', 0, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (43, 'Deflection', 'innate', 'Protects the user''s head by deflecting attacks and projectiles towards it.', 0, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (44, 'Photographic Memory', 'innate', 'Grants its user an instant memory recall. The memories are stored in bubbles inside the Wu and can be shared across users.', 0, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (45, 'Impenetrable Defence', 'innate', 'Can temporarily transform into an armor capable of blocking all sorts of attacks, but its weight increases drastically while active.', 0, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (46, 'Umbrakinesis', 'innate', 'Allows for shadow manipulation that can influence a physical target. It can absorb and dissipate shadows at will, allowing the user to create shadow copies when it''s charged up.', 0, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (47, 'Mnenokinesis', 'innate', 'Erases memory for a short while, leaving its victim unable to recall what they knew.', 0, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (48, 'Euthymia', 'luck', 'Your good spirits turn fortune your way and a lost Wu finds its way back to you.', 0, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (49, 'Misfortune', 'misfortune', 'Creates ironic or down-right unlucky situations for all of its user''s opponents.', 0, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (50, 'Allomorphia', 'morph', 'Allows the user to change their appearance into anything they choose - including the appearance of other beings.', 0, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (51, 'Thermokinesis', 'nullify_boost', 'Shoots out sparks that generate heat and can light fires, the sudden bloom of warmth smothering an opponent''s boost.', 0, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (52, 'Reversal', 'nullify_curse', 'Reverses the powers of anything that is binary, including other Shen Gong Wu (e.g. the Two-Ton Tunic becomes as light as a feather).', 0, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (53, 'Intangibility', 'nullify_element', 'Makes the user a ghost, allowing them to pass through solid objects and avoid physical attacks, but it doesn''t protect against non-physical attacks.', 0, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (54, 'Containment', 'nullify_stats', 'Traps the target in an impervious transparent sphere. It also copies authority and possessions from the prisoner to the user.', 0, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (55, 'Subjugation', 'nullify_wu', 'Allows the user to control or disable all other Shen Gong Wu, including multiple Wu constructs like Mala Mala Jong.', 0, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (56, 'Telepatheia', 'prognosis', 'Allows the user to hear the thoughts of other people whom the shell is aimed at.', 0, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (57, 'Diaskopia', 'read_deck', 'Allows the user to see through solid objects. The user may enhance the ability further by using its sister Shen Gong Wu, the Eagle Scope.', 0, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (58, 'Palingenesis', 'refresh', 'Heals any injury. Also regenerates aging over time.', 0, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (59, 'Lunarkinesis', 'reverse_element', 'Allows the user to control the sun, the stars and the moon, including their different phases.', 0, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (60, 'Teleskopia', 'scry', 'Transforms into a telescope, granting the user eagle-like long range vision. It is the sister Shen Gong Wu to the Falcon''s Eye.', 0, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (61, 'Seismokinesis', 'seize_ground', 'Grants the user seismic sense, and the power to open earthquakes or fissures at will - taking the ground itself.', 0, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (62, 'Anemokinesis', 'set_arena', 'Controls the weather, changing the arena''s element to the one the user calls.', 0, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (63, 'Chromakinesis', 'set_element', 'Shoots any random element from the center gem. Making Wu gain elemental powers. Also causes combustion.', 0, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (64, 'Hypersthenia', 'stat_shield', 'Grants the user super strength.', 0, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (65, 'Proaisthesis', 'stat_shield', 'It warned its user of impending danger.', 0, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (66, 'Gnoseokinesis', 'stat_shield', 'In form of a crown, grants the user infinite, but random knowledge. It can also grant perspective and sentience to an unintelligent beast. To gain specific knowledge use it with the Wushu Brcelet.', 0, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (67, 'Chi Reversal', 'stat_swap', 'When the Yo-Yo is broken into two parts, the user is still able to travel to the Yin-Yang World, but upon their return they will lose their predominant Chi and undergo a personality reversal.', 0, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (68, 'Temporokinesis', 'steal', 'Manipulates time, allowing short-term time travel to explore outcomes not yet set in stone, or to temporarily summon oneself from another point in the timeline.', 0, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (69, 'Zooglossia', 'train_boost', 'Grants the user the ability to talk to and understand animals, and to call a host of them to their side.', 0, '{beast}', 3);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (70, 'Empsychosis', 'train_boost', 'With just a look it could bring drawings to life, sketching a creature into being to fight at your side.', 0, '{drawing}', 3);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (71, 'Nekrokinesis', 'train_boost', 'Turns targets into mindless, obedient zombies, raising a shambling horde to do the user''s bidding.', 0, 'a Horde of Zombies', 3);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (72, 'Ensomatosis', 'train_boost', 'Calls spirits back from the Yin-Yang World and clothes them in temporary physical bodies, free to roam the Earth without possessing the living.', 0, '{spirit}', 6);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (73, 'Phantopoeia', 'train_boost', 'Turns the real unreal and the unreal real, shaping whatever the wielder imagines into being to fight at their side.', 0, '{desire}', 6);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (74, 'Agalmatosis', 'train_boost', 'Becomes a living sapphire dragon whose breath turns everyone - good, evil or indifferent - into sapphire statues, then raises them as its army. The most dangerous of all Shen Gong Wu, a last resort.', 0, 'the Sapphire Dragon', 10);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (75, 'Chi Exchange', 'transfer', 'Allows the user to control chi: for example astral project or swap two person''s souls entirly. If used on multiple people all have to be illuminated by its light.', 0, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (76, 'Chronomorphosis', 'treasure', 'Caused people to change age acording to the user (older/younger) rapidly. Can be used also to reverts a target back to its original form, such as turning oil into dinosaurs.', 0, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (77, 'Spirit Sealing', 'treasure', 'Traps spiritual bodies, such as Sibini or Wuya. There were multiple occurrences of this Wu.', 0, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (78, 'Fool''s Gold', 'treasure', 'Could produce laser beams of different colors, that could change everyone and everything color. Making people very enamoured by the object.', 0, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (79, 'Pyrophylaxia', 'ward', 'Covers the user in a shell of black bug that protects the user from extreme heat. It can also be used as a raft.', 0, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (80, 'Hydrophylaxia', 'ward', 'Allows the user to breathe underwater, transforming them into a fish-like being in the process (still can''t talk with fish).', 0, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (81, 'Anemophylaxia', 'ward', 'Grants the user the physical characteristics, as well as the acrobatic agility and balance of a monkey. If it stays active for too long it slowly transforms the user into a monkey.', 0, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (82, 'Geophylaxia', 'ward', 'Transforms the user hands into one large drill, allowing him to travel underground and break even diamonds.', 0, NULL, 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus", "summon", "train_step") VALUES (83, 'Wish', 'wish', 'A mystical chest housing the spirit of a powerful yet blind swordsman in the guise of a genie; it grants a single wish to whoever holds it, and is spent forever in the granting.', 0, NULL, 0);

-- ----------------------------------------------------------------------------
CREATE TABLE card (id INTEGER, name TEXT, force INTEGER, agility INTEGER, intellect INTEGER, power_id INTEGER NOT NULL REFERENCES power (id), element TEXT, type TEXT, points INTEGER, PRIMARY KEY (id AUTOINCREMENT));

INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (0, 'Jack-Bot', -1, -1, -1, 0, 'metal', 'wudai', 0);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (1, 'Silver Manta Ray', 1, 1, 1, -1, 'water', 'wudai', 0);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (2, 'Crest of a Sparrow', 1, 1, 1, -2, 'wind', 'wudai', 0);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (3, 'Longi Sash', 1, 1, 1, -3, 'fire', 'wudai', 0);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (4, 'Iron Bear Charm', 1, 1, 1, -4, 'earth', 'wudai', 0);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (5, 'Hodoku Mouse', 1, 1, 1, 1, 'metal', 'item', 5);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (6, 'Heart of Jong', NULL, NULL, NULL, 2, 'metal', 'item', 5);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (7, 'Wushu Bracelet', NULL, NULL, NULL, 3, 'metal', 'amulet', 3);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (8, 'Ruby of Ramses', 2, 1, 1, 4, 'metal', 'item', 2);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (9, 'Orb of Tornami', NULL, NULL, NULL, 5, 'water', 'item', 3);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (10, 'Ying-Yang Yo-Yo', NULL, NULL, NULL, 6, 'metal', 'item', 7);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (11, 'Kuzusu Atom', 2, 1, 1, 7, 'metal', 'item', 3);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (12, 'Shard of Lightning', 0, 0, 0, 8, 'metal', 'item', 5);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (13, 'Blade of the Nebula', 0, 2, 2, 9, 'wind', 'item', 3);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (14, 'Ring of Nine Xing', 2, 2, 1, 10, 'metal', 'amulet', 4);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (15, 'Shimo Staff', 1, 1, 1, 11, 'metal', 'wudai', 3);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (16, 'Bras Finger', 1, 1, 1, 12, 'metal', 'item', 2);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (17, 'Caleido-scope Glasses', 0, 2, 2, 13, 'metal', 'head', 3);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (18, 'Glove of Jisaku', 1, 1, 2, 14, 'metal', 'arms', 2);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (19, 'Ohwah Tegu Saim', NULL, NULL, NULL, 15, 'metal', 'item', 1);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (20, 'Denshi Bunny', 1, 0, 1, 16, 'metal', 'item', 4);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (21, 'Third-Arm Sash', 0, 3, 0, 17, 'metal', 'arms', 2);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (22, 'Longhorn Taurus', 3, 0, 0, 18, 'metal', 'item', 2);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (23, 'Jetbootsu', 0, 3, 0, 19, 'fire', 'boots', 2);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (24, 'Mask of Rio', 0, 0, 3, 20, 'earth', 'head', 2);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (25, 'Changing Chopsticks', 0, 1, 1, 21, 'water', 'item', 2);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (26, 'Pearl of LiBai', 0, 0, -4, 22, 'metal', 'amulet', 3);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (27, 'Lasso Boa-Boa', -3, 0, 0, 23, 'earth', 'arms', 2);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (28, 'Tangle Web Comb', 0, -3, 0, 24, 'fire', 'item', 2);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (29, 'Ju-Ju Flytrap', 0, 0, -3, 25, 'wind', 'item', 2);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (30, 'Silk Spitter', -1, -1, 0, 26, 'water', 'item', 2);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (31, 'Raijin''s Flip Coin', 0, 4, 0, 27, 'metal', 'item', 3);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (32, 'Winged Feet', 1, 3, 0, 28, 'metal', 'boots', 3);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (33, 'Shroud of Shadows', 0, 2, 2, 29, 'metal', 'item', 3);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (34, 'Golden Tiger Claws', 2, 2, 0, 30, 'metal', 'arms', 3);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (35, 'Culver Crystal', -2, -2, 0, 31, 'metal', 'item', 3);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (36, 'Woozy Shooter', 0, -1, -3, 32, 'metal', 'item', 3);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (37, 'Shadow of Fear', -2, 0, -2, 33, 'metal', 'item', 3);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (38, 'Crouching Cougar', 3, 0, 1, 34, 'fire', 'item', 3);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (39, 'Crowd of Yun', 0, 2, 0, 35, 'wind', 'item', 2);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (40, 'Lotus Twister', -1, -2, 0, 36, 'metal', 'item', 2);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (41, 'Polar Paws', -3, -1, 0, 37, 'water', 'boots', 3);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (42, 'Wings of Tinabi', 0, 4, 1, 38, 'wind', 'item', 3);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (43, 'Shen-Ga-Roo', 2, 0, 0, 39, 'metal', 'item', 2);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (44, 'Manchurian Musca', -1, 0, -2, 40, 'metal', 'item', 2);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (45, 'Vest of Komori', -1, 0, -3, 41, 'earth', 'torso', 3);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (46, 'Fist of Tebigong', 5, 0, 0, 42, 'metal', 'arms', 3);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (47, 'Helmet of Jong', 0, 5, 0, 43, 'metal', 'head', 3);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (48, 'Bubble Brains', 0, 0, 5, 44, 'metal', 'item', 3);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (49, 'Two-Ton Tunic', -5, 0, 0, 45, 'metal', 'torso', 3);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (50, 'Shadow Slicer', 0, -5, 0, 46, 'metal', 'item', 3);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (51, 'Wushan Geyser', 0, 0, -5, 47, 'metal', 'head', 3);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (52, 'Rooster Booster', 1, 1, 1, 48, 'metal', 'item', 3);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (53, 'Kaijin''s Curse', NULL, NULL, NULL, 49, 'metal', 'item', 3);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (54, 'Moby Morpher', NULL, NULL, NULL, 50, 'metal', 'arms', 4);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (55, 'Star Hanabi', 2, 2, 0, 51, 'fire', 'amulet', 3);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (56, 'Reversing Mirror', 0, 0, 0, 52, 'metal', 'item', 4);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (57, 'Serpent''s Tail', 1, 2, 1, 53, 'metal', 'item', 4);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (58, 'Sphere of Jianyu', 0, 0, 0, 54, 'metal', 'item', 4);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (59, 'Emperor Scorpion', 0, 0, 0, 55, 'metal', 'item', 4);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (60, 'Mind Reader Conch', 0, 0, 4, 56, 'metal', 'item', 3);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (61, 'Falcon''s Eye', 0, 1, 2, 57, 'metal', 'item', 2);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (62, 'Tong ku Reverso', 0, 0, 0, 58, 'metal', 'item', 5);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (63, 'Celestial Dial Locket', 1, 1, 1, 59, 'metal', 'amulet', 3);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (64, 'Eagle Scope', 0, 2, 1, 60, 'metal', 'item', 2);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (65, 'Cube of Haniku', 2, 1, 0, 61, 'earth', 'item', 3);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (66, 'Monsoon Sandals', 1, 1, 1, 62, 'metal', 'boots', 3);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (67, 'Eye of Dashi', 2, 2, 2, 63, 'metal', 'amulet', 4);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (68, 'Mikado Arms', 3, 0, 0, 64, 'metal', 'amulet', 3);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (69, 'Ninja Tabi', 0, 3, 0, 65, 'metal', 'torso', 3);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (70, 'Fountain of Hui', 0, 0, 3, 66, 'metal', 'head', 3);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (71, 'Ying Yo-Yo', NULL, NULL, NULL, 67, 'metal', 'item', 3);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (72, 'Yang Yo-Yo', NULL, NULL, NULL, 67, 'metal', 'item', 3);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (73, 'Sands of Time', 2, 0, 2, 68, 'metal', 'item', 5);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (74, 'Tongue of Saiping', 2, 0, 2, 69, 'metal', 'item', 3);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (75, 'Imo Gazer', -1, 3, 1, 70, 'metal', 'item', 3);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (76, 'Zing Zom-Bone', 0, -2, -1, 71, 'metal', 'item', 3);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (77, 'Monarch Wings', 2, 2, -1, 72, 'metal', 'item', 4);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (78, 'Moonstone Cat''s Eye', 1, -1, 3, 73, 'metal', 'item', 4);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (79, 'Sapphire Dragon', NULL, NULL, NULL, 74, 'metal', 'item', 5);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (80, 'Sun Chi Lantern', 0, 0, 0, 75, 'metal', 'item', 5);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (81, 'Sweet Baby Among Us', 1, 0, 0, 76, 'metal', 'item', 5);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (82, 'Mosaic Scale Puzzlebox', 0, 1, 0, 77, 'metal', 'item', 5);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (83, 'Prism of Genesis', 0, 0, 1, 78, 'metal', 'item', 5);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (84, 'Black Beetle', 0, 1, 2, 79, 'fire', 'item', 2);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (85, 'Gills of Hamachi', 0, 2, 1, 80, 'water', 'item', 2);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (86, 'Monkey Staff', 1, 2, 0, 81, 'wind', 'item', 2);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (87, 'Tunnel Armadillo', 2, 1, 0, 82, 'earth', 'item', 2);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (88, 'Treasurebox of the Blind Swordsman', 0, 0, 0, 83, 'metal', 'item', 10);

-- ----------------------------------------------------------------------------
CREATE TABLE "character" (
	"id"	INTEGER,
	"name"	TEXT,
	"force"	INTEGER,
	"agility"	INTEGER,
	"intellect"	INTEGER,
	"power_id"	INTEGER,
	"affiliation"	TEXT,
	"is_playable"	INTEGER,
	"tier"	TEXT,
	PRIMARY KEY("id" AUTOINCREMENT),
	FOREIGN KEY("power_id") REFERENCES "power"("id")
);

INSERT INTO character ("id", "name", "force", "agility", "intellect", "power_id", "affiliation", "is_playable", "tier") VALUES (1, 'Omi', 5, 5, 2, -1, 'xiaolin', 1, NULL);
INSERT INTO character ("id", "name", "force", "agility", "intellect", "power_id", "affiliation", "is_playable", "tier") VALUES (2, 'Raimundo', 4, 4, 4, -2, 'xiaolin', 1, NULL);
INSERT INTO character ("id", "name", "force", "agility", "intellect", "power_id", "affiliation", "is_playable", "tier") VALUES (3, 'Kimiko', 3, 4, 5, -3, 'xiaolin', 1, NULL);
INSERT INTO character ("id", "name", "force", "agility", "intellect", "power_id", "affiliation", "is_playable", "tier") VALUES (4, 'Clay', 5, 3, 4, -4, 'xiaolin', 1, NULL);
INSERT INTO character ("id", "name", "force", "agility", "intellect", "power_id", "affiliation", "is_playable", "tier") VALUES (5, 'Tubbimura', 5, 3, 3, NULL, 'heylin', 0, 'easy');
INSERT INTO character ("id", "name", "force", "agility", "intellect", "power_id", "affiliation", "is_playable", "tier") VALUES (6, 'Katnappé', 3, 5, 3, NULL, 'heylin', 0, 'easy');
INSERT INTO character ("id", "name", "force", "agility", "intellect", "power_id", "affiliation", "is_playable", "tier") VALUES (7, 'Salvador_Cumo', 3, 3, 5, NULL, 'heylin', 0, 'easy');
INSERT INTO character ("id", "name", "force", "agility", "intellect", "power_id", "affiliation", "is_playable", "tier") VALUES (8, 'Vlad', 6, 4, 4, NULL, 'heylin', 0, 'hard');
INSERT INTO character ("id", "name", "force", "agility", "intellect", "power_id", "affiliation", "is_playable", "tier") VALUES (9, 'Le_Mime', 4, 6, 4, NULL, 'heylin', 0, 'hard');
INSERT INTO character ("id", "name", "force", "agility", "intellect", "power_id", "affiliation", "is_playable", "tier") VALUES (10, 'PandaBubba', 4, 4, 6, NULL, 'heylin', 0, 'hard');
INSERT INTO character ("id", "name", "force", "agility", "intellect", "power_id", "affiliation", "is_playable", "tier") VALUES (11, 'Hannibal_Roy_Bean', 5, 5, 5, -5, 'heylin', 0, 'boss');
INSERT INTO character ("id", "name", "force", "agility", "intellect", "power_id", "affiliation", "is_playable", "tier") VALUES (12, 'Wuya', 6, 6, 6, -6, 'heylin', 0, 'boss');
INSERT INTO character ("id", "name", "force", "agility", "intellect", "power_id", "affiliation", "is_playable", "tier") VALUES (13, 'Chase_Young', 7, 7, 7, -7, 'heylin', 0, 'boss');
INSERT INTO character ("id", "name", "force", "agility", "intellect", "power_id", "affiliation", "is_playable", "tier") VALUES (14, 'Jack_Spicer', 3, 3, 7, -8, 'heylin', 0, 'boss');

-- ----------------------------------------------------------------------------
CREATE TABLE "background" (
	"id"	INTEGER,
	"name"	TEXT,
	"element"	TEXT,
	"sec_element"	TEXT,
	PRIMARY KEY("id" AUTOINCREMENT)
);

INSERT INTO background ("id", "name", "element", "sec_element") VALUES (1, 'Standing Pillars', 'wind', NULL);
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (2, 'Empty Field', 'earth', 'wind');
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (3, 'Highest Mountain', 'earth', 'wind');
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (4, 'Volcano', 'fire', NULL);
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (5, 'Stone Circle', 'earth', NULL);
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (6, 'Ocean Arch', 'water', 'wind');
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (7, 'Flying Statues', 'wind', NULL);
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (8, 'Winter Fortress', 'water', NULL);
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (9, 'Magma Pool', 'fire', NULL);
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (10, 'Cosmic Playfield', 'metal', NULL);
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (11, 'Pile of Hay', 'earth', 'fire');
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (12, 'Crocodile River', 'water', NULL);
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (13, 'Shadowy Marsh', 'water', 'metal');
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (14, 'Ice Ring', 'water', NULL);
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (15, 'Noir Dessert', 'earth', 'fire');
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (16, 'Tall Trees', 'earth', 'wind');
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (17, 'Bursted Lighthouse', 'fire', 'metal');
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (18, 'Chinese Folklore', 'metal', NULL);
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (19, 'Hulking Nest', 'wind', NULL);
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (20, 'Whirpool', 'water', 'wind');
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (21, 'Canalworks', 'water', 'metal');
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (22, 'Sand Pillars', 'earth', 'wind');
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (23, 'Valley of Doom', 'metal', NULL);
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (24, 'Crystal Cave', 'metal', NULL);
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (25, 'Divided Pyramid', 'metal', NULL);
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (26, 'Pipelines', 'metal', 'water');
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (27, 'Ring of Light', 'metal', NULL);
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (28, 'Burning Arena', 'fire', NULL);
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (29, 'Water Streams', 'water', NULL);
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (30, 'Frozen Lake', 'water', 'wind');
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (31, 'Stripes of Land', 'earth', NULL);
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (32, 'Long Cistern', 'metal', NULL);
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (33, 'Videogame', 'metal', NULL);
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (34, 'Blueprint', 'metal', NULL);
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (35, 'Bamboo Grove', 'earth', 'wind');
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (36, 'Tree Roots', 'earth', 'water');
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (37, 'Jagged Crevasse', 'earth', 'wind');
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (38, 'Thousand Balloons', 'wind', 'fire');
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (39, 'Amphitheater', 'earth', 'wind');
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (40, 'Muddy Canyon', 'earth', 'water');
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (41, 'Lava River', 'fire', NULL);
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (42, 'Meteorite', 'fire', NULL);
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (43, 'Atom Level', 'metal', NULL);
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (44, 'Enourmous Chessboard', 'earth', 'metal');
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (45, 'Basalt Cubes', 'earth', NULL);
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (46, 'Lifted Rock', 'wind', NULL);
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (47, 'Arcade Machine', 'metal', NULL);
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (48, 'Ying-Yang World', 'metal', NULL);
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (49, 'Boulder Forest', 'earth', NULL);
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (50, 'Grim Citadel', 'metal', NULL);
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (51, 'Snowy Slope', 'water', 'wind');
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (52, 'Tree of Life', 'earth', 'water');
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (53, 'Spectral Skeleton', 'metal', NULL);
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (54, 'Haunted Mangrove', 'earth', NULL);
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (55, 'Web of Snares', 'earth', NULL);
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (56, 'Ghost Ship', 'water', 'metal');
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (57, 'Molten Rock', 'fire', 'earth');
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (58, 'Thorny Bush', 'earth', NULL);
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (59, 'Pool Table', 'metal', NULL);
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (60, 'Anti-gravity Tunnel', 'wind', NULL);
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (61, 'Monstrous Toybox', 'metal', NULL);
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (62, 'Budda Statue', 'metal', NULL);
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (63, 'Christmas Snowglobe', 'water', 'wind');
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (64, 'Climbing Beanstalk', 'earth', 'wind');
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (65, 'Clockwork Vault', 'metal', NULL);
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (66, 'Eye of the Storm', 'wind', 'water');
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (67, 'Waterfalls', 'water', 'wind');
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (68, 'Geyser Hot Springs', 'water', 'fire');
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (69, 'Rice Fields', 'water', NULL);
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (70, 'Steam Vents', 'fire', 'water');
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (71, 'Ember Forge', 'fire', 'wind');
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (72, 'Firework Festival', 'fire', 'wind');
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (73, 'Dragon''s Mouth', 'fire', NULL);
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (74, 'Smoldering Ruins', 'fire', NULL);
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (75, 'Ash Plains', 'fire', NULL);
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (76, 'Mirror Maze', 'metal', NULL);
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (77, 'Power Plant', 'fire', 'metal');
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (78, 'Monsoon Rooftops', 'water', NULL);
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (79, 'Coral Shallows', 'water', NULL);
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (80, 'Cloud Terrace', 'wind', 'water');
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (81, 'Wildfire', 'fire', 'earth');
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (82, 'Sunflower Field', 'fire', 'earth');
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (83, 'Charcoal Braziers', 'fire', NULL);
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (84, 'Firefly Swamp', 'fire', 'water');
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (85, 'Hall of Candles', 'fire', NULL);
INSERT INTO background ("id", "name", "element", "sec_element") VALUES (86, 'Brimstone Steps', 'fire', NULL);

-- ----------------------------------------------------------------------------
CREATE TABLE "mechanic_config" (
	"id"	INTEGER,
	"mechanic"	TEXT NOT NULL,
	"key"	TEXT NOT NULL,
	"value"	INTEGER NOT NULL,
	PRIMARY KEY("id" AUTOINCREMENT),
	UNIQUE("mechanic", "key")
);

INSERT INTO mechanic_config ("id", "mechanic", "key", "value") VALUES (1, 'gamble', 'low', -2);
INSERT INTO mechanic_config ("id", "mechanic", "key", "value") VALUES (2, 'gamble', 'high', 5);
INSERT INTO mechanic_config ("id", "mechanic", "key", "value") VALUES (3, 'buff', 'value', 3);
INSERT INTO mechanic_config ("id", "mechanic", "key", "value") VALUES (4, 'scry', 'depth', 3);
INSERT INTO mechanic_config ("id", "mechanic", "key", "value") VALUES (5, 'morph', 'aside', 2);
INSERT INTO mechanic_config ("id", "mechanic", "key", "value") VALUES (6, 'morph', 'boost', 1);
INSERT INTO mechanic_config ("id", "mechanic", "key", "value") VALUES (7, 'animate', 'stat', 3);
INSERT INTO mechanic_config ("id", "mechanic", "key", "value") VALUES (8, 'animate', 'field_stat', 2);
INSERT INTO mechanic_config ("id", "mechanic", "key", "value") VALUES (9, 'beast_form', 'boost', 1);
INSERT INTO mechanic_config ("id", "mechanic", "key", "value") VALUES (10, 'beast_form', 'margin', 3);
INSERT INTO mechanic_config ("id", "mechanic", "key", "value") VALUES (11, 'bot', 'attack_stat', 3);
INSERT INTO mechanic_config ("id", "mechanic", "key", "value") VALUES (12, 'bot', 'good_jack_stat', 4);
INSERT INTO mechanic_config ("id", "mechanic", "key", "value") VALUES (13, 'bot', 'printed_physical', 3);
INSERT INTO mechanic_config ("id", "mechanic", "key", "value") VALUES (14, 'jong', 'stat', 6);
INSERT INTO mechanic_config ("id", "mechanic", "key", "value") VALUES (15, 'jong', 'boost_stat', 1);
INSERT INTO mechanic_config ("id", "mechanic", "key", "value") VALUES (16, 'witchcraft', 'recall_margin', 3);
INSERT INTO mechanic_config ("id", "mechanic", "key", "value") VALUES (17, 'witchcraft', 'recall_limit', 3);
INSERT INTO mechanic_config ("id", "mechanic", "key", "value") VALUES (18, 'witchcraft', 'early_bird_gap', 2);
INSERT INTO mechanic_config ("id", "mechanic", "key", "value") VALUES (19, 'bot', 'flee_cap', 3);
INSERT INTO mechanic_config ("id", "mechanic", "key", "value") VALUES (20, 'bot', 'attack_min_chance', 5);
INSERT INTO mechanic_config ("id", "mechanic", "key", "value") VALUES (21, 'bot', 'attack_max_chance', 90);
INSERT INTO mechanic_config ("id", "mechanic", "key", "value") VALUES (22, 'bot', 'attack_chance_when_leading', 2);
INSERT INTO mechanic_config ("id", "mechanic", "key", "value") VALUES (23, 'bot', 'attack_chance_when_trailing', 5);
INSERT INTO mechanic_config ("id", "mechanic", "key", "value") VALUES (24, 'bot', 'attack_momentum_step', 10);
INSERT INTO mechanic_config ("id", "mechanic", "key", "value") VALUES (25, 'bot', 'attack_momentum_cap', 30);
INSERT INTO mechanic_config ("id", "mechanic", "key", "value") VALUES (26, 'bot', 'chamelon_margin', 1);
INSERT INTO mechanic_config ("id", "mechanic", "key", "value") VALUES (27, 'bot', 'jack_force_margin', 1);
INSERT INTO mechanic_config ("id", "mechanic", "key", "value") VALUES (28, 'witchcraft', 'wears', 1);
INSERT INTO mechanic_config ("id", "mechanic", "key", "value") VALUES (29, 'witchcraft', 'returns', 1);
