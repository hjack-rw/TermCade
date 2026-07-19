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
--     *share* that power (Omi is the Dragon of Water). Moby Morpher (card 5) does not: Hannibal's
--     own power is "Free Allomorphia" (-5), the Wu's is "Allomorphia" (30) — the character holds the
--     Wu, it is not the Wu.
-- So a new Wu appends at the end. It never fills a hole and never renumbers a neighbour.
--
-- A power NAMES its mechanic, and `mechanics.powers.RULES` says what that mechanic does, when it
-- fires, and what it tells a player. A name nobody implemented fails at LOAD (`Mechanic(row)`),
-- rather than becoming a Wu that quietly does nothing. There is no trigger column and no effect
-- integer: when a power fires follows from what it is.

-- ----------------------------------------------------------------------------
CREATE TABLE "power" (
	"id"	INTEGER,
	"name"	TEXT,
	"mechanic"	TEXT NOT NULL,
	"description"	TEXT,
	"initiative_bonus"	INTEGER NOT NULL DEFAULT 0,
	PRIMARY KEY("id")
);

INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus") VALUES (-7, 'Beast Form', 'beast_form', 'Going over to the dark side, Chase became infused with the power of a Heylin Demon. He refuses however to meddle in mere mortal affairs.', 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus") VALUES (-6, 'Witchcraft', 'witchcraft', 'Due to Wuya''s personal connection to the Shen Gong Wu, she can both find Wu''s that have been lost, while also using them in more efficient ways.', 1);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus") VALUES (-5, 'Free Allomorphia', 'morph', 'Given his condition of being a literal Heylin Bean, Hannibal took a hold of Moby Morpher and never let it go - so he wields it as a free Wu.', 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus") VALUES (-4, 'Dragon of Earth', 'dragon', 'User has access to basic Earth-based attacks, and moves', 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus") VALUES (-3, 'Dragon of Fire', 'dragon', 'User has access to basic Fire-based attacks, and moves', 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus") VALUES (-2, 'Dragon of Wind', 'dragon', 'User has access to basic Wind-based attacks, and moves', 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus") VALUES (-1, 'Dragon of Water', 'dragon', 'User has access to basic Water-based attacks, and moves', 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus") VALUES (0, 'blank', 'filler', 'blank', 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus") VALUES (1, 'Superhuman Strength', 'innate', 'Allows the user to punch with incredible force, capable of creating shock waves during the impact', 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus") VALUES (2, 'Deflection', 'innate', 'Protects the user''s head by deflecting attacks and projectiles towards it', 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus") VALUES (3, 'Photographic Memory', 'innate', 'Grants its user an instant memory recall. The memories are stored in bubbles inside the Wu and can be shared across users', 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus") VALUES (4, 'Furious Charge', 'initiative', 'Bull horn that when blown blasts the user at rapid speeds forward at their target (aka a "DASH-i")', 1);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus") VALUES (5, 'Levitation', 'initiative', 'Allows the user to defy gravity, which enables them to walk vertically on walls and even float minimal above ground', 1);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus") VALUES (6, 'Camouflage', 'initiative', 'Helps its user blend into their surroundings like a chameleon', 1);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus") VALUES (7, 'Mégathoskinesis', 'initiative', 'Shrinks targeted objects or people to the size of a grain of rice. The size change is not permanent and requires the user to keep a hold of the Wu', 1);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus") VALUES (8, '? ? ?', 'gamble', '? ? ?', 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus") VALUES (9, 'Power Augmentation', 'boost', 'Could greatly enhance the powers of other Wu that the user is holding. It combines with it, making it count as one in a duel.', 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus") VALUES (10, 'Temporary Appendage', 'hand_size', 'Acts like an extendable, strong, and durable third arm. Its moves are somewhat independent from the wearer, but always obey their commands', 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus") VALUES (11, 'Chronokinesis', 'draw', 'Freezes anything it is pointed at in time and place for a short while', 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus") VALUES (12, 'Impenetrable Defence', 'innate', 'Can temporarily transform into an armor capable of blocking all sorts of attacks, but its weight increases drastically while active', 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus") VALUES (13, 'Umbrakinesis', 'innate', 'Allows for shadow manipulation that can influence a physical target. It can absorb and dissipate shadows at will, allowing the user to create shadow copies when it''s charged up', 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus") VALUES (14, 'Tongue Twister', 'innate', 'Makes the user''s enemies babble nonsense non stop. The effect prevents them of taking coherent actions', 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus") VALUES (15, 'Self-conscious Rope', 'initiative', 'Rope that can fulfill simple orders, behaving like a snake while at it. Apart from that it possess all the abilities of an ordinary rope', -1);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus") VALUES (16, 'Extendable Tendrils', 'initiative', 'It shoots a stream of hair from the comb''s teeth at the intended target and binds it. However, it requires complete focus from the user as you need to control each hair separately', -1);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus") VALUES (17, 'Méllissakinesis', 'initiative', 'When opened, unleashes a swarm of insects (e.g. ants, flies, bees) at a desired target', -1);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus") VALUES (18, 'Metáxikinesis', 'initiative', 'Allows the user to fire strands of spider-like silk. The user himself is immune to its stickiness, but opponents will be rendered immobile for a short while. Can also be used to swing from place to place on the slik string', -1);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus") VALUES (19, 'Intangibility', 'nullify_element', 'Makes the user a ghost, allowing them to pass through solid objects and avoid physical attacks, but it doesn''t protect against non-physical attacks', 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus") VALUES (20, 'Diaskopia', 'read_deck', 'Allows the user to see through solid objects. The user may enhance the ability further by using its sister Shen Gong Wu, the Eagle Scope', 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus") VALUES (21, 'Teleskopia', 'scry', 'Transforms into a telescope, granting the user eagle-like long range vision. It is the sister Shen Gong Wu to the Falcon''s Eye', 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus") VALUES (22, 'Oxyderkia', 'enhanced_vision', 'Alows for different kinds of vision (thermal or even sound).', 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus") VALUES (23, 'Hydrokinesis', 'buff', 'Releases a large flood of water, that can also be frozen into ice', 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus") VALUES (24, 'Misfortune', 'misfortune', 'Creates ironic or down-right unlucky situations for all of its user''s opponents', 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus") VALUES (25, 'Attraction', 'fetch', 'Allows the user to attract any object toward themselves, including other Shen Gong Wu', 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus") VALUES (26, 'Repulsion', 'bounce', 'Allows the user to telekinetically push targeted objects (opposite of the Glove of Jisaku)', 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus") VALUES (27, 'Containment', 'nullify_stats', 'Traps the target in an impervious transparent sphere. It also copies authority and possessions from the prisoner to the user', 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus") VALUES (28, 'Reversal', 'nullify_curse', 'Reverses the powers of anything that is binary, including other Shen Gong Wu (e.g. the Two-Ton Tunic becomes as light as a feather)', 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus") VALUES (29, 'Subjugation', 'nullify_wu', 'Allows the user to control or disable all other Shen Gong Wu, including multiple Wu constructs like Mala Mala Jong', 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus") VALUES (30, 'Astrapokinesis', 'initiative', 'For as long as the coin is in the air the user moves at the speed of light, and everything else is standing still', 2);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus") VALUES (31, 'Supersonic Flight', 'initiative', 'Carries its user at supersonic speed', 2);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus") VALUES (32, 'Invisibility', 'initiative', 'Renders its user unseen', 2);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus") VALUES (33, 'Reality Cutting', 'initiative', 'Cuts through anything, reality included: a clawed portal opens onto any place the user names, and stays open a short while – long enough that others may follow, until reality mends itself', 2);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus") VALUES (34, 'Blinding Glare', 'initiative', 'Throws up a glittering sphere of light that nobody can look away from and nobody can see past', -2);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus") VALUES (35, 'Mnenokinesis', 'initiative', 'Erases memory for a short while', -2);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus") VALUES (36, 'Stupefaction', 'initiative', 'Releases a purple gas that leaves its victims confused and foolish, or drops them into a deep sleep outright', -2);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus") VALUES (37, 'Efiáltiskinesis', 'initiative', 'Walks into a sleeping mind and gives its worst fear a body. It has no hold on anyone awake', -2);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus") VALUES (38, 'Euthymia', 'luck', 'Your good spirits turn fortune your way and a lost Wu finds its way back to you', 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus") VALUES (39, 'Polymorphia', 'dragon', 'Transforms into any weapon the user requires', 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus") VALUES (40, 'Allomorphia', 'morph', 'Allows the user to change their appearance into anything they choose - including the appearance of other beings', 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus") VALUES (41, 'Lunarkinesis', 'reverse_element', 'Allows the user to control the sun, the stars and the moon, including their different phases - turning the arena''s favour against itself.', 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus") VALUES (42, 'Thermokinesis', 'nullify_boost', 'Shoots out sparks that generate heat and can light fires, the sudden bloom of warmth smothering an opponent''s boost.', 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus") VALUES (43, 'Metallaxis', 'cleanse', 'Transforms an object''s alchemical properties by changing its atoms - turning a rival Wu to inert metal.', 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus") VALUES (44, 'Chromakinesis', 'set_element', 'Shoots any element from the centre gem, so the user''s own Wu take the colour they choose.', 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus") VALUES (45, 'Anemokinesis', 'set_arena', 'Controls the weather, changing the arena''s element to the one the user calls.', 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus") VALUES (46, 'Pyrophylaxia', 'ward', 'Covers the user in a shell of black bug that protects the user from extreme heat. It can also be used as a raft.', 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus") VALUES (47, 'Hydrophylaxia', 'ward', 'Allows the user to breathe underwater, transforming them into a fish-like being in the process (still can''t talk with fish).', 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus") VALUES (48, 'Anemophylaxia', 'ward', 'Grants the user the physical characteristics, as well as the acrobatic agility and balance of a monkey. If it stays active for too long it slowly transforms the user into a monkey.', 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus") VALUES (49, 'Geophylaxia', 'ward', 'Transforms the user hands into one large drill, allowing him to travel underground and break even diamonds.', 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus") VALUES (50, 'Metempsychosis', 'transfer', 'Allows the user to control chi: for example astral project or swap two person''s souls entirly. If used on multiple people all have to be illuminated by its light.', 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus") VALUES (51, 'Telepatheia', 'prognosis', 'Allows the user to hear the thoughts of other people whom the shell is aimed at.', 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus") VALUES (52, 'Chronomorphosis', 'treasure', 'Caused people to change age acording to the user (older/younger) rapidly. Can be used also to reverts a target back to its original form, such as turning oil into dinosaurs.', 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus") VALUES (53, 'Spirit Sealing', 'treasure', 'Traps spiritual bodies, such as Sibini or Wuya. There were multiple occurrences of this Wu.', 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus") VALUES (54, 'Fool''s Gold', 'treasure', 'Could produce laser beams of different colors, that could change everyone and everything color. Making people very enamoured by the object.', 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus") VALUES (55, 'Palingenesis', 'refresh', 'Heals any injury. Also regenerates aging over time.', 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus") VALUES (56, 'Klonogenesis', 'double_training', 'Multiplies the user into as many as nine people, but it also divides up the user''s skills (and mental prower is a skill) among all the clones.', 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus") VALUES (57, 'Hypersthenia', 'stat_shield', 'Grants the user super strength.', 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus") VALUES (58, 'Proaisthesis', 'stat_shield', 'It warned its user of impending danger.', 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus") VALUES (59, 'Gnoseokinesis', 'stat_shield', 'In form of a crown, grants the user infinite, but random knowledge. It can also grant perspective and sentience to an unintelligent beast. To gain specific knowledge use it with the Wushu Brcelet.', 0);
INSERT INTO power ("id", "name", "mechanic", "description", "initiative_bonus") VALUES (60, 'Thyellokinesis', 'double_element', 'Allows the user to generate or manipulate strong winds and tornados (leting its user to become a walking hurricane), but the sword itself cannot be used for physical attacks as it phases through enemies.', 0);

-- ----------------------------------------------------------------------------
CREATE TABLE card (id INTEGER, name TEXT, force INTEGER, agility INTEGER, intellect INTEGER, power_id INTEGER NOT NULL REFERENCES power (id), element TEXT, type TEXT, points INTEGER, PRIMARY KEY (id AUTOINCREMENT));

INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (0, 'blank', 0, 0, 0, 0, 'metal', 'item', 0);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (1, 'Silver Manta Ray', 1, 1, 1, -1, 'water', 'wudai', 0);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (2, 'Crest of a Sparrow', 1, 1, 1, -2, 'wind', 'wudai', 0);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (3, 'Longi Sash', 1, 1, 1, -3, 'fire', 'wudai', 0);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (4, 'Iron Bear Charm', 1, 1, 1, -4, 'earth', 'wudai', 0);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (5, 'Moby Morpher', NULL, NULL, NULL, 40, 'metal', 'arms', 4);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (6, 'Fist of Tebigong', 5, 0, 0, 1, 'metal', 'arms', 3);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (7, 'Helmet of Jong', 0, 5, 0, 2, 'metal', 'head', 3);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (8, 'Bubble Brains', 0, 0, 5, 3, 'metal', 'item', 3);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (9, 'Longhorn Taurus', 3, 0, 0, 4, 'wind', 'item', 2);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (10, 'Jetbootsu', 0, 3, 0, 5, 'fire', 'boots', 2);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (11, 'Mask of Rio', 0, 0, 3, 6, 'earth', 'head', 2);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (12, 'Changing Chopsticks', 0, 1, 1, 7, 'water', 'item', 2);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (13, 'Ohwah Tegu Saim', NULL, NULL, NULL, 8, 'metal', 'item', 1);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (14, 'Wushu Bracelet', NULL, NULL, NULL, 9, 'metal', 'amulet', 3);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (15, 'Third-Arm Sash', 0, 3, 0, 10, 'metal', 'arms', 2);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (16, 'Bras Finger', 1, 1, 1, 11, 'metal', 'item', 2);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (17, 'Two-Ton Tunic', -5, 0, 0, 12, 'metal', 'torso', 3);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (18, 'Shadow Slicer', 0, -5, 0, 13, 'metal', 'item', 3);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (19, 'Pearl of LiBai', 0, 0, -5, 14, 'metal', 'amulet', 3);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (20, 'Lasso Boa-Boa', -3, 0, 0, 15, 'earth', 'arms', 2);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (21, 'Tangle Web Comb', 0, -3, 0, 16, 'fire', 'item', 2);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (22, 'Ju-Ju Flytrap', 0, 0, -3, 17, 'wind', 'item', 2);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (23, 'Silk Spitter', -1, -1, 0, 18, 'water', 'item', 2);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (24, 'Serpent''s Tail', 1, 2, 1, 19, 'metal', 'item', 4);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (25, 'Falcon''s Eye', 0, 1, 2, 20, 'metal', 'item', 2);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (26, 'Eagle Scope', 0, 2, 1, 21, 'metal', 'item', 2);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (27, 'Mind Reader Conch', 0, 0, 4, 51, 'metal', 'item', 3);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (28, 'Orb of Tornami', NULL, NULL, NULL, 23, 'water', 'item', 3);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (29, 'Kaijin''s Curse', NULL, NULL, NULL, 24, 'metal', 'item', 3);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (30, 'Glove of Jisaku', 1, 1, 2, 25, 'metal', 'arms', 2);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (31, 'Ruby of Ramses', 2, 1, 1, 26, 'metal', 'item', 2);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (32, 'Sphere of Jianyu', 0, 0, 0, 27, 'metal', 'item', 4);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (33, 'Reversing Mirror', 0, 0, 0, 28, 'metal', 'item', 4);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (34, 'Emperor Scorpion', 0, 0, 0, 29, 'metal', 'item', 4);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (35, 'Raijin''s Flip Coin', 0, 4, 0, 30, 'metal', 'item', 2);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (36, 'Winged Feet', 1, 3, 0, 31, 'metal', 'boots', 2);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (37, 'Shroud of Shadows', 0, 2, 2, 32, 'metal', 'amulet', 2);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (38, 'Golden Tiger Claws', 2, 2, 0, 33, 'metal', 'arms', 2);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (39, 'Culver Crystal', -2, -2, 0, 34, 'metal', 'item', 2);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (40, 'Wushan Geyser', 0, 0, -4, 35, 'metal', 'head', 2);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (41, 'Woozy Shooter', 0, -1, -3, 36, 'metal', 'item', 2);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (42, 'Shadow of Fear', -2, 0, -2, 37, 'metal', 'item', 2);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (43, 'Rooster Booster', 1, 1, 1, 38, 'metal', 'item', 3);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (44, 'Shimo Staff', 1, 1, 1, 39, 'metal', 'wudai', 3);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (45, 'Celestial Dial Locket', 1, 1, 1, 41, 'metal', 'amulet', 3);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (46, 'Star Hanabi', 2, 2, 0, 42, 'fire', 'amulet', 3);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (47, 'Kuzusu Atom', 2, 1, 1, 43, 'metal', 'item', 3);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (48, 'Eye of Dashi', 2, 2, 2, 44, 'metal', 'amulet', 4);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (49, 'Monsoon Sandals', 1, 1, 1, 45, 'metal', 'boots', 3);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (50, 'Black Beetle', 0, 1, 2, 46, 'fire', 'item', 2);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (51, 'Gills of Hamachi', 0, 2, 1, 47, 'water', 'item', 2);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (52, 'Monkey Staff', 1, 2, 0, 48, 'wind', 'item', 2);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (53, 'Tunnel Armadillo', 2, 1, 0, 49, 'earth', 'item', 2);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (54, 'Sun Chi Lantern', 0, 0, 0, 50, 'metal', 'item', 5);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (55, 'Caleido-scope Glasses', 0, 2, 2, 22, 'metal', 'head', 3);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (56, 'Sweet Baby Among Us', 1, 0, 0, 52, 'metal', 'item', 5);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (57, 'Mosaic Scale Puzzlebox', 0, 1, 0, 53, 'metal', 'item', 5);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (58, 'Prism of Genesis', 0, 0, 1, 54, 'metal', 'item', 5);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (59, 'Tong ku Reverso', 0, 0, 0, 55, 'metal', 'item', 5);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (60, 'Ring of Nine Xing', 2, 2, 1, 56, 'metal', 'amulet', 4);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (61, 'Mikado Arms', 3, 0, 0, 57, 'metal', 'amulet', 3);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (62, 'Ninja Tabi', 0, 3, 0, 58, 'metal', 'torso', 3);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (63, 'Fountain of Hui', 0, 0, 3, 59, 'metal', 'head', 3);
INSERT INTO card ("id", "name", "force", "agility", "intellect", "power_id", "element", "type", "points") VALUES (64, 'Blade of the Nebula', 0, 2, 2, 60, 'wind', 'item', 3);

-- ----------------------------------------------------------------------------
CREATE TABLE "character" (
	"id"	INTEGER,
	"name"	TEXT,
	"force"	INTEGER,
	"agility"	INTEGER,
	"intellect"	INTEGER,
	"power_id"	INTEGER NOT NULL,
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
INSERT INTO character ("id", "name", "force", "agility", "intellect", "power_id", "affiliation", "is_playable", "tier") VALUES (5, 'Tubbimura', 5, 3, 3, 0, 'heylin', 0, 'easy');
INSERT INTO character ("id", "name", "force", "agility", "intellect", "power_id", "affiliation", "is_playable", "tier") VALUES (6, 'Katnappé', 3, 5, 3, 0, 'heylin', 0, 'easy');
INSERT INTO character ("id", "name", "force", "agility", "intellect", "power_id", "affiliation", "is_playable", "tier") VALUES (7, 'Salvador_Cumo', 3, 3, 5, 0, 'heylin', 0, 'easy');
INSERT INTO character ("id", "name", "force", "agility", "intellect", "power_id", "affiliation", "is_playable", "tier") VALUES (8, 'Vlad', 6, 4, 4, 0, 'heylin', 0, 'hard');
INSERT INTO character ("id", "name", "force", "agility", "intellect", "power_id", "affiliation", "is_playable", "tier") VALUES (9, 'Le_Mime', 4, 6, 4, 0, 'heylin', 0, 'hard');
INSERT INTO character ("id", "name", "force", "agility", "intellect", "power_id", "affiliation", "is_playable", "tier") VALUES (10, 'PandaBubba', 4, 4, 6, 0, 'heylin', 0, 'hard');
INSERT INTO character ("id", "name", "force", "agility", "intellect", "power_id", "affiliation", "is_playable", "tier") VALUES (11, 'Hannibal_Roy_Bean', 5, 5, 5, -5, 'heylin', 0, 'boss');
INSERT INTO character ("id", "name", "force", "agility", "intellect", "power_id", "affiliation", "is_playable", "tier") VALUES (12, 'Wuya', 6, 6, 6, -6, 'heylin', 0, 'boss');
INSERT INTO character ("id", "name", "force", "agility", "intellect", "power_id", "affiliation", "is_playable", "tier") VALUES (13, 'Chase_Young', 7, 7, 7, -7, 'heylin', 0, 'boss');

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
