"""Bastion: loading the structure files (content/structures/*.json) when the game is imported.

A structure is anything placed on the board: buildings (several cells, worked by cards for
goods), and the two tile kinds, roads and walls (cell sets, never worked). Fields are
documented in content/README.md. Bad files are logged (logger "bastion") and skipped.

    RESOURCES    [(id, name, icon)] in display order. GOODS are the ones stored in buildings and
                 hauled; gold is paid straight into the stockpile.
    OUTPUTS      what a building's work may make: GOODS + gold, soldiers, keep (health), cure
    TERRAIN      {code letter: terrain name} for map rows; BUILDABLE terrain is "grass"
    STRUCTURES   {id: structure}, structure = {
        "id", "name", "icon", "text",
        "tile":     None for buildings, "road" or "wall" for tiles
        "pieces":   4 rotations (gamekit.shapes), each [(dy, dx)]; "sizes": [(h, w)] each
        "cost":     {resource: n} paid from the stockpile to build it
        "price":    gold for its blueprint in the market (None: never sold)
        "reusable": the blueprint stays in the deck after building (roads and walls)
        "requires": [condition] that must all hold where it's placed
        "work":     None or {"uses": {resource: n}, "makes": {output: n}} (one output)
        "bonuses":  [condition with "bonus" (min) or "each" (per thing, up to "max")]
        "income":   {resource: n} made at the end of every round without a card (the keep)
        "depot":    goods made next to it go straight to the stockpile; roads deliver here
        "protects": radius (cells, square) of raid protection around it (0: none)
        "population": people living there (cottages): each Haul moves 1 more good per person
        "card":     card id added to the builder's deck when built (None: none); buildings that
                    work get a crew card "crew-<id>" (named "crew") unless "card" names another
        "crew":     the crew card's name }
    condition = {"near": terrain | "empty" | "road" | "wall" | structure id, "min": n, ...}
    describe(condition)   readable text ("next to ≥3 forest", "per Cottage next to it (max 3)")
    load_structures(folder) -> STRUCTURES (tests feed temporary folders)
"""

import logging
from pathlib import Path

from gamekit.data import flag, load_json_dir, text, whole
from gamekit.shapes import parse, rotations

log = logging.getLogger("bastion")

CONTENT = Path(__file__).resolve().parent.parent / "content"
RESOURCES = [("gold", "Gold", "💰"), ("wood", "Wood", "🪵"), ("stone", "Stone", "🪨"),
             ("ore", "Ore", "⛓️"), ("food", "Food", "🌾"), ("tools", "Tools", "🔨")]
RESOURCE_IDS = [r[0] for r in RESOURCES]
GOODS = ["wood", "stone", "ore", "food", "tools"]
OUTPUTS = RESOURCE_IDS + ["soldiers", "keep", "cure"]
OUTPUT_NAMES = {**{r[0]: r[1].lower() for r in RESOURCES}, "soldiers": "soldiers", "keep": "keep health",
                "cure": "plague cured"}
TERRAIN = {".": "grass", "F": "forest", "M": "mountain", "~": "water"}
BUILDABLE = "grass"
TILES = ("road", "wall")
SPECIAL_NEAR = ("empty", "road", "wall")
MAX_AMOUNT = 20


def amounts(data, key, allowed):
    value = data.get(key, {})
    if not isinstance(value, dict) or any(k not in allowed for k in value):
        raise ValueError(f"{key} must be an object with keys from {allowed}")
    return {k: whole(value, k, 1, MAX_AMOUNT) for k in allowed if k in value}


def condition(data, with_bonus):
    if not isinstance(data, dict) or not isinstance(data.get("near"), str):
        raise ValueError("each condition needs a 'near' string")
    cond = {"near": data["near"], "min": whole(data, "min", 1, 8, default=1)}
    if with_bonus:
        if "each" in data:
            cond["each"] = whole(data, "each", -5, 5)
            cond["max"] = whole(data, "max", 1, 8, default=8)
        else:
            cond["bonus"] = whole(data, "bonus", -5, 5)
    return cond


