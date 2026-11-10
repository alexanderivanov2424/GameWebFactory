"""Bastion: loading the structure files (content/structures/*.json) when the game is imported.

A structure is anything placed on the board: buildings (one tile each; each belongs to the
player who placed it) and road tiles (built by units, also owned). Fields are documented in
content/README.md. Bad files are logged (logger "bastion") and skipped.

    RESOURCES    [(id, name, icon)] in display order: each player's own stock (Seat.stock)
    COST_KEYS    what a cost may name: RESOURCE_IDS + "decrees" (royal decrees: each player's
                 per-planning-phase allowance, Seat.decrees)
    GOODS        resources but gold (the dormant enemy attacks steal/loot these)
    TERRAIN      {code letter: terrain name} for map rows; BUILDABLE terrain is "grass"
    GATHER       {terrain: resource} a unit on that terrain gathers 1 of (forest: wood, mountain: stone)
    STRUCTURES   {id: structure}, structure = {
        "id", "name", "icon", "text",
        "tile":     None for buildings, "road" for road tiles (built by units: resolution.py)
        "pieces":   [[(0, 0)]] (every structure is one tile; kept as rotations for board.py)
        "cost":     {resource or "decrees": n} paid when its blueprint is played
        "price":    gold for its blueprint in the market (None: never sold)
        "build":    build tokens it is planned with (each unit building it removes one; 0 = at once)
        "requires": [condition] that must all hold where it's planned
        "work":     None, or what a unit stationed there does every round:
                    {"makes": {resource: n}}                     automatic
                    {"uses": {resource: n}, "makes": {...}}      the owner is asked (convert)
                    {"choices": [{"uses"?, "makes"}, ...]}       the owner picks one (or none)
        "trains":   a worker placed here becomes a soldier (barracks)
        "staff":    who may be placed here: "worker" (default), "soldier" or "none" (the keep)
        "units":    workers it adds to its owner's pool when built (house 2, keep 1)
        "income":   {resource: n} its owner gets at the end of every round (the keep)
        "decrees":  royal decrees it grants its owner each planning phase (the keep: 3) }
    condition = {"near": terrain | "empty" | "road" | structure id, "min": n}
    describe(condition)   readable text ("next to a forest", "next to ≥2 mountains")
    load_structures(folder) -> STRUCTURES (tests feed temporary folders)
"""

import logging
from pathlib import Path

from gamekit.data import flag, load_json_dir, text, whole

log = logging.getLogger("bastion")

CONTENT = Path(__file__).resolve().parent.parent / "content"
RESOURCES = [("gold", "Gold", "💰"), ("wood", "Wood", "🪵"), ("stone", "Stone", "🪨"),
             ("metal", "Metal", "⛓️"), ("food", "Food", "🍞"), ("tools", "Tools", "🔨")]
RESOURCE_IDS = [r[0] for r in RESOURCES]
COST_KEYS = RESOURCE_IDS + ["decrees"]
GOODS = [r for r in RESOURCE_IDS if r != "gold"]
OUTPUT_NAMES = {**{r[0]: r[1].lower() for r in RESOURCES}, "decrees": "decrees", "soldiers": "soldiers"}
ICONS = {**{r[0]: r[2] for r in RESOURCES}, "decrees": "📜", "units": "🧍", "soldiers": "⚔️"}
TERRAIN = {".": "grass", "F": "forest", "M": "mountain", "~": "water"}
BUILDABLE = "grass"
GATHER = {"forest": "wood", "mountain": "stone"}
TILES = ("road",)
STAFF = ("worker", "soldier", "none")
SPECIAL_NEAR = ("empty", "road")
MAX_AMOUNT = 20


def amounts(data, key, allowed):
    value = data.get(key, {})
    if not isinstance(value, dict) or any(k not in allowed for k in value):
        raise ValueError(f"{key} must be an object with keys from {allowed}")
    return {k: whole(value, k, 1, MAX_AMOUNT) for k in allowed if k in value}


