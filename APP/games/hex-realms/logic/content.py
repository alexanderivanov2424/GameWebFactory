"""Hex Realms: game content loaded from JSON at import (bad files are logged and skipped).

    from .content import STRUCTURES, UNITS, ADVANCES, TERRAIN, RESOURCES, footprint

TERRAIN      {id: {"name", "move" (half steps, None = impassable), "cover" (hits need 5+), "build"}}
RESOURCES    stock resources in display order ("people" is separate)
RESOURCE_INFO  {res: (name, icon)} for the client, incl. people, population, housing
structures/<id>.json:
    name, icon, color ("#rrggbb" map colour), cells [[q, r], ...] (axial, first = anchor)
    cost {res: n} (no food), hp (0 = unattackable), defense (dice it rolls back), jobs (people to work)
    produce {res: n} (output never below 0), onTerrain {terrain: {res: n}} (anchor's terrain, replaces produce)
    perCell {terrain: {res: n}} (per own cell), perAdjacent {"terrain"|"type"|"tag", "gain", "max"} (or a list; terrain counts only cells with nothing built)
    tags [TAG ids], housing, storage (room for each stored good: wood, stone, metal), store {res: n}
    terrain [ids] (default: buildable), coast (touches water), requires (advance), recruits [unit ids]
    heals, shoots (dice) + range, trade (give n for 1), score, hammers (work to build, default 1)
    boost [{"type"|"tag", "add"}] (while it works: +add to each resource an adjacent own structure of that
    type / with that tag makes), freeNear (terrain id: needs no workers while touching that terrain)
    category (CATEGORIES id), vision (cells seen around each cell, default 3)
units/<id>.json:
    name, icon, art (client/art/units/ file, drawn instead of icon), cost {res: n} (no food), people (default 1)
    attack, defense, hp, move (steps), range (shoots instead of moving), siege (damage per hit on structures)
    vsMounted (extra dice vs mounted), mounted, naval (water only), settler (founds a Town Hall)
    requires (advance), needs (structure type owned), upkeep {res: n}, vision (default 2)
advances/<id>.json:
    name, cost {"science"|"faith": n}, after [advance ids], effect {towerDice|attackDice|defendDice: n},
    bonus {structure type: {res: n}} (added to its output), housing {tag: n} (per own structure with the tag)
Descriptions players read are in client/text.js, not here.
"""

import logging
import re
from pathlib import Path

from gamekit.data import load_json_dir, text, whole
from gamekit.hexes import rotations

log = logging.getLogger(__name__)
HERE = Path(__file__).resolve().parent.parent

RESOURCES = ["gold", "food", "wood", "stone", "metal", "faith", "science"]
# For the client; icons are placeholders for art.
RESOURCE_INFO = {"gold": ("Gold", "🪙"), "food": ("Food", "🍞"), "wood": ("Wood", "🪵"), "stone": ("Stone", "🪨"),
                 "metal": ("Metal", "🔩"), "faith": ("Faith", "🙏"), "science": ("Science", "🔬"),
                 "people": ("People", "👥"), "population": ("Population", "👥"), "housing": ("Housing", "🏠"), "hammers": ("Hammers", "🔨")}
CAPPED = ["wood", "stone", "metal"]  # goods: kept in stores (logistics.py)
GLOBAL = ["gold"]  # realm-wide, kept from turn to turn, uncapped
FLAT = ["faith", "science"]  # what working structures give now, minus what advances spent (logistics.py)
SPENDABLE = GLOBAL + FLAT + CAPPED  # what costs may ask for (food is never stored, so never spent)
TERRAIN = {
    "plains": {"name": "Plains", "move": 2, "cover": False, "build": True},
    "desert": {"name": "Desert", "move": 2, "cover": False, "build": True},
    "forest": {"name": "Forest", "move": 4, "cover": True, "build": True},
    "hills": {"name": "Hills", "move": 4, "cover": True, "build": True},
    "mountain": {"name": "Mountains", "move": None, "cover": True, "build": False},
    "water": {"name": "Water", "move": None, "cover": False, "build": False},
}
CATEGORIES = {"defense": "Defense", "homes": "Homes", "food": "Food", "industry": "Industry", "trade": "Trade",
              "military": "Military", "culture": "Learning & Faith", "city": "City"}  # build menu tabs, in order