def conditions(data, key, with_bonus):
    value = data.get(key, [])
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a list")
    return [condition(c, with_bonus) for c in value]


def parse_structure(structure_id, data):
    cells, height, width = parse(data.get("shape"), max_size=4)
    pieces, sizes = rotations(cells, height, width)
    tile = data.get("tile")
    if tile is not None and tile not in TILES:
        raise ValueError(f"tile must be one of {TILES}")
    work = None
    if "work" in data:
        if not isinstance(data["work"], dict):
            raise ValueError("work must be an object")
        makes = amounts(data["work"], "makes", OUTPUTS)
        if len(makes) != 1:
            raise ValueError("work.makes needs exactly one output")
        work = {"uses": amounts(data["work"], "uses", RESOURCE_IDS), "makes": makes}
    name = text(data, "name", 30, required=True)
    card = data.get("card")
    if card is not None and not isinstance(card, str):
        raise ValueError("card must be a card id")
    if card is None and work:
        card = f"crew-{structure_id}"
    return {
        "id": structure_id,
        "name": name,
        "icon": text(data, "icon", 8),
        "text": text(data, "text", 300),
        "tile": tile,
        "pieces": pieces,
        "sizes": sizes,
        "cost": amounts(data, "cost", RESOURCE_IDS),
        "price": whole(data, "price", 0, 30) if "price" in data else None,
        "reusable": flag(data, "reusable"),
        "requires": conditions(data, "requires", False),
        "work": work,
        "bonuses": conditions(data, "bonuses", True) if work else [],
        "income": amounts(data, "income", RESOURCE_IDS),
        "depot": flag(data, "depot"),
        "protects": whole(data, "protects", 0, 5, default=0),
        "population": whole(data, "population", 0, 5, default=0),
        "card": card,
        "crew": text(data, "crew", 30) or f"{name} Crew",
    }


def check_names(structures):
    """Drop structures whose conditions name something unknown (logged)."""
    known = set(TERRAIN.values()) | set(SPECIAL_NEAR) | set(structures)
    for sid, s in list(structures.items()):
        bad = [c["near"] for c in s["requires"] + s["bonuses"] if c["near"] not in known]
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
    if near in TILES or near not in structures:
        name = {"empty": "empty grass"}.get(near, near)
        return name + ("s" if plural and near in ("road", "wall", "mountain") else "")
    return structures[near]["name"] + ("s" if plural else "")


def describe(cond, structures):
    near, low = cond["near"], cond["min"]
    if "each" in cond:
        return f"per {thing_name(near, structures)} next to it (max {cond['max']})"
    if low > 1:
        return f"next to ≥{low} {thing_name(near, structures, plural=True)}"
    if near in structures or near in ("road", "wall", "mountain"):
        return f"next to {a(thing_name(near, structures))}"
    return f"next to {thing_name(near, structures)}"


def public(s, structures):
    """What clients get (the catalog): shapes as rotations of [dx, dy] plus text to show."""
    view = {
        "name": s["name"], "icon": s["icon"], "text": s["text"], "tile": s["tile"],
        "rotations": [[[dx, dy] for dy, dx in piece] for piece in s["pieces"]],
        "cost": s["cost"], "price": s["price"], "reusable": s["reusable"],
        "requires": [describe(c, structures) for c in s["requires"]],
        "work": s["work"],
        "bonuses": [[describe(c, structures), c.get("bonus", c.get("each"))] for c in s["bonuses"]],
        "income": s["income"], "depot": s["depot"], "protects": s["protects"], "card": s["card"],
        "population": s["population"],
    }
    return {k: v for k, v in view.items() if v is not None}  # PatchState: no nulls in dicts


STRUCTURES = load_structures(CONTENT / "structures")
