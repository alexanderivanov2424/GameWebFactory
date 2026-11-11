"""Hex Realms: game content loaded from JSON at import (bad files are logged and skipped).

    from .content import STRUCTURES, UNITS, ADVANCES, TERRAIN, RESOURCES, footprint

TERRAIN      {id: {"name", "move" (cost in half steps, None = impassable for land units),
             "cover" (hitting a unit here needs 5+), "build" (ordinary structures allowed)}}
RESOURCES    stock resources in display order; "people" is separate (population)
RESOURCE_INFO  {res: (name, icon)} for the client, people included
structures/<id>.json:
    name, icon (an emoji or short text drawn on the map; placeholder for art), cells [[q, r], ...] (axial offsets, first = anchor),
    cost {res: n}, hp (0 = can't be attacked; roads), defense (dice it rolls back at attackers),
    jobs (people needed to work), produce {res: n}, perCell {terrain: {res: n}} (per own cell),
    onTerrain {terrain: {res: n}} (by the anchor's terrain, replaces produce), perAdjacent
    {"terrain"|"type"|"home": ..., "gain": {res: n}, "max": n} (per neighbouring forest cell /
    structure of that type / home structure), housing, home (counts as a home), storage (all
    capped resources), store {res: n} (a structure with either is a store of goods: see
    logistics.py), navigable (part of road networks: roads that touch it are linked through it,
    roads.py), growth (extra growth per turn), territory (claim radius,
    default 2), terrain [ids] (default every "build" terrain), coast (a cell must touch water),
    requires (advance id), recruits [unit ids], heals, shoots (dice) + range, trade (market
    rate: give n for 1), score, buildTurns (turns of work to build it, default 1), builders (idle
    people it needs for each of those turns, default 1; construction.py), category (a CATEGORIES id: the build menu's tabs), vision (fog of
    war: cells seen around each of its cells, default 3), text.
units/<id>.json:
    name, icon, cost {res: n}, people (default 1), attack, defense, hp, move (steps), range
    (shoots instead of moving), siege (damage per hit on structures, default 1), vsMounted (extra
    dice against mounted), mounted, naval (water only), settler (can found a Town Hall),
    requires (advance), needs (a structure type the owner must own), upkeep {res: n}, vision (cells
    seen around it, default 2), text.
advances/<id>.json:
    name, cost {"science"|"faith": n}, after [advance ids], effect {key: n}, text.
    Effect keys: towerDice, farmFood, homeHousing, defendDice, chapelGold, attackDice.
"""

import logging
from pathlib import Path

from gamekit.data import load_json_dir, text, whole
from gamekit.hexes import rotations

log = logging.getLogger(__name__)
HERE = Path(__file__).resolve().parent.parent

RESOURCES = ["gold", "food", "wood", "stone", "metal", "faith", "science"]
# Name and icon of each resource (plus people) for the client; icons are placeholders for art.
RESOURCE_INFO = {"gold": ("Gold", "🪙"), "food": ("Food", "🍞"), "wood": ("Wood", "🪵"), "stone": ("Stone", "🪨"),
                 "metal": ("Metal", "🔩"), "faith": ("Faith", "🙏"), "science": ("Science", "🔬"),
                 "people": ("People", "👥")}
CAPPED = ["food", "wood", "stone", "metal"]  # goods: kept in stores (logistics.py)
GLOBAL = ["gold", "faith", "science"]  # realm-wide, uncapped
TERRAIN = {
    "grass": {"name": "Grassland", "move": 2, "cover": False, "build": True},
    "plains": {"name": "Plains", "move": 2, "cover": False, "build": True},
    "desert": {"name": "Desert", "move": 2, "cover": False, "build": True},
    "forest": {"name": "Forest", "move": 4, "cover": True, "build": True},
    "hills": {"name": "Hills", "move": 4, "cover": True, "build": True},
    "mountain": {"name": "Mountains", "move": None, "cover": True, "build": False},
    "water": {"name": "Water", "move": None, "cover": False, "build": False},
}
ROAD_MOVE = 1  # half steps per road cell
CATEGORIES = {"roads": "Roads & Defense", "homes": "Homes", "food": "Food", "industry": "Industry", "trade": "Trade",
              "military": "Military", "culture": "Learning & Faith", "city": "City"}  # build menu tabs, in order
EFFECTS = {"towerDice", "farmFood", "homeHousing", "defendDice", "chapelGold", "attackDice"}


def res_map(data, k, keys=RESOURCES):
    v = data.get(k, {})
    if not isinstance(v, dict) or any(r not in keys or type(n) is not int or not 0 <= n <= 999 for r, n in v.items()):
        raise ValueError(f"{k} must map resources to whole numbers")
    return dict(v)


def terrain_list(data, k, default):
    v = data.get(k, default)
    if not isinstance(v, list) or any(t not in TERRAIN for t in v):
        raise ValueError(f"{k} must list terrain ids")
    return list(v)


