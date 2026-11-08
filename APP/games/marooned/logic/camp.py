"""Marooned: the camp projects: the shelter (levels) and the raft (stages).

A Project is a list of stages built in order. Materials go into the current stage until it
has everything it needs; then a build check decides (checks.py): Solid finishes it,
Shaky asks for one more of one of its materials and then finishes it with no new check,
Snapped throws away half of what's in it.

    camp = Camp(player_count)
    project = camp.project("raft")       # or "shelter"
    project.put(item, n)                 # how many were accepted (up to what's missing)
    project.full()                       # everything needed is in
    project.patched                      # Shaky: the next fill finishes it without a check
    project.finish() / project.snap() / project.patch(rng)
    camp.shelter_spots()                 # sleepers the shelter fits (2 per level built)
    camp.raft_done()
    camp.public()

The stockpile is the camp tile's pile (island.py); the camp tile itself is island.camp.
"""

import math

from gamekit import LobbyError

SHELTER_PER_LEVEL = 2
SHELTER_LEVELS = [
    {"name": "Lean-to", "need": {"wood": 2, "fiber": 2}},
    {"name": "Hut", "need": {"wood": 3, "fiber": 2}},
    {"name": "Stone hut", "need": {"wood": 3, "fiber": 2, "stone": 2}},
]
# Raft amounts are for 4 players; scaled up by player count (rounded up).
RAFT_STAGES = [
    {"name": "Frame", "need": {"wood": 6, "fiber": 3}},
    {"name": "Hull", "need": {"fiber": 4, "stone": 2}},
    {"name": "Sail", "need": {"scrap": 2, "wood": 2}},
    {"name": "Provisions", "perPlayer": {"food": 1, "water": 1}},
]
RAFT_BASE_PLAYERS = 4


def raft_stages(players):
    stages = []
    for stage in RAFT_STAGES:
        if "perPlayer" in stage:
            need = {item: count * players for item, count in stage["perPlayer"].items()}
        else:
            need = {item: math.ceil(count * players / RAFT_BASE_PLAYERS) for item, count in stage["need"].items()}
        stages.append({"name": stage["name"], "need": need})
    return stages


class Project:
    def __init__(self, key, name, stages):
        self.key = key
        self.name = name
        self.stages = stages
        self.index = 0          # stages finished
        self.have = {}
        self.extra = {}         # Shaky: one more of an item
        self.patched = False

    def done(self):
        return self.index >= len(self.stages)

    def stage(self):
        return None if self.done() else self.stages[self.index]

    def need(self):
        need = dict(self.stage()["need"])
        for item, count in self.extra.items():
            need[item] = need.get(item, 0) + count
        return need

    def missing(self, item):
        if self.done():
            return 0
        return max(0, self.need().get(item, 0) - self.have.get(item, 0))

    def full(self):
        return not self.done() and all(self.missing(item) == 0 for item in self.need())

    def put(self, item, count):
        if self.done():
            raise LobbyError(f"The {self.name.lower()} is finished.")
        accepted = min(count, self.missing(item))
        if not accepted:
            raise LobbyError(f"The {self.name.lower()} doesn't need {item} right now.")
        self.have[item] = self.have.get(item, 0) + accepted
        return accepted

    def finish(self):
        self.index += 1
        self.have = {}
        self.extra = {}
        self.patched = False

    def snap(self):
        """Half of each material is lost (rounded up), so a full stage keeps the lower half."""
        self.have = {item: count // 2 for item, count in self.have.items() if count // 2}

    def patch(self, rng):
        item = rng.choice(sorted(self.stage()["need"]))
        self.extra[item] = self.extra.get(item, 0) + 1
        self.patched = True
        return item

    def public(self):
        data = {
            "name": self.name,
            "built": self.index,
            "stages": [{"name": s["name"], "need": dict(s["need"])} for s in self.stages],
        }
        if not self.done():
            data["need"] = self.need()
            data["have"] = dict(self.have)
            if self.patched:
                data["patched"] = True
        return data


class Camp:
    def __init__(self, players):
        self.shelter = Project("shelter", "Shelter", [dict(level) for level in SHELTER_LEVELS])
        self.raft = Project("raft", "Raft", raft_stages(players))

    def project(self, key):
        if key == "shelter":
            return self.shelter
        if key == "raft":
            return self.raft
        raise LobbyError("Unknown project.")

    def shelter_spots(self):
        return self.shelter.index * SHELTER_PER_LEVEL

    def raft_done(self):
        return self.raft.done()

    def public(self):
        return {"shelter": self.shelter.public(), "raft": self.raft.public(), "spots": self.shelter_spots()}
