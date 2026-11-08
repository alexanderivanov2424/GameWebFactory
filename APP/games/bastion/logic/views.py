"""Bastion: what clients see (Match.public / Match.private), and where each hand card may go.

    public(match)     everything public: the catalog (static: "kinds" (structure files),
                      "cards", resources, icons, terrain; cached on the match), round, keep,
                      stockpile, soldiers, board ("structures", roads, walls, blights), foes (face-down ones show only their arrival round), market, seats, log
    private(match, pid)   {"hand", "targets"} (None for someone not seated)
    targets           {card uid: ...} for every playable hand card:
                      blueprint: {"<rotation>": {"x,y": output}} for each legal top-left cell
                                 (output: what the building would make there; -1 if it isn't worked)
                      targeted action: {"<structure uid>": "preview text"}
Blueprint targets depend only on the board, so they're cached by (board.version, structure).
"""

from gamekit import LobbyError

from . import economy
from .cards import CARDS, public as card_public
from .structures import OUTPUT_NAMES, RESOURCES, STRUCTURES, TERRAIN, public as structure_public

OUTPUT_ICONS = {"soldiers": "🗡️", "keep": "🏰", "cure": "⚕️"}


def catalog(match):
    if not hasattr(match, "_catalog"):
        board = match.board
        match._catalog = {
            "kinds": {sid: structure_public(s, STRUCTURES) for sid, s in STRUCTURES.items()},
            "cards": {cid: card_public(c) for cid, c in CARDS.items()},
            "resources": [list(r) for r in RESOURCES],
            "outputNames": OUTPUT_NAMES,
            "icons": {**{r[0]: r[2] for r in RESOURCES}, **OUTPUT_ICONS},
            "terrain": ["".join(next(k for k, v in TERRAIN.items() if v == t) for t in row) for row in board.terrain],
            "terrainNames": TERRAIN,
            "width": board.width,
            "height": board.height,
            "storeCap": economy.STORE_CAP,
            "colors": dict(match.colors),
            "names": dict(match.names),
        }
    return match._catalog


def structure_view(match, s, reach):
    board = match.board
    view = {"kind": s.kind, "cells": [[x, y] for x, y in s.cells], "owner": s.owner or "",
            "ruined": sorted([x, y] for x, y in s.ruined), "plague": s.plague is not None,
            "frozen": s.frozen == match.round, "worked": s.worked, "store": dict(s.store),
            "link": board.link(s, reach) or "none",
            "protected": sum(1 for c in s.cells if board.protected(c))}
    if s.spec["work"]:
        view["output"], view["parts"] = economy.output(board, s.kind, s.cells)
    return view


def public(match):
    from .match import OVERTIME
    board = match.board
    reach = board.road_reach()
    last = match.last_arrival()
    return {
        **catalog(match),
        "round": match.round,
        "step": match.step,
        "keep": match.keep,
        "keepMax": match.keep_max,
        "stock": dict(match.stock),
        "soldiers": match.soldiers,
        "deadline": last + OVERTIME if match.foes else 0,
        "structures": {str(uid): structure_view(match, s, reach) for uid, s in board.structures.items()},
        **board.public(),
        "foes": {str(f.index): f.public() for f in match.foes},
        "market": list(match.market.slots),
        "seats": {pid: seat.public() for pid, seat in match.seats.items()},
        "log": {str(i): entry for i, entry in enumerate(match.log)},
        "logCount": len(match.log),
    }


def build_targets(match, kind):
    cache = match.__dict__.setdefault("_build_cache", {})
    key = (match.board.version, kind)
    if key not in cache:
        if len(cache) > 40:
            cache.clear()
        board, spec, found = match.board, STRUCTURES[kind], {}
        for rotation in range(4):
            spots = {}
            for y in range(board.height):
                for x in range(board.width):
                    try:
                        cells = board.check(kind, rotation, x, y)
                    except LobbyError:
                        continue
                    spots[f"{x},{y}"] = economy.output(board, kind, cells)[0] if spec["work"] else -1
            found[str(rotation)] = spots
        cache[key] = found
    return cache[key]


def action_targets(match, card):
    board, found = match.board, {}
    plagued = match.plagued()
    for uid, s in board.structures.items():
        if card["work"]:
            if card["work"] != "any" and s.kind not in card["work"]:
                continue
            if economy.why_not(board, s, match.stock, match.round, plagued):
                continue
            key = next(iter(s.spec["work"]["makes"]))
            amount = economy.output(board, s.kind, s.cells)[0] + card["boost"]
            stored = key in economy.GOODS and board.link(s) != "depot"
            found[str(uid)] = f"+{amount} {OUTPUT_NAMES[key]}" + (" (stored)" if stored else "")
        elif card["repair"] and s.ruined:
            found[str(uid)] = f"repair for {len(s.ruined)} wood"
        elif card["cure"] and s.plague is not None:
            found[str(uid)] = "cure"
    return found


def private(match, pid):
    seat = match.seats.get(pid)
    if seat is None:
        return None
    targets = {}
    for instance in seat.hand:
        card = CARDS[instance["card"]]
        if card["kind"] == "build":
            targets[str(instance["uid"])] = build_targets(match, card["structure"])
        elif card["kind"] == "action" and (card["work"] or card["repair"] or card["cure"]):
            targets[str(instance["uid"])] = action_targets(match, card)
    return {"hand": seat.private()["hand"], "targets": targets}
