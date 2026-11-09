"""Bastion: shared test helpers (not a test file: run_tests.py only collects test_*.py).

Tests never depend on the real content: FixtureCase installs small fixture structures, cards and
enemies (parsed by the real loaders) into the registries for each test and restores them after.

    class MyTests(helpers.FixtureCase): ...     # setUp installs the fixtures
    new_match(players=1, enemies=(), act=True, **settings)   a Match on MAP with a fixed seed;
                                       `enemies` = fixture enemy ids in arrival order (none by
                                       default); act=True: everyone is ready, so it is p1's turn
                                       in the act phase (act=False: still placing)
    give(match, pid, card_id)          a fresh instance of card_id in pid's hand -> its uid
    build(match, kind, x, y, rotation=0)   place a structure directly (no checks)
    foe(match, enemy_id)               a fixture enemy made active right now -> Foe
    units(match, pid, n)               give pid n more units to place this round
    put(match, pid, target)            a unit of pid's on target (straight into match.placed, any phase)
    ready_all(match)                   everyone ready: the act phase starts
    next_round(match)                  everyone ready, everyone ends their turn, and everyone is
                                       ready again in the new round (its act phase, first player's turn)

MAP (8 x 6), keep at (3, 2):          Fixture structures (see STRUCTURES below):
    y0  F F . . . . . .                  mill "##" next to forest; wood 2; +1 next to >=2 forest,
    y1  F . . . . . . .                       +1 next to a yard, -1 next to another mill
    y2  . . . K . . . .                  yard "#" depot; shop "#" 2 wood -> 1 tools;
    y3  . . . . . . . .                  field "##/##" wheat 2, +1 per "hut" (max 2);
    y4  . . . . . . M M                  clinic "#" 1 wheat -> cure 1; tower "#" protects 1;
    y5  ~ . . . . . M M                  hut "#" population 2, gives the "boon" card; cart "#"
                                         (a carriage); road, wall tiles
"""

import importlib
import random
import unittest

GAME = "bastion"
structures = importlib.import_module(f"games.{GAME}.logic.structures")
cards = importlib.import_module(f"games.{GAME}.logic.cards")
enemies = importlib.import_module(f"games.{GAME}.logic.enemies")
maps = importlib.import_module(f"games.{GAME}.logic.maps")
match_module = importlib.import_module(f"games.{GAME}.logic.match")
foes_module = importlib.import_module(f"games.{GAME}.logic.foes")

STRUCTURES = {
    "keep": {"name": "Keep", "shape": ["#"], "depot": True, "income": {"gold": 1}},
    "road": {"name": "Road", "shape": ["##"], "tile": "road", "cost": {"gold": 1}},
    "wall": {"name": "Wall", "shape": ["##"], "tile": "wall", "cost": {"stone": 1}},
    "mill": {"name": "Mill", "shape": ["##"], "price": 1, "cost": {"wood": 1}, "requires": [{"near": "forest"}],
             "work": {"makes": {"wood": 2}},
             "bonuses": [{"near": "forest", "min": 2, "bonus": 1}, {"near": "yard", "bonus": 1}, {"near": "mill", "bonus": -1}]},
    "yard": {"name": "Yard", "shape": ["#"], "price": 1, "depot": True},
    "shop": {"name": "Shop", "shape": ["#"], "price": 1, "work": {"uses": {"wood": 2}, "makes": {"tools": 1}}},
    "field": {"name": "Field", "shape": ["##", "##"], "price": 1, "work": {"makes": {"wheat": 2}},
              "bonuses": [{"near": "hut", "each": 1, "max": 2}]},
    "clinic": {"name": "Clinic", "shape": ["#"], "price": 1, "work": {"uses": {"wheat": 1}, "makes": {"cure": 1}}},
    "tower": {"name": "Tower", "shape": ["#"], "price": 1, "protects": 1},
    "hut": {"name": "Hut", "shape": ["#"], "price": 1, "bundle": 2, "population": 2, "card": "boon"},
    "cart": {"name": "Cart", "shape": ["#"], "price": 1, "carriage": True},
    "ell": {"name": "Ell", "shape": ["##", "#."], "price": 1},
}
CARDS = {
    "mend": {"name": "Mend", "repair": True},
    "remedy": {"name": "Remedy", "cure": True, "cost": {"wheat": 1}},
    "boon": {"name": "Boon", "gain": {"gold": 2, "soldiers": 1}, "draw": 1},
    "note": {"name": "Note", "kind": "curse", "pay": {"gold": 1}, "hurts": True},
    "dread": {"name": "Dread", "kind": "curse", "pay": {"wheat": 1}},
}
ENEMIES = {
    "brute": {"name": "Brute", "tier": 1, "hp": 2, "defeat": {"soldiers": 2},
              "attacks": [{"name": "Smash", "ruin": 1}, {"name": "Rob", "steal": {"gold": 2}}, {"name": "Rest"}]},
    "sender": {"name": "Sender", "tier": 1, "hp": 2, "defeat": {"cards": True},
               "attacks": [{"name": "Send", "curse": "note", "to": "each"}]},
    "rat": {"name": "Rat", "tier": 1, "hp": 2, "defeat": {"cure": True}, "attacks": [{"name": "Sicken", "plague": 1}]},
    "witch": {"name": "Witch", "tier": 2, "hp": 2, "defeat": {"resources": {"wood": 2}},
              "attacks": [{"name": "Freeze", "freeze": 1}, {"name": "Hit", "keep": 3, "shield": True}]},
    "lich": {"name": "Lich", "tier": 3, "defeat": {"raze": 1}, "lair": {"name": "Altar", "shape": ["#"]},
             "attacks": [{"name": "Grave", "place": {"name": "Grave"}}, {"name": "Kill", "kill": 2}]},
}
MAP = maps.GameMap("Test", 8, 6, ["FF......", "F.......", "........", "........", "......MM", "~.....MM"],
                   [{"structure": "keep", "x": 3, "y": 2, "rotation": 0}])
