"""Snowbound content: machines (machines/*.json) and upgrades (upgrades/*.json).

Machine file <id>.json:
    {"order": 1, "name": "Drift Dog", "icon": "🐕", "kind": "dog", "cost": 100, "rate": 2.5,
     "speed": 3, "reach": 1, "diesel": 0, "text": "...", "placed": true?, "params": {...}?}
    kind: which behaviour in machines.py runs it (KINDS); rate: its main snow per second (what
    "rate" means depends on the kind, see machines.py); speed: lots per second it moves (0 for
    placed machines); reach: lots from its centre to a lot's centre it can work; diesel: litres
    per second while it exists (0 = none); placed: built on the lot the buyer stands on, bought
    one at a time, never moves; params: numbers the kind reads (see machines.py).

Upgrade file <id>.json:
    {"name": "...", "cost": 100, "text": "...", "effect": {"kind": ..., "value"?: ...},
     "shared": true?, "machine": id?}
    shared: one purchase covers the whole team. machine: only shown once you own that machine.
    Effect kinds: click_mult (x shovel), click_pct (swings also clear value% of your machines'
    rate), auto ("rations" | "diesel" | "logs": deliveries), food_drain (x hunger), warm_loss
    (x warmth lost), stove (x logs burned, shared), dust (x blizzard snow on cleared ground,
    shared), flake (x golden snowflake rewards), wade (you can walk on snow up to this level),
    machine_mult (x that machine's rate), flag (a rule change checked by id in code:
    Player.has(id) / Match.team_has(id)).
Upgrades without a machine show up once a player has earned UNLOCK_SHARE of their cost.
"""

import logging
from pathlib import Path

from gamekit.data import load_json_dir, text

log = logging.getLogger("snowbound")
ROOT = Path(__file__).resolve().parent.parent

UNLOCK_SHARE = 0.25
GROWTH = 1.15  # each machine of a kind costs 15% more than the last
KINDS = {"worker", "dog", "sweeper", "brazier", "buddy", "dozer", "auger", "still", "grader", "jet"}
EFFECTS = {"click_mult", "click_pct", "auto", "food_drain", "warm_loss", "stove", "dust", "flake",
           "wade", "machine_mult", "flag"}
AUTO = {"rations", "diesel", "logs"}


def number(data, key, low, high):
    value = data.get(key)
    if type(value) not in (int, float) or not low <= value <= high:
        raise ValueError(f"{key} must be a number from {low} to {high}")
    return value


def parse_machine(mid, data):
    if data.get("kind") not in KINDS:
        raise ValueError("kind must be one of " + ", ".join(sorted(KINDS)))
    params = data.get("params", {})
    if not isinstance(params, dict) or not all(type(v) in (int, float) for v in params.values()):
        raise ValueError("params must map names to numbers")
    return {
        "id": mid, "order": number(data, "order", 0, 1000), "kind": data["kind"],
        "name": text(data, "name", 30, required=True), "text": text(data, "text", 200),
        "icon": text(data, "icon", 4) or "?", "cost": number(data, "cost", 1, 1e15),
        "rate": number(data, "rate", 0.01, 1e12), "speed": number(data, "speed", 0, 50),
        "reach": number(data, "reach", 0, 20), "diesel": number(data, "diesel", 0, 1e9),
        "placed": data.get("placed") is True, "params": params,
    }


def parse_upgrade(uid, data):
    effect = data.get("effect")
    if not isinstance(effect, dict) or effect.get("kind") not in EFFECTS:
        raise ValueError("effect.kind must be one of " + ", ".join(sorted(EFFECTS)))
    kind = effect["kind"]
    if kind == "auto":
        if effect.get("value") not in AUTO:
            raise ValueError("auto effects deliver rations, diesel or logs")
        value = effect["value"]
    elif kind == "flag":
        value = None
    else:
        value = number(effect, "value", 0.01, 1000)
    machine = data.get("machine")
    if machine is not None and machine not in MACHINES:
        raise ValueError(f"unknown machine {machine!r}")
    if kind == "machine_mult" and machine is None:
        raise ValueError("machine_mult needs a machine")
    return {"id": uid, "name": text(data, "name", 30, required=True), "text": text(data, "text", 200),
            "cost": number(data, "cost", 1, 1e15), "kind": kind, "value": value,
            "shared": data.get("shared") is True, "machine": machine}


def nominal(m):
    """About how much snow per second one machine clears (for display and income-based bonuses)."""
    p = m["params"]
    if m["kind"] == "brazier":
        return m["rate"] * 12        # lots within 2
    if m["kind"] == "dozer":
        return m["rate"] * p.get("paid", 1)
    if m["kind"] == "jet":
        return m["rate"] * p.get("range", 1) / max(1, p.get("cooldown", 1))
    return m["rate"]


MACHINES = dict(sorted(load_json_dir(ROOT / "machines", parse_machine, log).items(),
                       key=lambda item: item[1]["order"]))
for _m in MACHINES.values():
    _m["nominal"] = nominal(_m)
UPGRADES = load_json_dir(ROOT / "upgrades", parse_upgrade, log)


def machine_cost(mid, owned, count=1):
    """Price of the next `count` machines of a kind when you own `owned`."""
    base = MACHINES[mid]["cost"]
    first = base * GROWTH ** owned
    return round(first * (GROWTH ** count - 1) / (GROWTH - 1))


def defs():
    """Static definitions for the client."""
    return {
        "machines": {mid: {k: m[k] for k in ("order", "name", "icon", "kind", "text", "nominal", "diesel", "placed", "reach")}
                     for mid, m in MACHINES.items()},
        "upgrades": {uid: {k: u[k] for k in ("name", "text", "cost", "shared")} for uid, u in UPGRADES.items()},
    }
