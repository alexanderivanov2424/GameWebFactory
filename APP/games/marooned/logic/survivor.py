"""Marooned: one player's body and backpack: energy, hunger, health, items, tools, stats.

    s = Survivor(pid, pos)
    s.max_energy()        # BASE_ENERGY, +1 Rested, minus hunger, wounds and Sick (at least MIN_ENERGY)
    s.spend(n)            # LobbyError if there isn't enough energy
    s.capacity()          # backpack slots (PACK_SIZE, more with a Basket)
    s.space()             # free slots
    s.add(item, n)        # puts up to n in the backpack; returns how many fit
    s.remove(item, n)     # LobbyError if they aren't there
    s.public()            # what everyone sees (backpacks and tools are public)

`stats` collects what scoring and objectives need (see scoring.py / objectives.py).
"""

from gamekit import LobbyError

BASE_ENERGY = 5
PACK_SIZE = 6
MAX_HUNGER = 4
HUNGRY = 3            # from this hunger on, max energy -1; at MAX_HUNGER (starving) -2
MIN_ENERGY = 2

TOOLS = {
    "axe": {"name": "Axe", "cost": {"wood": 1, "stone": 1}, "text": "+1 Wood or Stone on a successful gather."},
    "spear": {"name": "Spear", "cost": {"wood": 2}, "text": "+1 Food on a successful gather."},
    "machete": {"name": "Machete", "cost": {"stone": 1, "scrap": 1}, "text": "Jungle and Swamp cost 1 less to enter."},
    "basket": {"name": "Basket", "cost": {"fiber": 2}, "text": "+2 backpack slots."},
}
BASKET_SLOTS = 2


class Survivor:
    def __init__(self, pid, pos):
        self.pid = pid
        self.pos = tuple(pos)
        self.hunger = 0
        self.wounds = 0
        self.sick = False
        self.rested = False       # slept sheltered last night: +1 max energy today
        self.unsheltered = 0      # unsheltered nights in a row
        self.pack = {}
        self.tools = set()
        self.arrived = 0          # when they last reached their square (camp shelter order)
        self.energy = BASE_ENERGY
        self.stats = {
            "explored": 0,          # squares explored first
            "explorePoints": 0,
            "built": 0,             # materials put into projects
            "raftWood": 0,
            "stages": 0,            # stages finished
            "given": 0,
            "attacks": [],          # public ids attacked, in order
            "woundsTaken": 0,
            "lies": 0,              # gather rolls announced worse than rolled
            "maxHunger": 0,
            "starving": 0,          # nights spent starving
            "campShelter": 0,       # nights slept in the camp shelter
            "visited": {tuple(pos)},
            "votes": [],            # ballots, one per night ("nobody" or a public id)
        }

    # --- Energy ------------------------------------------------------------------------

    def max_energy(self):
        value = BASE_ENERGY + self.rested - self.wounds - self.sick
        if self.hunger >= HUNGRY:
            value -= 1
        if self.hunger >= MAX_HUNGER:
            value -= 1
        return max(MIN_ENERGY, value)

    def spend(self, amount):
        if amount > self.energy:
            raise LobbyError(f"That needs {amount} energy; you have {self.energy}.")
        self.energy -= amount

    def lose_energy(self, amount):
        self.energy = max(0, self.energy - amount)

    # --- Backpack ----------------------------------------------------------------------

    def capacity(self):
        return PACK_SIZE + (BASKET_SLOTS if "basket" in self.tools else 0)

    def carried(self):
        return sum(self.pack.values())

    def space(self):
        return max(0, self.capacity() - self.carried())

    def has(self, item, count=1):
        return self.pack.get(item, 0) >= count

    def add(self, item, count):
        added = min(count, self.space())
        if added:
            self.pack[item] = self.pack.get(item, 0) + added
        return added

    def remove(self, item, count=1):
        if not self.has(item, count):
            raise LobbyError(f"You don't have {count} {item}.")
        self.pack[item] -= count
        if not self.pack[item]:
            del self.pack[item]

    def eat_hunger(self, amount):
        self.hunger = max(0, self.hunger - amount)

    def add_hunger(self, amount):
        self.hunger = min(MAX_HUNGER, self.hunger + amount)
        self.stats["maxHunger"] = max(self.stats["maxHunger"], self.hunger)

    # --- What clients see ----------------------------------------------------------------

    def public(self):
        data = {
            "pos": list(self.pos),
            "energy": self.energy,
            "maxEnergy": self.max_energy(),
            "hunger": self.hunger,
            "wounds": self.wounds,
            "pack": dict(self.pack),
            "capacity": self.capacity(),
            "tools": sorted(self.tools),
        }
        if self.sick:
            data["sick"] = True
        if self.rested:
            data["rested"] = True
        return data
