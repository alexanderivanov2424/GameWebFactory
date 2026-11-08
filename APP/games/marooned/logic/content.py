"""Marooned: loaders for the content files in ../content/ (tiles, finds, build-check cards).

Each folder holds one JSON file per item; the fields are described in content/README.md.
Bad files are logged and skipped (gamekit.data). Objectives load in objectives.py, next to
the functions that score them.

    TILES    {tile id: {"id", "name", "icon", "color", "moveCost", "resources", "searches",
                        "shelter", "reveals", "points", "count": {"small", "large"}, "text"}}
    FINDS    {find id: {"id", "name", "text", "gives": {item: n}, "energy", "count"}}
    CHECKS   {card id: {"id", "name", "text", "outcome", "count"}}
"""

import logging
from pathlib import Path

from gamekit.data import flag, load_json_dir, text, whole

log = logging.getLogger("marooned")

CONTENT = Path(__file__).resolve().parent.parent / "content"

# Things a player can carry. Resources come from tiles; relics only from finds.
ITEMS = ("wood", "fiber", "food", "water", "stone", "scrap", "herbs", "relic")
RESOURCES = ("wood", "fiber", "food", "water", "stone", "scrap", "herbs")
UNLIMITED = -1
OUTCOMES = ("solid", "shaky", "snapped")


def _item_counts(data, key, allowed, low):
    value = data.get(key, {})
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be an object")
    counts = {}
    for item, count in value.items():
        if item not in allowed:
            raise ValueError(f"{key}: unknown item {item!r}")
        if type(count) is not int or count < low or count > 99:
            raise ValueError(f"{key}.{item} must be a whole number from {low} to 99")
        if count:
            counts[item] = count
    return counts


def parse_tile(tile_id, data):
    count = data.get("count")
    if not isinstance(count, dict):
        raise ValueError("count must be an object with small and large")
    return {
        "id": tile_id,
        "name": text(data, "name", 30, required=True),
        "icon": text(data, "icon", 8),
        "color": text(data, "color", 20) or "#cccccc",
        "moveCost": whole(data, "moveCost", 1, 5, default=1),
        "resources": _item_counts(data, "resources", RESOURCES, UNLIMITED),
        "searches": whole(data, "searches", 0, 9, default=0),
        "shelter": whole(data, "shelter", 0, 9, default=0),
        "reveals": flag(data, "reveals"),
        "points": whole(data, "points", 0, 9, default=1),
        "count": {size: whole(count, size, 0, 99, default=0) for size in ("small", "large")},
        "text": text(data, "text", 200),
    }


def parse_find(find_id, data):
    return {
        "id": find_id,
        "name": text(data, "name", 30, required=True),
        "text": text(data, "text", 200),
        "gives": _item_counts(data, "gives", ITEMS, 0),
        "energy": whole(data, "energy", -5, 5, default=0),
        "count": whole(data, "count", 0, 99, default=1),
    }


def parse_check(card_id, data):
    outcome = data.get("outcome")
    if outcome not in OUTCOMES:
        raise ValueError(f"outcome must be one of {', '.join(OUTCOMES)}")
    return {
        "id": card_id,
        "name": text(data, "name", 30, required=True),
        "text": text(data, "text", 200),
        "outcome": outcome,
        "count": whole(data, "count", 0, 99, default=1),
    }


TILES = load_json_dir(CONTENT / "tiles", parse_tile, log)
FINDS = load_json_dir(CONTENT / "finds", parse_find, log)
CHECKS = load_json_dir(CONTENT / "checks", parse_check, log)


def card_list(definitions, count=lambda item: item["count"]):
    """[id, id, ...] with each id repeated as many times as its count (a deck's contents)."""
    return [item_id for item_id, item in definitions.items() for _ in range(count(item))]
