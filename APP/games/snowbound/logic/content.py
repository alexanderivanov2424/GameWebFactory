"""Snowbound content: machines (machines/*.json) and upgrades (upgrades/*.json + generated tiers).

Machine file <id>.json:
    {"order": 1, "name": "Snowblower", "cost": 100, "rate": 1.5, "speed": 1.5, "reach": 1.2,
     "diesel": 0.02, "icon": "🌀", "text": "...", "upgrades": ["Tier 1 name", "Tier 2 name", "Tier 3 name"]}
    rate: snow per second per machine; speed: lots per second the crew drives; reach: lots
    away it can work from; diesel: litres per second per machine (0 = needs none).
    Each machine gets one tier upgrade per name (x2 its rate), unlocked by owning
    TIER_OWNED[k] of it, costing TIER_COST[k] x its base cost.

Upgrade file <id>.json:
    {"name": "...", "cost": 100, "text": "...", "effect": {"kind": ..., "value": ...},
     "shared": true?}   shared upgrades help everyone; one purchase covers the whole team.
    Effect kinds: click_mult (x clicks), click_pct (clicks also clear value% of your machines'
    rate), auto ("rations" | "diesel" | "logs": deliveries), food_drain (x hunger), warm_loss
    (x warmth lost), stove (x logs burned, shared), dust (x blizzard snow on cleared ground,
    shared), flake (x golden snowflake rewards).
Upgrades show up once a player has earned UNLOCK_SHARE of their cost (tiers: once owned enough).
"""

import logging
from pathlib import Path

from gamekit.data import load_json_dir, text

log = logging.getLogger("snowbound")
ROOT = Path(__file__).resolve().parent.parent

TIER_OWNED = (1, 10, 25)
TIER_COST = (10, 50, 500)
UNLOCK_SHARE = 0.25
GROWTH = 1.15  # each machine of a kind costs 15% more than the last
EFFECTS = {"click_mult", "click_pct", "auto", "food_drain", "warm_loss", "stove", "dust", "flake"}
AUTO = {"rations", "diesel", "logs"}


def number(data, key, low, high):
    value = data.get(key)
    if type(value) not in (int, float) or not low <= value <= high:
        raise ValueError(f"{key} must be a number from {low} to {high}")
    return value


def parse_machine(mid, data):
    names = data.get("upgrades")
    if not isinstance(names, list) or len(names) != len(TIER_OWNED) or not all(isinstance(n, str) for n in names):
        raise ValueError(f"upgrades must list {len(TIER_OWNED)} names")
    return {
        "id": mid, "order": number(data, "order", 0, 1000),
        "name": text(data, "name", 30, required=True), "text": text(data, "text", 120),
        "icon": text(data, "icon", 4) or "?", "cost": number(data, "cost", 1, 1e15), "rate": number(data, "rate", 0.01, 1e12),
        "speed": number(data, "speed", 0.1, 50), "reach": number(data, "reach", 0.5, 10),
        "diesel": number(data, "diesel", 0, 1e9), "upgrades": [n.strip()[:30] for n in names],
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
    else:
        value = number(effect, "value", 0.01, 1000)
    return {"id": uid, "name": text(data, "name", 30, required=True), "text": text(data, "text", 160),
            "cost": number(data, "cost", 1, 1e15), "kind": kind, "value": value,
            "shared": data.get("shared") is True, "machine": None, "owned": 0}


def tier_upgrades(machines):
    """Generated per-machine upgrades: x2 that machine's rate each."""
    out = {}
    for m in machines.values():
        for k, name in enumerate(m["upgrades"]):
            uid = f"{m['id']}-tier{k + 1}"
            out[uid] = {"id": uid, "name": name, "text": f"{m['name']}s work twice as fast.",
                        "cost": m["cost"] * TIER_COST[k], "kind": "machine", "value": 2,
                        "shared": False, "machine": m["id"], "owned": TIER_OWNED[k]}
    return out


MACHINES = dict(sorted(load_json_dir(ROOT / "machines", parse_machine, log).items(),
                       key=lambda item: item[1]["order"]))
UPGRADES = {**load_json_dir(ROOT / "upgrades", parse_upgrade, log), **tier_upgrades(MACHINES)}


def machine_cost(mid, owned, count=1):
    """Price of the next `count` machines of a kind when you own `owned`."""
    base = MACHINES[mid]["cost"]
    first = base * GROWTH ** owned
    return round(first * (GROWTH ** count - 1) / (GROWTH - 1))


def defs():
    """Static definitions for the client."""
    return {
        "machines": {mid: {k: m[k] for k in ("order", "name", "icon", "text", "rate", "speed", "diesel")}
                     for mid, m in MACHINES.items()},
        "upgrades": {uid: {k: u[k] for k in ("name", "text", "cost", "shared")} for uid, u in UPGRADES.items()},
    }