def condition(data):
    if not isinstance(data, dict) or not isinstance(data.get("near"), str):
        raise ValueError("each condition needs a 'near' string")
    return {"near": data["near"], "min": whole(data, "min", 1, 8, default=1)}


def parse_work(data):
    if not isinstance(data, dict):
        raise ValueError("work must be an object")

    def option(value):
        if not isinstance(value, dict):
            raise ValueError("each work option must be an object")
        makes = amounts(value, "makes", RESOURCE_IDS)
        if not makes:
            raise ValueError("work needs 'makes'")
        return {"uses": amounts(value, "uses", RESOURCE_IDS), "makes": makes}

    if "choices" in data:
        choices = data["choices"]
        if not isinstance(choices, list) or not 2 <= len(choices) <= 4:
            raise ValueError("work.choices must list 2 to 4 options")
        return {"choices": [option(c) for c in choices]}
    return option(data)


def parse_structure(structure_id, data):
    tile = data.get("tile")
    if tile is not None and tile not in TILES:
        raise ValueError(f"tile must be one of {TILES}")
    requires = data.get("requires", [])
    if not isinstance(requires, list):
        raise ValueError("requires must be a list")
    staff = data.get("staff", "worker")
    if staff not in STAFF:
        raise ValueError(f"staff must be one of {STAFF}")
    return {
        "id": structure_id,
        "name": text(data, "name", 30, required=True),
        "icon": text(data, "icon", 8),
        "text": text(data, "text", 300),
        "tile": tile,
        "pieces": [[(0, 0)]] * 4,
        "cost": amounts(data, "cost", COST_KEYS),
        "price": whole(data, "price", 0, 30) if "price" in data and not tile else None,
        "build": whole(data, "build", 0, 5, default=1),
        "requires": [condition(c) for c in requires],
        "work": parse_work(data["work"]) if "work" in data else None,
        "trains": flag(data, "trains"),
        "staff": "none" if tile else staff,
        "units": whole(data, "units", 0, 10, default=0),
        "income": amounts(data, "income", RESOURCE_IDS),
        "decrees": whole(data, "decrees", 0, 10, default=0),
    }


def check_names(structures):
    """Drop structures whose conditions name something unknown (logged)."""
    known = set(TERRAIN.values()) | set(SPECIAL_NEAR) | set(structures)
    for sid, s in list(structures.items()):
        bad = [c["near"] for c in s["requires"] if c["near"] not in known]
        if bad:
            log.error("Structure %s: unknown 'near' %s", sid, bad)
            del structures[sid]
    return structures


def load_structures(folder):
    return check_names(load_json_dir(folder, parse_structure, log))


def a(name):
    """"a Mine", "an Apothecary"."""
    return ("an " if name[:1].lower() in "aeiou" else "a ") + name


def thing_name(near, structures, plural=False):
    if near not in structures:
        name = {"empty": "empty grass"}.get(near, near)
        return name + ("s" if plural and near in ("road", "mountain", "forest") else "")
    return structures[near]["name"] + ("s" if plural else "")


def describe(cond, structures):
    near, low = cond["near"], cond["min"]
    if low > 1:
        return f"next to ≥{low} {thing_name(near, structures, plural=True)}"
    if near in structures or near in ("road", "mountain", "forest"):
        return f"next to {a(thing_name(near, structures))}"
    return f"next to {thing_name(near, structures)}"


def public(s, structures):
    """What clients get (the catalog). PatchState: no nulls in dicts."""
    view = {
        "name": s["name"], "icon": s["icon"], "text": s["text"], "tile": s["tile"] or "",
        "cost": s["cost"], "price": s["price"] if s["price"] is not None else -1, "build": s["build"],
        "requires": [describe(c, structures) for c in s["requires"]],
        "work": s["work"] or {}, "trains": s["trains"], "staff": s["staff"], "units": s["units"],
        "income": s["income"], "decrees": s["decrees"],
    }
    return view


STRUCTURES = load_structures(CONTENT / "structures")
