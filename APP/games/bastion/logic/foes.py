"""Bastion: the enemies of one game: who comes, when, their health and how they're beaten.

    scale(players, difficulty)        health multiplier (DIFFICULTY x (1 + PER_PLAYER per extra player))
    lineup(enemies, count, rng)       `count` enemy dicts in arrival order: lower tiers first, a
                                      tier-3 boss last when there is one
    Foe(index, enemy, arrives, scale) one enemy card in this game
        foe.state                     "coming" (face down), "active" or "defeated"
        foe.hp / foe.max_hp           damage left / total (a lair foe: its lair tiles)
        foe.defeat                    the enemy's ways to beat it (a copy: arrive() may change it)
        foe.raze                      soldiers per lair tile
        foe.attack()                  the attack it makes this round (then foe.step += 1)
        foe.arrive(board, rng)        turn face up; place its lair (as blights on empty grass)
        foe.hit(n)                    -> True if that beat it
        foe.public()                  face down: only when it arrives
"""

import math

from .enemies import ENEMIES

DIFFICULTY = {"easy": 0.75, "normal": 1.0, "hard": 1.3}
PER_PLAYER = 0.5


def scale(players, difficulty):
    return DIFFICULTY[difficulty] * (1 + PER_PLAYER * max(0, players - 1))


def lineup(enemies, count, rng):
    pool = sorted(enemies.values(), key=lambda e: e["id"])
    bosses = [e for e in pool if e["tier"] == 3]
    boss = [rng.choice(bosses)] if bosses else []
    others = [e for e in pool if e["tier"] < 3]
    picked = rng.sample(others, min(len(others), max(0, count - len(boss))))
    rng.shuffle(picked)
    picked.sort(key=lambda e: e["tier"])
    return picked + boss[:count]


class Foe:
    def __init__(self, index, enemy, arrives, factor):
        self.index = index
        self.enemy = enemy
        self.arrives = arrives
        self.state = "coming"
        self.step = 0
        self.defeat = dict(enemy["defeat"])
        self.raze = max(1, math.ceil(self.defeat.get("raze", 0) * factor)) if "raze" in self.defeat else 0
        self.max_hp = self.hp = max(1, round(enemy["hp"] * factor))

    @property
    def name(self):
        return self.enemy["name"]

    @property
    def active(self):
        return self.state == "active"

    def attack(self):
        attacks = self.enemy["attacks"]
        attack = attacks[self.step % len(attacks)]
        self.step += 1
        return attack

    def arrive(self, board, rng):
        self.state = "active"
        lair = self.enemy["lair"]
        if not lair:
            return
        spots = board.free_spots(lair["cells"], rng)
        if spots:
            x, y = spots[0]
            for dy, dx in lair["cells"]:
                board.add_blight((x + dx, y + dy), lair["name"], lair["icon"], self.index, lair=True)
            self.max_hp = self.hp = len(lair["cells"])
        else:  # no room for the lair: fight it with soldiers instead
            self.defeat = {"soldiers": self.raze}
            self.raze = 0

    def hit(self, amount=1):
        if not self.active:
            return False
        self.hp = max(0, self.hp - amount)
        if self.hp == 0:
            self.state = "defeated"
            return True
        return False

    def public(self):
        if self.state == "coming":
            return {"state": "coming", "arrives": self.arrives}
        attacks = self.enemy["attacks"]
        return {
            "state": self.state, "arrives": self.arrives, "id": self.enemy["id"], "name": self.name,
            "icon": self.enemy["icon"], "text": self.enemy["text"], "hp": self.hp, "maxHp": self.max_hp,
            "attacks": [{"name": a["name"], "text": a["text"]} for a in attacks],
            "next": self.step % len(attacks),
            "defeat": {k: v for k, v in self.defeat.items() if k != "raze"} | ({"raze": self.raze} if self.raze else {}),
            "lair": self.enemy["lair"]["name"] if self.enemy["lair"] else "",
        }


def make_foes(players, settings, rng, enemies=None):
    picked = lineup(enemies if enemies is not None else ENEMIES, settings["enemies"], rng)
    factor = scale(players, settings["difficulty"])
    first = settings["peaceRounds"] + 1
    return [Foe(i, e, first + i * settings["enemyGap"], factor) for i, e in enumerate(picked)]
