"""Bastion: what clients see (Match.public / Match.private), and where each hand card may go.

    public(match)     everything public: the catalog (static, cached on the match: "kinds"
                      (structure files), "cards", resources, icons, terrain, rule numbers),
                      round, phase, turn order, population and food, units and placements,
                      keep, stockpile, soldiers, tile stocks, hauls, the board ("structures",
                      roads, walls, blights), foes (face-down ones show only their arrival
                      round), market and rerollCost, tiles (where a road or wall tile may go
                      and which can be removed: tiles.targets), seats, log
    private(match, pid)   {"hand", "targets", "places", "sources"} (None for someone not seated)
    targets           {card uid: ...} for every playable hand card:
                      blueprint: {"<rotation>": {"x,y": output}} for each legal top-left cell
                                 (output: what the building would make there; -1 if it isn't worked)
                      repair/cure action: {"<structure uid>": "preview text"}
    places            {target: {"text", "tool", "why"}} (units.preview): in the place phase every
                      target a unit may go on now; in the act phase every target holding one
                      of your units
    sources           {"<structure uid>": "3 wood, 1 stone"} buildings a haul may take from now
Blueprint targets depend only on the board, so they're cached by (board.version, structure).
"""

from gamekit import LobbyError

from . import economy, food, hauling, tiles, units
from .cards import CARDS, amount_text, public as card_public
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
            "toolBoost": economy.TOOL_BOOST,
            "feeds": dict(food.FEEDS),
            "haulSizes": {"small": hauling.SMALL, "big": hauling.BIG},
            "tileBatch": tiles.BATCH,
            "colors": dict(match.colors),
            "names": dict(match.names),
        }
    return match._catalog


def structure_view(match, s, reach):
    board = match.board
    view = {"kind": s.kind, "cells": [[x, y] for x, y in s.cells],
            "ruined": sorted([x, y] for x, y in s.ruined), "plague": s.plague is not None,
            "frozen": s.frozen == match.round, "worked": s.worked, "store": dict(s.store),
            "link": board.link(s, reach) or "none",
            "protected": sum(1 for c in s.cells if board.protected(c))}
    if s.spec["work"]:
        view["output"], view["parts"] = economy.output(board, s.kind, s.cells)
    return view


def placements(match):
    """{target: pid} for one-unit targets, {target: {pid: n}} for pools (haul, fight)."""
    found = {}
    for target, by in match.placed.items():
        if target.startswith(units.POOLS):
            found[target] = dict(by)
        else:
            found[target] = next(iter(by))
    return found


def public(match):
    from .match import OVERTIME
    board = match.board
    reach = board.road_reach()
    last = match.last_arrival()
    haul_units = sum(match.placed.get("haul", {}).values())
    return {
        **catalog(match),
        "round": match.round,
        "step": match.step,
        "phase": match.phase,
        "firstPlayer": match.order[0] if match.order else "",
        "turn": match.turn() or "",
        "order": list(match.order),
        "population": match.population(),
        "hungry": match.hungry,
        "eaten": dict(match.eaten),
        "upkeep": food.feed(match.population(), match.stock),
        "units": {pid: {"total": seat.units, "free": units.free(match, pid),
                        "placed": sum(units.mine(match, pid).values())} for pid, seat in match.seats.items()},
        "placements": placements(match),
        "ready": {pid: seat.ready for pid, seat in match.seats.items()},
        "keep": match.keep,
        "keepMax": match.keep_max,
        "stock": dict(match.stock),
        "soldiers": match.soldiers,
        "roadStock": match.tile_stock["road"],
        "wallStock": match.tile_stock["wall"],
        "carriages": hauling.carriages(board),
        "hauls": {"next": hauling.capacity(board, match.hauled), "done": match.hauled,
                  "bigLeft": max(0, hauling.carriages(board) - match.hauled),
                  "queue": hauling.queue(board, match.hauled, haul_units)},
        "deadline": last + OVERTIME if match.foes else 0,
        "structures": {str(uid): structure_view(match, s, reach) for uid, s in board.structures.items()},
        **board.public(),
        "foes": {str(f.index): f.public() for f in match.foes},
        "market": list(match.market.slots),
        "rerollCost": match.reroll_cost(),
        "tiles": tiles.targets(match),
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
    found = {}
    for uid, s in match.board.structures.items():
        if card["repair"] and s.ruined:
            found[str(uid)] = f"repair for {len(s.ruined)} wood"
        elif card["cure"] and s.plague is not None:
            found[str(uid)] = "cure"
    return found


def places(match, pid):
    if match.phase == "place":
        wanted = units.targets(match)
    else:
        wanted = list(units.mine(match, pid))
    found = {}
    for target in wanted:
        try:
            found[target] = units.preview(match, target)
        except LobbyError:  # the target is gone
            continue
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
        elif card["kind"] == "action" and (card["repair"] or card["cure"]):
            targets[str(instance["uid"])] = action_targets(match, card)
    return {"hand": seat.private()["hand"], "targets": targets, "places": places(match, pid),
            "sources": {str(uid): amount_text(s.store) for uid, s in hauling.sources(match.board).items()}}
