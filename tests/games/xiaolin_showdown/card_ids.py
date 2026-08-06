"""Named cards the test suite reaches for, one constant per mechanic that only one pool Wu carries.

GENERATED — do not hand-edit. Run ``python scripts/generate_card_ids.py`` after any card DB change (a
renumber, a rename, a new or removed Wu) to bring this back in sync; ``test_seed.py``'s sibling check
fails the build the moment it drifts. Import from here instead of a bare integer:

    from card_ids import AMEND
    mouse = card(AMEND)

A mechanic several Wu share (initiative, innate, train_boost, dragon...) has no single right answer
the generator can pick — it is not represented here. A test that needs one specific Wu among several
picks it inline by whatever actually singles it out (a stat, a summon keyword, the mechanic plus a
second trait) — never a bare id.
"""

from __future__ import annotations

AMEND = 5  # "Hodoku Mouse"
ANIMATE = 6  # "Heart of Jong"
BOOST = 7  # "Wushu Bracelet"
BOUNCE = 8  # "Ruby of Ramses"
BUFF = 9  # "Orb of Tornami"
CHI_SWAP = 10  # "Ying-Yang Yo-Yo"
CLEANSE = 11  # "Kuzusu Atom"
CONDUCT = 12  # "Shard of Lightning"
DOUBLE_ELEMENT = 13  # "Blade of the Nebula"
DOUBLE_TRAINING = 14  # "Ring of Nine Xing"
DRAGON = 15  # "Shimo Staff"
DRAW = 16  # "Bras Finger"
ENHANCED_VISION = 17  # "Caleido-scope Glasses"
FETCH = 18  # "Glove of Jisaku"
GAMBLE = 19  # "Ohwah Tegu Saim"
HACK = 20  # "Denshi Bunny"
HAND_SIZE = 21  # "Third-Arm Sash"
LUCK = 52  # "Rooster Booster"
MISFORTUNE = 53  # "Kaijin's Curse"
MORPH = 54  # "Moby Morpher"
NULLIFY_BOOST = 55  # "Star Hanabi"
NULLIFY_CURSE = 56  # "Reversing Mirror"
NULLIFY_ELEMENT = 57  # "Serpent's Tail"
NULLIFY_STATS = 58  # "Sphere of Jianyu"
NULLIFY_WU = 59  # "Emperor Scorpion"
PROGNOSIS = 60  # "Mind Reader Conch"
READ_DECK = 61  # "Falcon's Eye"
REFRESH = 62  # "Tong ku Reverso"
REVERSE_ELEMENT = 63  # "Celestial Dial Locket"
SCRY = 64  # "Eagle Scope"
SEIZE_GROUND = 65  # "Cube of Haniku"
SET_ARENA = 66  # "Monsoon Sandals"
SET_ELEMENT = 67  # "Eye of Dashi"
STEAL = 73  # "Sands of Time"
TRANSFER = 80  # "Sun Chi Lantern"
WISH = 88  # "Treasurebox of the Blind Swordsman"
