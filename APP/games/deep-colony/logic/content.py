"""Content: elements (elements/*.json) and buildings (buildings/*.json), loaded and validated at import.

Bad files are logged and skipped (gamekit.data). Everything else in logic/ reads the dicts below;
the client gets them in the public state ("defs") and draws any element or building from them.

Element file (all optional except name/phase):
    name, phase ("solid" | "liquid" | "gas" | "vacuum" | "food"), color "#rrggbb",
    classes [material classes, e.g. "raw", "metal", "fuel", "soil", "filter", "organic"],
    shc (kJ per kg per °C), conductivity (relative heat conduction), hardness (dig time factor),
    diggable (default true for solids), defaultMass (kg in a generated cell),
    decor (decor of loose debris of it), density (layering rank: gases/liquids, higher sinks),
    breathable (gases), germs (germs per kg when generated),
    freezeAt/freezeTo, meltAt/meltTo, boilAt/boilTo, condenseAt/condenseTo (°C, element id),
    freezeLatent/meltLatent/boilLatent/condenseLatent (kJ per kg absorbed or released by that
    phase change; heat.py holds the cell at the threshold until it's paid),
    offgas {"element", "rate": kg/s per exposed cell or debris pile}, kcal (food, per kg).
Building file:
    name, category, description, w, h (cells; x, y of a building = its top-left cell),
    cost {material class or element id: kg}, buildTime (s of colonist work),
    kind (behaviour key, machines.KINDS; "none" for passive),
    layer ("main" | "pipe" (liquid) | "gaspipe" | "wire"), rotatable (players may turn it),
    solid (blocks gas/liquid, can be stood on), insulated, ladder, door (solid but walkable),
    floor (bottom row needs solid ground or tiles under it), buildable (default true),
    deconstructable (default true), operated (a colonist must work at it),
    toilet (colonists relieve themselves here), bed (colonists sleep here),
    decor {"value", "radius"}, power {"use": W} | {"gen": W} | {"capacity": J},
    powerPort / pipeIn / pipeOut / gasIn / gasOut [dx, dy] (cell offsets from the top-left of the
    unrotated footprint; Building.port_cell applies the rotation),
    storage kinds: filterable (players pick which elements it accepts),
    accepts {element id: kg capacity} (colonists keep it supplied), capacity (storage kg),
    heat (kW given off while working), params {kind-specific numbers}.

Indexes for the hot loops: ELEMENT_IDS (index -> id), INDEX (id -> index), and per-index lists
PHASE, SHC, COND, DENSITY. CHARS[index] is the element's one-character code in grid rows.
"""

import logging
from pathlib import Path

from gamekit.data import load_json_dir

log = logging.getLogger("deep-colony")

ROOT = Path(__file__).resolve().parent.parent
PHASES = ("solid", "liquid", "gas", "vacuum", "food")
LAYERS = ("main", "pipe", "gaspipe", "wire")
CATEGORIES = ("base", "oxygen", "power", "food", "plumbing", "ventilation", "climate", "decor", "research")
PORTS = ("powerPort", "pipeIn", "pipeOut", "gasIn", "gasOut")
ROW_CHARS = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _num(data, key, default, low=-1e9, high=1e9):
    value = data.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be a number")
    if not low <= value <= high:
        raise ValueError(f"{key} out of range")
    return value


def _offset(data, key, w, h):
    if key not in data:
        return None
    value = data[key]
    if (not isinstance(value, list) or len(value) != 2 or any(type(v) is not int for v in value)
            or not (0 <= value[0] < w and 0 <= value[1] < h)):
        raise ValueError(f"{key} must be [dx, dy] inside the building")
    return value


def parse_element(element_id, data):
    phase = data.get("phase")
    if phase not in PHASES:
        raise ValueError("phase must be one of " + ", ".join(PHASES))
    name = data.get("name")
    if not isinstance(name, str) or not name:
        raise ValueError("name required")
    out = {
        "id": element_id, "name": name[:40], "phase": phase,
        "color": str(data.get("color", "#888888"))[:9],
        "classes": [c for c in data.get("classes", []) if isinstance(c, str)],
        "shc": _num(data, "shc", 1.0, 0.01, 100), "conductivity": _num(data, "conductivity", 1.0, 0, 100),
        "hardness": _num(data, "hardness", 1, 0, 1000),
        "diggable": phase == "solid" and data.get("diggable", True) is not False,
        "defaultMass": _num(data, "defaultMass", 1.0, 0, 100000), "decor": _num(data, "decor", 0, -100, 100),
        "density": _num(data, "density", 0, 0, 100), "breathable": data.get("breathable") is True,
        "germs": _num(data, "germs", 0, 0, 1e7), "kcal": _num(data, "kcal", 0, 0, 1e5),
    }
    for key in ("freeze", "melt", "boil", "condense"):
        if f"{key}At" in data:
            out[f"{key}At"] = _num(data, f"{key}At", 0)
            out[f"{key}To"] = str(data.get(f"{key}To", ""))
            out[f"{key}Latent"] = _num(data, f"{key}Latent", 0, 0, 1e5)
    if isinstance(data.get("offgas"), dict):
        out["offgas"] = {"element": str(data["offgas"].get("element", "")),
                         "rate": _num(data["offgas"], "rate", 0, 0, 100)}
    return out