# {id: (name, pip colour)}; perAdjacent can count them.
TAGS = {"industrial": ("Industrial", "#a0643c"), "food": ("Food", "#c9a93a"), "home": ("Home", "#c97b5b"),
        "storage": ("Storage", "#4f86c6"), "military": ("Military", "#b8433a"), "defense": ("Defense", "#7d8794"),
        "trade": ("Trade", "#d9b13b"), "culture": ("Culture", "#8e5bb5"), "civic": ("Civic", "#5f9e8f")}
EFFECTS = {"towerDice", "defendDice", "attackDice"}


def res_map(data, k, keys=RESOURCES, low=0):
    v = data.get(k, {})
    if not isinstance(v, dict) or any(r not in keys or type(n) is not int or not low <= n <= 999 for r, n in v.items()):
        raise ValueError(f"{k} must map resources to whole numbers")
    return dict(v)


def terrain_list(data, k, default):
    v = data.get(k, default)
    if not isinstance(v, list) or any(t not in TERRAIN for t in v):
        raise ValueError(f"{k} must list terrain ids")
    return list(v)


def tag_list(d):
    v = d.get("tags", [])
    if not isinstance(v, list) or any(t not in TAGS for t in v):
        raise ValueError(f"tags must list ids from {sorted(TAGS)}")
    return list(v)


