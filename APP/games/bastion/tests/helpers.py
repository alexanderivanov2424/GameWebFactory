"""Bastion: shared test helpers (not a test file: run_tests.py only collects test_*.py).

Tests use fixture content (cards "t-...", enemies "t-...", a tiny map and hand-made levels) so
they check rules, never the real cards, enemies or levels, which get rebalanced all the time.

    helpers = importlib.import_module("games.bastion.tests.helpers")
    helpers.install()                  add the fixture cards/enemies to the game's registries
                                       (call from setUpModule; remove() in tearDownModule)
    new_match(players=2, levels=None, **settings)   a Match on the fixture map, fixed seed;
                                       default levels: [level(wave("t-grunt", 1))] * 3
    level(*waves, turns=1, reward=5) / wave(enemy, count=1, road="main", start=0, gap=4)
    give(match, pid, card_id)          a fresh instance of card_id in pid's hand -> its uid
    build(match, card_id, x, y, owner="p1", level=1)   put a structure straight on the board
    siege(match, *waves)               run one siege of those waves on match's board -> Result

Fixture map (8 x 5), keep at (0, 2):
    main road:  (7, 2) -> (0, 2), straight along row 2 (8 cells; (7, 2) is its entrance)
    flank road: (4, 4) -> (4, 2), then along row 2 to the keep
    rocks at (2, 0); everything else is grass.
"""

import importlib
import random

GAME = "bastion"
match_module = importlib.import_module(f"games.{GAME}.logic.match")
cards = importlib.import_module(f"games.{GAME}.logic.cards")
enemies = importlib.import_module(f"games.{GAME}.logic.enemies")
maps = importlib.import_module(f"games.{GAME}.logic.maps")
battle = importlib.import_module(f"games.{GAME}.logic.battle")
Match = match_module.Match

MAP = maps.parse_map("t-map", {
    "name": "Test",
    "terrain": ["..^.....", "........", "........", "........", "........"],
    "keep": [0, 2],
    "roads": {"main": [[7, 2], [0, 2]], "flank": [[4, 4], [4, 2], [0, 2]]},
})

CARDS = {
    "t-tower": {"name": "T Tower", "icon": "T", "kind": "tower", "labor": 2, "cost": 3,
                "stats": {"damage": [5, 8, 11], "range": [1.5, 2, 2.5], "cooldown": 1}},
    "t-air": {"name": "T Air", "icon": "A", "kind": "tower", "labor": 2, "cost": 3,
              "stats": {"damage": 5, "range": 9, "cooldown": 1, "air": True, "ground": False}},
    "t-pierce": {"name": "T Pierce", "icon": "P", "kind": "tower", "labor": 2, "cost": 3,
                 "stats": {"damage": 2, "range": 9, "cooldown": 1, "pierce": True}},
    "t-weak": {"name": "T Weak", "icon": "W", "kind": "tower", "labor": 2, "cost": 3,
               "stats": {"damage": 2, "range": 9, "cooldown": 1}},
    "t-wall": {"name": "T Wall", "icon": "#", "kind": "wall", "labor": 1, "cost": 2, "stats": {"hp": [10, 20, 30]}},
    "t-spikes": {"name": "T Spikes", "icon": "^", "kind": "spikes", "labor": 1, "cost": 2, "stats": {"damage": 5}},
    "t-tar": {"name": "T Tar", "icon": "~", "kind": "tar", "labor": 1, "cost": 2, "stats": {"slow": 50}},
    "t-barracks": {"name": "T Barracks", "icon": "B", "kind": "barracks", "labor": 3, "cost": 5,
                   "stats": {"hp": 30, "damage": 4, "cooldown": 1, "respawn": 20}},
    "t-farm": {"name": "T Farm", "icon": "F", "kind": "farm", "labor": 1, "cost": 4, "stats": {"gold": [1, 2, 3]}},
    "t-quarry": {"name": "T Quarry", "icon": "Q", "kind": "quarry", "labor": 1, "cost": 4, "maxLevel": 2,
                 "stats": {"labor": [1, 2]}},
    "t-forge": {"name": "T Forge", "icon": "G", "kind": "forge", "labor": 1, "cost": 4, "stats": {"bonus": 3}},
    "t-watch": {"name": "T Watch", "icon": "O", "kind": "watch", "labor": 1, "cost": 4, "stats": {"bonus": 1}},
    "t-chapel": {"name": "T Chapel", "icon": "C", "kind": "chapel", "labor": 1, "cost": 4,
                 "stats": {"keep": 2, "repair": 5}},
    "t-hustle": {"name": "T Hustle", "icon": "H", "kind": "order", "labor": 0, "cost": 3, "stats": {"labor": 2, "draw": 1}},
    "t-gift": {"name": "T Gift", "icon": "$", "kind": "order", "labor": 1, "cost": 3, "stats": {"teamGold": 2}},
    "t-mason": {"name": "T Mason", "icon": "M", "kind": "order", "labor": 1, "cost": 3, "stats": {"upgrade": True}},
    "t-fix": {"name": "T Fix", "icon": "R", "kind": "order", "labor": 1, "cost": 3, "stats": {"repair": 4, "keep": 3}},
}