def parse_building(building_id, data):
    name = data.get("name")
    if not isinstance(name, str) or not name:
        raise ValueError("name required")
    w, h = data.get("w", 1), data.get("h", 1)
    if type(w) is not int or type(h) is not int or not (1 <= w <= 4 and 1 <= h <= 4):
        raise ValueError("w and h must be 1-4")
    layer = data.get("layer", "main")
    if layer not in LAYERS:
        raise ValueError("bad layer")
    cost = data.get("cost", {})
    if not isinstance(cost, dict) or any(not isinstance(v, (int, float)) or v <= 0 for v in cost.values()):
        raise ValueError("cost must map materials to positive kg")
    power = data.get("power", {})
    if not isinstance(power, dict) or any(k not in ("use", "gen", "capacity") for k in power):
        raise ValueError("power keys: use, gen, capacity")
    decor = data.get("decor", {})
    accepts = data.get("accepts", {})
    if not isinstance(accepts, dict):
        raise ValueError("accepts must be a dict")
    category = data.get("category", "base")
    return {
        "id": building_id, "name": name[:40], "category": category if category in CATEGORIES else "base",
        "description": str(data.get("description", ""))[:200], "w": w, "h": h,
        "cost": {str(k): float(v) for k, v in cost.items()},
        "buildTime": _num(data, "buildTime", 5, 0, 600), "kind": str(data.get("kind", "none")),
        "layer": layer,
        **{flag: data.get(flag) is True for flag in
           ("solid", "insulated", "ladder", "door", "floor", "operated", "toilet", "rotatable",
            "filterable", "bed")},
        "buildable": data.get("buildable", True) is not False,
        "deconstructable": data.get("deconstructable", True) is not False,
        "decor": {"value": _num(decor, "value", 0, -100, 100), "radius": int(_num(decor, "radius", 0, 0, 10))},
        "power": {k: float(v) for k, v in power.items()},
        **{port: _offset(data, port, w, h) for port in PORTS},
        "accepts": {str(k): float(v) for k, v in accepts.items()},
        "capacity": _num(data, "capacity", 0, 0, 1e6), "heat": _num(data, "heat", 0, 0, 1000),
        "params": dict(data.get("params", {})) if isinstance(data.get("params"), dict) else {},
    }


ELEMENTS = load_json_dir(ROOT / "elements", parse_element, log)
BUILDINGS = load_json_dir(ROOT / "buildings", parse_building, log)

# Drop references to elements that failed to load, so the rules never meet unknown ids.
for _e in ELEMENTS.values():
    for _key in ("freeze", "melt", "boil", "condense"):
        if _e.get(f"{_key}To") is not None and _e[f"{_key}To"] not in ELEMENTS:
            _e.pop(f"{_key}At", None)
            _e.pop(f"{_key}To", None)
    if "offgas" in _e and _e["offgas"]["element"] not in ELEMENTS:
        del _e["offgas"]

ELEMENT_IDS = sorted(ELEMENTS, key=lambda i: (i != "vacuum", i))  # vacuum is index 0
INDEX = {element_id: n for n, element_id in enumerate(ELEMENT_IDS)}
VACUUM = 0
PHASE = [ELEMENTS[i]["phase"] for i in ELEMENT_IDS]
SHC = [ELEMENTS[i]["shc"] for i in ELEMENT_IDS]
COND = [ELEMENTS[i]["conductivity"] for i in ELEMENT_IDS]
DENSITY = [ELEMENTS[i]["density"] for i in ELEMENT_IDS]
CHARS = ROW_CHARS[:len(ELEMENT_IDS)]
if len(ELEMENT_IDS) > len(ROW_CHARS):
    raise RuntimeError("too many elements for one-character grid codes")


def materials_for(key):
    """Element ids a cost or accepts key matches: an element id itself, or every element of a class."""
    if key in ELEMENTS:
        return [key]
    return [i for i in ELEMENT_IDS if key in ELEMENTS[i]["classes"]]


def matches(element_id, key):
    """Whether an element satisfies a cost/accepts key (element id or material class)."""
    return element_id == key or key in ELEMENTS.get(element_id, {}).get("classes", ())


def defs():
    """Definitions for the client (static during a game)."""
    return {
        "elements": {i: {k: v for k, v in ELEMENTS[i].items() if v is not None} for i in ELEMENT_IDS},
        "order": ELEMENT_IDS, "chars": CHARS,
        "buildings": {i: {k: v for k, v in b.items() if v is not None} for i, b in BUILDINGS.items()},
    }
