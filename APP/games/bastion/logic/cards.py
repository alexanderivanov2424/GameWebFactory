"""Bastion: loading the card files (content/cards/*.json) and the starting deck when the game is imported.

Every card either builds a structure on the map or is an order (played for an effect). Fields are
documented in content/README.md. Bad files are logged (logger "bastion") and skipped.

    CARDS            {id: card}, card = {
                         "id", "name", "icon", "text",
                         "kind":     a structure kind (KINDS) or "order"
                         "place":    "road" | "ground" | None (orders; "structure" for targeted orders)
                         "labor":    labor to play it (0-5)
                         "cost":     gold to buy it at the market (0 = never offered)
                         "unlock":   first market that may offer it (after level N, 1-10)
                         "maxLevel": highest level (play the same card on it again to upgrade)
                         "shot":     projectile style the client draws for towers
                         "stats":    {name: number | [number per level] | bool} }
    stat(card, name, level=1, default=0)   a stat at a level (lists are per level)
    STARTING_DECK    [card id, ...]  from content/starting-deck.json ({"cards": {id: copies}})
    public(card)     what clients get (everything above but the id)
"""

import logging
from pathlib import Path

from gamekit.data import load_json, load_json_dir, text, whole

log = logging.getLogger("bastion")

CONTENT = Path(__file__).resolve().parent.parent / "content"
CARDS_DIR = CONTENT / "cards"

# Structure kinds -> where they go and which stats they read (anything else in "stats" is refused).
KINDS = {
    "tower": ("ground", {"damage", "range", "cooldown", "air", "ground", "pierce", "splash", "minRange", "area"}),
    "wall": ("road", {"hp"}),
    "spikes": ("road", {"damage"}),
    "tar": ("road", {"slow"}),
    "barracks": ("ground", {"hp", "damage", "cooldown", "respawn"}),
    "farm": ("ground", {"gold"}),
    "forge": ("ground", {"bonus"}),
    "watch": ("ground", {"bonus"}),
    "quarry": ("ground", {"labor"}),
    "chapel": ("ground", {"keep", "repair"}),
}
# Order effects, applied in this order by orders.py.
ORDER_STATS = {"labor", "draw", "gold", "keep", "repair", "teamLabor", "teamGold", "teamDraw", "upgrade"}
SHOTS = ("arrow", "bolt", "rock", "oil", "none")
MAX_LEVEL = 3


def stat(card, name, level=1, default=0):
    value = card["stats"].get(name, default)
    if isinstance(value, list):
        return value[min(level, len(value)) - 1]
    return value


def _stats(data, allowed, max_level):
    stats = data.get("stats", {})
    if not isinstance(stats, dict):
        raise ValueError("stats must be an object")
    clean = {}
    for name, value in stats.items():
        if name not in allowed:
            raise ValueError(f"unknown stat {name!r} (allowed: {', '.join(sorted(allowed))})")
        if isinstance(value, bool):
            clean[name] = value
        elif isinstance(value, (int, float)) and 0 <= value <= 1000:
            clean[name] = value
        elif (isinstance(value, list) and len(value) == max_level
              and all(isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v <= 1000 for v in value)):
            clean[name] = list(value)
        else:
            raise ValueError(f"stat {name} must be true/false, a number, or a list of {max_level} numbers")
    return clean


def parse_card(card_id, data):
    kind = data.get("kind")
    if kind == "order":
        place, allowed = None, ORDER_STATS
    elif kind in KINDS:
        place, allowed = KINDS[kind]
    else:
        raise ValueError(f"kind must be 'order' or one of {', '.join(KINDS)}")
    max_level = whole(data, "maxLevel", 1, MAX_LEVEL, default=1 if kind == "order" else MAX_LEVEL)
    stats = _stats(data, allowed, max_level)
    if kind == "order" and stats.get("upgrade"):
        place = "structure"
    shot = data.get("shot", "arrow" if kind == "tower" else "none")
    if shot not in SHOTS:
        raise ValueError(f"shot must be one of {', '.join(SHOTS)}")
    return {
        "id": card_id,
        "name": text(data, "name", 30, required=True),
        "icon": text(data, "icon", 8, required=True),
        "text": text(data, "text", 240),
        "kind": kind,
        "place": place,
        "labor": whole(data, "labor", 0, 5),
        "cost": whole(data, "cost", 0, 30),
        "unlock": whole(data, "unlock", 1, 10, default=1),
        "maxLevel": max_level,
        "shot": shot,
        "stats": stats,
    }


def public(card):
    return {key: value for key, value in card.items() if key != "id"}


def parse_deck(data, cards):
    counts = data.get("cards")
    if not isinstance(counts, dict) or not counts:
        raise ValueError("starting deck needs a non-empty 'cards' object")
    deck = []
    for card_id, copies in counts.items():
        if card_id not in cards:
            raise ValueError(f"unknown card {card_id!r}")
        if type(copies) is not int or not 1 <= copies <= 10:
            raise ValueError(f"copies of {card_id} must be 1-10")
        deck += [card_id] * copies
    return deck


CARDS = load_json_dir(CARDS_DIR, parse_card, log)
STARTING_DECK = load_json(CONTENT / "starting-deck.json", lambda d: parse_deck(d, CARDS), log,
                          default=[c for c in CARDS if CARDS[c]["cost"]][:8])
