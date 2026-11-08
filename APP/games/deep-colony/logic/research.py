"""Research: a shared tech tree (research/*.json) that unlocks buildings, and the Research Station.

Tech file: {"name", "cost" (research points), "requires" [tech ids], "unlocks" [building ids],
"description"}. A building that no tech unlocks is available from the start.

    research = Research(match)           match.research
    research.is_unlocked(btype) -> bool
    research.select(pid, tech_id)        any player picks what the colony studies (logged);
                                         raises LobbyError if unknown, done or prerequisites missing
    research.add_points(n)               points go into the current tech; finishing it unlocks
                                         its buildings (logged) and clears the selection
    research.public() -> {"techs": {id: {"name", "cost", "requires", "unlocks", "description",
                          "progress" (points), "done" 0/1}}, "current"?: id}
Research Station (kind "research_station", machines.py delegates here):
    wants_operator(match, b)   enabled, powered, a tech selected and dirt for a point in store
    operate(match, b, dupe, dt)  work accumulates (half speed when sick); every workPerPoint s of
                                 work uses dirtPerPoint kg of dirt and adds a point
"""

import logging
from pathlib import Path

from gamekit import LobbyError
from gamekit.data import load_json_dir

from . import content

log = logging.getLogger("deep-colony")


def parse_tech(tech_id, data):
    name = data.get("name")
    cost = data.get("cost")
    if not isinstance(name, str) or not name:
        raise ValueError("name required")
    if type(cost) is not int or not 1 <= cost <= 10000:
        raise ValueError("cost must be 1-10000")
    lists = {}
    for key in ("requires", "unlocks"):
        value = data.get(key, [])
        if not isinstance(value, list) or any(not isinstance(v, str) for v in value):
            raise ValueError(f"{key} must be a list of ids")
        lists[key] = value
    return {"id": tech_id, "name": name[:40], "cost": cost, "description": str(data.get("description", ""))[:200],
            "requires": lists["requires"], "unlocks": [u for u in lists["unlocks"] if u in content.BUILDINGS]}


TECHS = load_json_dir(content.ROOT / "research", parse_tech, log)
for _t in TECHS.values():
    _t["requires"] = [r for r in _t["requires"] if r in TECHS]
LOCKED_BY = {b: t["id"] for t in TECHS.values() for b in t["unlocks"]}  # building -> tech


class Research:
    def __init__(self, match):
        self.match = match
        self.done = set()
        self.progress = {}
        self.current = ""

    def is_unlocked(self, btype):
        tech = LOCKED_BY.get(btype)
        return tech is None or tech in self.done

    def available(self, tech_id):
        t = TECHS.get(tech_id)
        return t is not None and tech_id not in self.done and all(r in self.done for r in t["requires"])

    def select(self, pid, tech_id):
        t = TECHS.get(tech_id)
        if t is None:
            raise LobbyError("Unknown research.")
        if tech_id in self.done:
            raise LobbyError("Already researched.")
        if not self.available(tech_id):
            raise LobbyError("Research its prerequisites first.")
        if tech_id != self.current:
            self.current = tech_id
            self.match.log(f"{self.match.names.get(pid, pid)} set research: {t['name']}.")

    def add_points(self, n):
        t = TECHS.get(self.current)
        if t is None:
            return
        self.progress[t["id"]] = self.progress.get(t["id"], 0) + n
        if self.progress[t["id"]] >= t["cost"]:
            self.done.add(t["id"])
            self.current = ""
            names = ", ".join(content.BUILDINGS[b]["name"] for b in t["unlocks"])
            self.match.log(f"Research done: {t['name']}." + (f" Unlocked {names}." if names else ""))

    def public(self):
        out = {"techs": {tid: {"name": t["name"], "cost": t["cost"], "requires": t["requires"],
                               "unlocks": t["unlocks"], "description": t["description"],
                               "progress": int(self.progress.get(tid, 0)), "done": 1 if tid in self.done else 0}
                         for tid, t in TECHS.items()}}
        if self.current:
            out["current"] = self.current
        return out


def wants_operator(match, b):
    p = b.d["params"]
    b.state["active"] = bool(b.enabled and match.research.current and b.stored("dirt") >= p["dirtPerPoint"])
    return b.state["active"] and b.powered


def operate(match, b, dupe, dt):
    if not b.powered:
        return
    p = b.d["params"]
    b.state["work"] = b.state.get("work", 0.0) + dt * (0.5 if getattr(dupe, "sick", 0) > 0 else 1.0)
    if b.state["work"] >= p["workPerPoint"] and b.stored("dirt") >= p["dirtPerPoint"]:
        b.state["work"] = 0.0
        b.take("dirt", p["dirtPerPoint"])
        match.research.add_points(1)


def step(match, b, dt):
    """Per-step status for the station (machines.step calls it)."""
    p = b.d["params"]
    if not b.enabled:
        b.status, b.state["active"] = "Disabled", False
    elif not match.research.current:
        b.status, b.state["active"] = "Pick a research", False
    elif b.stored("dirt") < p["dirtPerPoint"]:
        b.status, b.state["active"] = "No dirt", False
    else:
        b.state["active"] = True
        b.status = "Researching" if b.powered else "No power"