def parse_structure(sid, d):
    cells = d.get("cells")
    if not isinstance(cells, list) or not 1 <= len(cells) <= 7 or any(
            not isinstance(c, list) or len(c) != 2 or any(type(x) is not int for x in c) for c in cells) or cells[0] != [0, 0]:
        raise ValueError("cells must be [[0, 0], [q, r], ...]")
    s = {
        "id": sid, "name": text(d, "name", 30, required=True), "icon": text(d, "icon", 4), "cells": cells,
        "cost": res_map(d, "cost"), "hp": whole(d, "hp", 0, 99, default=3), "defense": whole(d, "defense", 0, 9, default=0),
        "jobs": whole(d, "jobs", 0, 9, default=0), "produce": res_map(d, "produce"),
        "housing": whole(d, "housing", 0, 99, default=0), "home": d.get("home") is True,
        "storage": whole(d, "storage", 0, 999, default=0), "store": res_map(d, "store", CAPPED),
        "growth": whole(d, "growth", 0, 9, default=0), "territory": whole(d, "territory", 0, 5, default=2),
        "terrain": terrain_list(d, "terrain", [t for t, v in TERRAIN.items() if v["build"]]),
        "coast": d.get("coast") is True, "requires": d.get("requires"), "recruits": list(d.get("recruits", [])),
        "heals": d.get("heals") is True, "shoots": whole(d, "shoots", 0, 9, default=0), "range": whole(d, "range", 0, 5, default=0),
        "trade": whole(d, "trade", 0, 9, default=0), "vision": whole(d, "vision", 0, 9, default=3),
        "score": whole(d, "score", 0, 99, default=0), "text": text(d, "text", 300),
        "buildTurns": whole(d, "buildTurns", 1, 9, default=1), "builders": whole(d, "builders", 1, 9, default=1),
    }
    s["category"] = d.get("category", "city")
    if s["category"] not in CATEGORIES:
        raise ValueError(f"category must be one of {sorted(CATEGORIES)}")
    s["navigable"] = d.get("navigable") is True
    s["perCell"] = {t: res_map(d["perCell"], t) for t in d.get("perCell", {}) if t in TERRAIN}
    s["onTerrain"] = {t: res_map(d["onTerrain"], t) for t in d.get("onTerrain", {}) if t in TERRAIN}
    adj = d.get("perAdjacent")
    if adj is not None:
        if not isinstance(adj, dict):
            raise ValueError("perAdjacent must be an object")
        s["perAdjacent"] = {"terrain": adj.get("terrain"), "type": adj.get("type"), "home": adj.get("home") is True,
                            "gain": res_map(adj, "gain"), "max": whole(adj, "max", 1, 9, default=4)}
    s["rotations"] = [[[q, r] for q, r in rot] for rot in rotations(cells)]
    return s


def parse_unit(uid, d):
    return {
        "id": uid, "name": text(d, "name", 30, required=True), "icon": text(d, "icon", 3), "cost": res_map(d, "cost"),
        "people": whole(d, "people", 0, 9, default=1), "attack": whole(d, "attack", 0, 9), "defense": whole(d, "defense", 0, 9),
        "hp": whole(d, "hp", 1, 20), "move": whole(d, "move", 0, 9), "range": whole(d, "range", 0, 5, default=0),
        "siege": whole(d, "siege", 1, 9, default=1), "vsMounted": whole(d, "vsMounted", 0, 9, default=0),
        "mounted": d.get("mounted") is True, "naval": d.get("naval") is True, "settler": d.get("settler") is True,
        "requires": d.get("requires"), "needs": d.get("needs"), "upkeep": res_map(d, "upkeep"),
        "vision": whole(d, "vision", 0, 9, default=2), "text": text(d, "text", 300),
    }


def parse_advance(aid, d):
    cost = res_map(d, "cost", ["science", "faith"])
    if len(cost) != 1:
        raise ValueError("cost must be science or faith")
    effect = d.get("effect", {})
    if not isinstance(effect, dict) or any(k not in EFFECTS or type(v) is not int for k, v in effect.items()):
        raise ValueError(f"effect keys must be from {sorted(EFFECTS)}")
    return {"id": aid, "name": text(d, "name", 30, required=True), "cost": cost, "after": list(d.get("after", [])),
            "effect": dict(effect), "text": text(d, "text", 300)}


STRUCTURES = load_json_dir(HERE / "structures", parse_structure, log)
UNITS = load_json_dir(HERE / "units", parse_unit, log)
ADVANCES = load_json_dir(HERE / "advances", parse_advance, log)
TOWN_HALL = "town_hall"
ROAD = "road"


def footprint(stype, at, rot):
    """The keys covered by structure `stype` anchored at key `at` with `rot` 60-degree turns."""
    q, r = (int(x) for x in at.split(","))
    return [f"{q + dq},{r + dr}" for dq, dr in STRUCTURES[stype]["rotations"][rot % 6]]