ENEMIES = {
    "t-grunt": {"name": "Grunt", "icon": "g", "hp": 10, "speed": 0.5, "keep": 2, "attack": 5, "attackEvery": 1},
    "t-flyer": {"name": "Flyer", "icon": "f", "hp": 10, "speed": 0.5, "keep": 1, "flying": True},
    "t-armored": {"name": "Armored", "icon": "a", "hp": 20, "speed": 0.25, "keep": 1, "armor": 4},
    "t-tank": {"name": "Tank", "icon": "k", "hp": 1000, "speed": 0.5, "keep": 1, "attack": 2, "attackEvery": 1},
    "t-bomber": {"name": "Bomber", "icon": "b", "hp": 10, "speed": 0.5, "keep": 1, "explode": 25},
    "t-summoner": {"name": "Summoner", "icon": "s", "hp": 1000, "speed": 0.1, "keep": 1,
                   "summon": {"enemy": "t-grunt", "every": 5, "max": 2}},
    "t-troll": {"name": "Troll", "icon": "r", "hp": 20, "speed": 0.1, "keep": 1, "regen": 3},
    "t-healer": {"name": "Healer", "icon": "h", "hp": 1000, "speed": 0.25, "keep": 1,
                 "heal": {"amount": 100, "radius": 2, "every": 1}},
    "t-dragon": {"name": "Dragon", "icon": "d", "hp": 1000, "speed": 0.25, "keep": 1, "flying": True,
                 "breath": {"radius": 3, "every": 1, "stun": 5, "damage": 0}},
}

SETTINGS = {"difficulty": "normal", "keepHealth": 30, "map": "t-map"}


def install():
    for card_id, data in CARDS.items():
        cards.CARDS[card_id] = cards.parse_card(card_id, data)
    for enemy_id, data in ENEMIES.items():
        enemies.ENEMIES[enemy_id] = enemies.parse_enemy(enemy_id, data)


def remove():
    for card_id in CARDS:
        cards.CARDS.pop(card_id, None)
    for enemy_id in ENEMIES:
        enemies.ENEMIES.pop(enemy_id, None)


def wave(enemy, count=1, road="main", start=0, gap=4):
    return {"enemy": enemy, "count": count, "road": road, "start": start, "gap": gap}


def level(*waves, turns=1, reward=5, name="Test level"):
    return enemies.parse_level("t-level", {"name": name, "buildTurns": turns, "reward": reward,
                                           "waves": list(waves) or [wave("t-grunt")]}, enemies.ENEMIES)


def new_match(players=2, levels=None, **settings):
    names = {f"p{i + 1}": f"Player {i + 1}" for i in range(players)}
    if levels is None:
        levels = [level() for _ in range(3)]
    return Match(names, {**SETTINGS, **settings}, rng=random.Random(1), levels=levels, maps={"t-map": MAP})


def give(match, pid, card_id):
    seat = match.seats[pid]
    instance = seat.deck.make(card_id)
    seat.hand.append(instance)
    return instance["uid"]


def build(match, card_id, x, y, owner="p1", level=1):
    match.board.place(cards.CARDS[card_id], x, y, owner)
    structure = match.board.at(x, y)
    structure.level = level
    structure.hp = structure.max_hp()
    return structure


def siege(match, *waves, keep=30, hp_scale=1.0):
    return battle.run_siege(match.board, level(*waves), keep, hp_scale, 1, 1)
