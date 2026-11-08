"""Gilded Trail: loaders for the content files next to server.py (cards/*.json, maps/*.json).

    CARDS   {card id: {"id", "name", "kind", "value", "cost"?, "single", "effect"?, "text"}}
            kind: "machete" | "paddle" | "coin" (movement on that terrain; coins also buy),
                  "joker" (any one of the three), "action" (played for its effect).
            effect (actions only): {"draw": n, "remove": n, "free": true, "guide": true}
            Cards without a cost are starting cards and never sold.
    MAPS    {map id: {"id", "name", "order", "text", "dirs", "weights", "hazards", "seed"}}
            (fields explained in logic/board.py)

Bad files are logged and skipped (gamekit.data). The rules that use these are in market.py,
movement.py and actions.py.
"""

import logging
from pathlib import Path

from gamekit.data import flag, load_json_dir, text, whole

log = logging.getLogger("gilded-trail")
ROOT = Path(__file__).resolve().parent.parent

MOVE_KINDS = ("machete", "paddle", "coin")
CARD_KINDS = MOVE_KINDS + ("joker", "action")
EFFECTS = ("draw", "remove", "free", "guide")
TERRAIN_WEIGHTS = MOVE_KINDS + ("mountain",)


def parse_card(card_id, data):
    kind = data.get("kind")
    if kind not in CARD_KINDS:
        raise ValueError(f"kind must be one of {', '.join(CARD_KINDS)}")
    card = {
        "id": card_id,
        "name": text(data, "name", 30, required=True),
        "kind": kind,
        "value": whole(data, "value", 0, 9, default=0),
        "single": flag(data, "single"),
        "text": text(data, "text", 200),
    }
    if "cost" in data:
        card["cost"] = whole(data, "cost", 0, 20)
    if kind == "action":
        effect = data.get("effect")
        if not isinstance(effect, dict) or not effect or any(key not in EFFECTS for key in effect):
            raise ValueError(f"action cards need an effect using {', '.join(EFFECTS)}")
        card["effect"] = {
            key: (whole(effect, key, 1, 5) if key in ("draw", "remove") else flag(effect, key))
            for key in effect
        }
    elif card["value"] < 1:
        raise ValueError("movement cards need a value of 1 or more")
    return card


def parse_map(map_id, data):
    dirs = data.get("dirs")
    if type(dirs) is not list or not 1 <= len(dirs) <= 10 or any(type(d) is not int or not 0 <= d <= 5 for d in dirs):
        raise ValueError("dirs must be 1-10 directions, each 0-5")
    weights = data.get("weights")
    if not isinstance(weights, dict) or set(weights) != set(TERRAIN_WEIGHTS) or any(
            type(w) not in (int, float) or w < 0 for w in weights.values()):
        raise ValueError(f"weights must give {', '.join(TERRAIN_WEIGHTS)} as numbers >= 0")
    hazards = data.get("hazards", 1)
    if type(hazards) not in (int, float) or not 0 <= hazards <= 4:
        raise ValueError("hazards must be a number from 0 to 4")
    return {
        "id": map_id,
        "name": text(data, "name", 40, required=True),
        "order": whole(data, "order", 0, 1000, default=100),
        "text": text(data, "text", 200),
        "dirs": dirs,
        "weights": weights,
        "hazards": hazards,
        "seed": whole(data, "seed", 1, 2**31 - 1),
    }


CARDS = load_json_dir(ROOT / "cards", parse_card, log)
MAPS = dict(sorted(load_json_dir(ROOT / "maps", parse_map, log).items(), key=lambda item: item[1]["order"]))