def parse_structure(sid, d):
    cells = d.get("cells")
    if not isinstance(cells, list) or not 1 <= len(cells) <= 7 or any(
            not isinstance(c, list) or len(c) != 2 or any(type(x) is not int for x in c) for c in cells) or cells[0] != [0, 0]:
        raise ValueError("cells must be [[0, 0], [q, r], ...]")
    s = {
        "id": sid, "name": text(d, "name", 30, required=True), "icon": text(d, "icon", 4), "cells": cells,
        "cost": res_map(d, "cost", SPENDABLE), "hp": whole(d, "hp", 0, 99, default=3), "defense": whole(d, "defense", 0, 9, default=0),
        "jobs": whole(d, "jobs", 0, 9, default=0), "produce": res_map(d, "produce"),
        "housing": whole(d, "housing", 0, 99, default=0), "tags": tag_list(d),
        "storage": whole(d, "storage", 0, 999, default=0), "store": res_map(d, "store", CAPPED),
        "terrain": terrain_list(d, "terrain", [t for t, v in TERRAIN.items() if v["build"]]),
        "coast": d.get("coast") is True, "requires": d.get("requires"), "recruits": list(d.get("recruits", [])),
        "heals": d.get("heals") is True, "shoots": whole(d, "shoots", 0, 9, default=0), "range": whole(d, "range", 0, 5, default=0),
        "trade": whole(d, "trade", 0, 9, default=0), "vision": whole(d, "vision", 0, 9, default=3),
        "score": whole(d, "score", 0, 99, default=0),
        "hammers": whole(d, "hammers", 1, 99, default=1),
    }
    s["freeNear"] = d.get("freeNear")
    if s["freeNear"] is not None and s["freeNear"] not in TERRAIN:
        raise ValueError("freeNear must be a terrain id")
    boosts = d.get("boost", [])
    s["boost"] = []
    for b in boosts if isinstance(boosts, list) else [boosts]:
        if not isinstance(b, dict) or (b.get("tag") is None) == (b.get("type") is None) or \
                (b.get("tag") is not None and b["tag"] not in TAGS):
            raise ValueError(f"boost needs a type or a tag from {sorted(TAGS)}")
        s["boost"].append({"type": b.get("type"), "tag": b.get("tag"), "add": whole(b, "add", 1, 9)})
    s["color"] = d.get("color", "#a0a0a0")
    if not isinstance(s["color"], str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", s["color"]):
        raise ValueError("color must be like #a0b0c0")
    s["category"] = d.get("category", "city")
    if s["category"] not in CATEGORIES:
        raise ValueError(f"category must be one of {sorted(CATEGORIES)}")
    s["perCell"] = {t: res_map(d["perCell"], t) for t in d.get("perCell", {}) if t in TERRAIN}
    s["onTerrain"] = {t: res_map(d["onTerrain"], t) for t in d.get("onTerrain", {}) if t in TERRAIN}
    adjs = d.get("perAdjacent", [])
    s["perAdjacent"] = []
    for adj in adjs if isinstance(adjs, list) else [adjs]:
        if not isinstance(adj, dict):
            raise ValueError("perAdjacent must be an object or a list of them")
        if adj.get("tag") is not None and adj["tag"] not in TAGS:
            raise ValueError(f"perAdjacent tag must be one of {sorted(TAGS)}")
        s["perAdjacent"].append({"terrain": adj.get("terrain"), "type": adj.get("type"), "tag": adj.get("tag"),
                                 "gain": res_map(adj, "gain", low=-99),
                                 "max": whole(adj, "max", 1, 9, default=4)})
    s["rotations"] = [[[q, r] for q, r in rot] for rot in rotations(cells)]
    return s


def parse_unit(uid, d):
    return {
        "id": uid, "name": text(d, "name", 30, required=True), "icon": text(d, "icon", 3), "art": text(d, "art", 60), "cost": res_map(d, "cost", SPENDABLE),
        "people": whole(d, "people", 0, 9, default=1), "attack": whole(d, "attack", 0, 9), "defense": whole(d, "defense", 0, 9),
        "hp": whole(d, "hp", 1, 20), "move": whole(d, "move", 0, 9), "range": whole(d, "range", 0, 5, default=0),
        "siege": whole(d, "siege", 1, 9, default=1), "vsMounted": whole(d, "vsMounted", 0, 9, default=0),
        "mounted": d.get("mounted") is True, "naval": d.get("naval") is True, "settler": d.get("settler") is True,
        "requires": d.get("requires"), "needs": d.get("needs"), "upkeep": res_map(d, "upkeep"),
        "vision": whole(d, "vision", 0, 9, default=2),
    }


def parse_advance(aid, d):
    cost = res_map(d, "cost", ["science", "faith"])
    if len(cost) != 1:
        raise ValueError("cost must be science or faith")
    effect = d.get("effect", {})
    if not isinstance(effect, dict) or any(k not in EFFECTS or type(v) is not int for k, v in effect.items()):
        raise ValueError(f"effect keys must be from {sorted(EFFECTS)}")
    bonus = d.get("bonus", {})
    if not isinstance(bonus, dict) or any(t not in STRUCTURES for t in bonus):
        raise ValueError("bonus must map structure types to {res: n}")
    housing = d.get("housing", {})
    if not isinstance(housing, dict) or any(t not in TAGS or type(n) is not int for t, n in housing.items()):
        raise ValueError(f"housing must map tags from {sorted(TAGS)} to whole numbers")
    return {"id": aid, "name": text(d, "name", 30, required=True), "cost": cost, "after": list(d.get("after", [])),
            "effect": dict(effect), "bonus": {t: res_map(bonus, t) for t in bonus}, "housing": dict(housing)}


STRUCTURES = load_json_dir(HERE / "structures", parse_structure, log)
UNITS = load_json_dir(HERE / "units", parse_unit, log)
ADVANCES = load_json_dir(HERE / "advances", parse_advance, log)
TOWN_HALL = "town_hall"


def footprint(stype, at, rot):
    """Keys covered by structure `stype` anchored at `at`, turned `rot` times (60 degrees each)."""
    q, r = (int(x) for x in at.split(","))
    return [f"{q + dq},{r + dr}" for dq, dr in STRUCTURES[stype]["rotations"][rot % 6]]