SETTINGS = {"map": "test", "keepHealth": 10, "difficulty": "normal", "enemies": 3, "peaceRounds": 2, "enemyGap": 2}


def fixture_registries():
    found = {sid: structures.parse_structure(sid, data) for sid, data in STRUCTURES.items()}
    structures.check_names(found)
    return found


class FixtureCase(unittest.TestCase):
    """Installs the fixture structures/cards in place (modules share these dicts) per test."""

    def setUp(self):
        saved = [(registry, dict(registry)) for registry in (structures.STRUCTURES, cards.CARDS)]

        def restore():
            for registry, old in saved:
                registry.clear()
                registry.update(old)
        self.addCleanup(restore)
        structures.STRUCTURES.clear()
        structures.STRUCTURES.update(fixture_registries())
        made = {cid: cards.parse_card(cid, data, structures.STRUCTURES) for cid, data in CARDS.items()}
        made.update(cards.structure_cards(structures.STRUCTURES))
        cards.CARDS.clear()
        cards.CARDS.update(made)
        self.enemies = {eid: enemies.parse_enemy(eid, data, cards.CARDS) for eid, data in ENEMIES.items()}


def new_match(case, players=1, enemies=(), act=True, **settings):
    """A Match with fixed seed on MAP; `enemies` = fixture enemy ids in arrival order."""
    picked = {eid: case.enemies[eid] for eid in enemies}
    merged = {**SETTINGS, "enemies": len(enemies), **settings}
    names = {f"p{i + 1}": f"P{i + 1}" for i in range(players)}
    original = foes_module.lineup
    foes_module.lineup = lambda pool, count, rng: [pool[eid] for eid in enemies]
    try:
        match = match_module.Match(names, merged, rng=random.Random(1), enemies=picked, maps={"test": MAP},
                                   deck={"boon": 5})
    finally:
        foes_module.lineup = original
    if act:
        ready_all(match)
    return match


def give(match, pid, card_id):
    instance = match.seats[pid].deck.make(card_id)
    match.seats[pid].hand.append(instance)
    return instance["uid"]


def build(match, kind, x, y, rotation=0):
    return match.board.place(kind, rotation, x, y)


def foe(case, match, enemy_id):
    made = foes_module.Foe(len(match.foes), case.enemies[enemy_id], match.round, 1.0)
    match.foes.append(made)
    made.arrive(match.board, match.rng)
    return made


def units(match, pid, n):
    match.seats[pid].units += n


def put(match, pid, target):
    by = match.placed.setdefault(target, {})
    by[pid] = by.get(pid, 0) + 1
    match.seats[pid].units += 1


def ready_all(match):
    for pid in list(match.seats):
        if match.phase == "place" and match.result is None:
            match.ready(pid)


def next_round(match):
    ready_all(match)
    while match.turn() and match.result is None:
        match.end_turn(match.turn())
    ready_all(match)
