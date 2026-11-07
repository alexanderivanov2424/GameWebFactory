"""Smugglers: content files (goods, ship tiles, Interpol cards) and contract generation.

Files live in content/ next to server.py; every field is described in content/README.md.
Bad files are logged and skipped (gamekit.data). Loaders take a folder so tests can feed
temporary files.

    GOODS          {id: {"id", "name", "legal", "value", "penalty", "count", "color", "text"}}
    SHIPS          {id: {"id", "name", "speed", "count"}}            ship tiles
    INTERPOL_CARDS {id: {"id", "name", "kind", "cost", "supply", "start", "effects", "text"}}
    goods_deck_ids(goods)            card ids for a fresh goods deck (count copies of each)
    legal_goods(goods)               ids of the legal goods, cheapest first
    make_contracts(board, goods, count, rng)
        [{"id": "c1", "from": planet, "to": planet, "good": legal id, "bonus": X}, ...]
"""

import logging

from gamekit.data import flag, load_json_dir, text, whole

from .board import CONTENT

log = logging.getLogger("smugglers")

PIECES = ("patrol", "barrier", "checkpoint")
KINDS = ("action", "funding")
MIN_CONTRACT_DISTANCE = 4  # steps between a contract's source and destination


def parse_good(good_id, data):
    legal = flag(data, "legal")
    return {
        "id": good_id,
        "name": text(data, "name", 30, required=True),
        "legal": legal,
        "value": whole(data, "value", 0, 50),
        "penalty": 0 if legal else whole(data, "penalty", 0, 50),
        "count": whole(data, "count", 0, 60),
        "color": text(data, "color", 7) or "#888888",
        "text": text(data, "text", 120),
    }


def parse_ship(ship_id, data):
    return {
        "id": ship_id,
        "name": text(data, "name", 30, required=True),
        "speed": whole(data, "speed", 1, 9),
        "count": whole(data, "count", 0, 20),
    }


def parse_interpol_card(card_id, data):
    kind = data.get("kind")
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {', '.join(KINDS)}")
    raw = data.get("effects")
    if not isinstance(raw, dict):
        raise ValueError("effects must be an object")
    effects = {}
    for key in ("cards", "actions", "budget"):
        if key in raw:
            effects[key] = whole(raw, key, 0, 9)
    if "piece" in raw:
        if raw["piece"] not in PIECES:
            raise ValueError(f"effects.piece must be one of {', '.join(PIECES)}")
        effects["piece"] = raw["piece"]
        if raw["piece"] == "patrol":
            effects["move"] = whole(raw, "move", 0, 9)
    if flag(raw, "repeat"):
        effects["repeat"] = True
    if not effects:
        raise ValueError("effects must do something")
    if kind == "funding" and set(effects) - {"budget", "cards"}:
        raise ValueError("funding cards only give budget (and cards)")
    return {
        "id": card_id,
        "name": text(data, "name", 30, required=True),
        "kind": kind,
        "cost": whole(data, "cost", 0, 20),
        "supply": whole(data, "supply", 0, 40),
        "start": whole(data, "start", 0, 10, default=0),
        "effects": effects,
        "text": text(data, "text", 200),
    }


def load_goods(folder=CONTENT / "goods"):
    return load_json_dir(folder, parse_good, log)


def load_ships(folder=CONTENT / "ships"):
    return load_json_dir(folder, parse_ship, log)


def load_interpol_cards(folder=CONTENT / "interpol"):
    return load_json_dir(folder, parse_interpol_card, log)


GOODS = load_goods()
SHIPS = load_ships()
INTERPOL_CARDS = load_interpol_cards()


def goods_deck_ids(goods):
    return [gid for gid, good in goods.items() for _ in range(good["count"])]


def ship_tile_ids(ships):
    return [sid for sid, ship in ships.items() for _ in range(ship["count"])]


def legal_goods(goods):
    return sorted((gid for gid, g in goods.items() if g["legal"]), key=lambda g: (goods[g]["value"], g))


def make_contracts(board, goods, count, rng):
    """`count` random contracts between planets at least MIN_CONTRACT_DISTANCE steps apart.
    The bonus grows with the distance (1 per 3 steps, at least 1)."""
    planets = sorted(board.planets)
    pairs = []
    for a in planets:
        for b in planets:
            if a != b:
                steps = board.distance(a, b)
                if steps is not None and steps >= MIN_CONTRACT_DISTANCE:
                    pairs.append((a, b, steps))
    legal = legal_goods(goods)
    contracts = []
    for n in range(1, count + 1):
        source, destination, steps = rng.choice(pairs)
        contracts.append({
            "id": f"c{n}",
            "from": source,
            "to": destination,
            "good": rng.choice(legal),
            "bonus": max(1, steps // 3),
        })
    return contracts
