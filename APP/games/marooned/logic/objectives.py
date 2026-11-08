"""Marooned: secret objectives: loading content/objectives/*.json and checking them at the end.

Each file names a `check` (a key in CHECKS below) and an optional `param`; a new objective
is just a file unless it needs a new check. `role` says whose pool it's dealt from
("castaway" or "imposter"). At the start everyone is dealt DEALT from their pool and keeps
KEPT of them (the host can change both).

    deal(rng, role, count)          # objective ids, no repeats within one hand
    achieved(m, pid, objective_id)  # bool, at the end of the game
"""

import logging

from gamekit.data import load_json_dir, text, whole

from .content import CONTENT

log = logging.getLogger("marooned")

ROLES = ("castaway", "imposter")


def _visited_types(m, s):
    return [m.island.tile(cell)["type"] for cell in s.stats["visited"] if m.island.tile(cell)]


CHECKS = {
    "explored": lambda m, s, n: s.stats["explored"] >= n,
    "food_held": lambda m, s, n: s.pack.get("food", 0) >= n,
    "never_camp_shelter": lambda m, s, n: s.stats["campShelter"] == 0,
    "escaped_relics": lambda m, s, n: s.pid in m.escaped and s.pack.get("relic", 0) >= n,
    "most_raft_wood": lambda m, s, n: s.stats["raftWood"] > 0
    and s.stats["raftWood"] == max(p.stats["raftWood"] for p in m.people.values()),
    "summit": lambda m, s, n: "peak" in _visited_types(m, s) and _visited_types(m, s).count("hills") >= n,
    "given": lambda m, s, n: s.stats["given"] >= n,
    "max_hunger": lambda m, s, n: s.stats["maxHunger"] <= n,
    "wounded_imposter": lambda m, s, n: m.imposter is not None and s.stats["attacks"].count(m.imposter) >= n,
    "never_attacked": lambda m, s, n: not s.stats["attacks"],
    "lies": lambda m, s, n: s.stats["lies"] >= n,
    "snapped": lambda m, s, n: m.snapped >= n,
    "innocent_wounds": lambda m, s, n: sum(
        p.stats["woundsTaken"] for pid, p in m.people.items() if pid != m.imposter) >= n,
    "escaped": lambda m, s, n: s.pid in m.escaped,
}


def parse_objective(objective_id, data):
    check = data.get("check")
    if check not in CHECKS:
        raise ValueError(f"unknown check {check!r}")
    role = data.get("role", "castaway")
    if role not in ROLES:
        raise ValueError(f"role must be one of {', '.join(ROLES)}")
    return {
        "id": objective_id,
        "title": text(data, "title", 40, required=True),
        "text": text(data, "text", 200, required=True),
        "points": whole(data, "points", 0, 20, default=3),
        "role": role,
        "check": check,
        "param": whole(data, "param", 0, 99, default=0),
    }


OBJECTIVES = load_json_dir(CONTENT / "objectives", parse_objective, log)


def deal(rng, role, count):
    pool = sorted(oid for oid, o in OBJECTIVES.items() if o["role"] == role)
    return rng.sample(pool, min(count, len(pool)))


def achieved(m, pid, objective_id):
    objective = OBJECTIVES[objective_id]
    return bool(CHECKS[objective["check"]](m, m.people[pid], objective["param"]))


def public(objective_id):
    o = OBJECTIVES[objective_id]
    return {"id": objective_id, "title": o["title"], "text": o["text"], "points": o["points"]}
