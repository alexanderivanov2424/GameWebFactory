"""Hex Realms: the orders a player gives while planning a turn (validated, nothing resolves yet).

Costs are paid when an order is given (goods from the Town Halls and the stores linked to them) and refunded when it's cancelled or fails at resolution,
so a player can never order more than they have. Orders are private until the turn resolves.

    build(m, pid, stype, at, rot)   structure footprint anchored at `at`, `rot` 60-degree turns
    recruit(m, pid, sid, utype)     train a unit at a working structure (1 per structure per turn)
    move(m, pid, uid, to)           move along the cheapest path; ending on an enemy = attack;
                                    `to` = the unit's own cell clears its orders
    shoot(m, pid, uid, at)          ranged unit: shoot a cell instead of moving
    hold(m, pid, uid)               toggle: stay put and defend with 1 more die
    found(m, pid, uid, rot)         settlers found a Town Hall where they stand (instead of moving)
    research(m, pid, aid)           buy an advance (takes effect at the start of resolution)
    cancel(m, pid, oid)             undo a build / recruit / research order (refund)
    trade(m, pid, give, get)        market: give `rate` of one resource for 1 of another, at once
    toggle(m, pid, sid)             switch a structure with jobs off/on (frees its workers)
    disband(m, pid, uid)            remove one of your units at once (its people come home)
"""

from gamekit import LobbyError
from gamekit.hexes import dist, neighbors

from .content import ADVANCES, STRUCTURES, TERRAIN, TOWN_HALL, UNITS, footprint
from . import logistics
from .economy import report
from .movement import path

CITY_SPACING = 5
TRADE_GOODS = ["gold", "food", "wood", "stone", "metal"]


def pay(m, pid, cost):
    """From the Town Halls and the stores linked to them (logistics.py), plus realm gold/faith/science."""
    logistics.take(m, pid, cost)


def refund(m, pid, cost):
    logistics.give(m, pid, cost)


def own_unit(m, pid, uid):
    u = m.units.get(uid)
    if u is None or u["owner"] != pid:
        raise LobbyError("That's not your unit.")
    return u


def own_structure(m, pid, sid):
    s = m.structures.get(sid)
    if s is None or s["owner"] != pid:
        raise LobbyError("That's not your structure.")
    return s


def clear_unit(m, pid, uid):
    o = m.orders[pid]
    o["moves"].pop(uid, None)
    o["shots"].pop(uid, None)
    o["found"].pop(uid, None)
    if uid in o["holds"]:
        o["holds"].remove(uid)


def site_problem(m, pid, stype, cells, pending=()):
    """Why `cells` can't hold a `stype` for pid right now (None if they can)."""
    d = STRUCTURES[stype]
    for c in cells:
        if c not in m.cells:
            return "That doesn't fit on the map."
        if m.cells[c] not in d["terrain"]:
            return f"{d['name']} can't be built on {TERRAIN[m.cells[c]]['name'].lower()}."
        if c in m.cell_structure or c in pending:
            return "Something is already built there."
        occ = m.unit_at.get(c)
        if occ is not None and m.units[occ]["owner"] != pid:
            return "An enemy unit stands there."
    if d["coast"] and not any(m.cells.get(n) == "water" for c in cells for n in neighbors(c)):
        return f"{d['name']} must touch water."
    return None


def build(m, pid, stype, at, rot):
    d = STRUCTURES.get(stype)
    if d is None or stype == TOWN_HALL:
        raise LobbyError("You can't build that.")
    if d["requires"] and d["requires"] not in m.players[pid]["advances"]:
        raise LobbyError(f"Research {ADVANCES[d['requires']]['name']} first.")
    if at not in m.cells:
        raise LobbyError("That doesn't fit on the map.")
    cells = footprint(stype, at, rot)
    o = m.orders[pid]
    pending = {c for b in o["builds"] for c in b["cells"]}
    problem = site_problem(m, pid, stype, cells, pending)
    if problem:
        raise LobbyError(problem)
    if any(m.territory.get(c) != pid for c in cells):
        raise LobbyError("Build inside your territory.")
    mine = {c for c, sid in m.cell_structure.items() if m.structures[sid]["owner"] == pid} | pending
    if not any(n in mine for c in cells for n in neighbors(c)):
        raise LobbyError("It must touch one of your structures or roads.")
    pay(m, pid, d["cost"])
    o["builds"].append({"id": m.new_id("o"), "type": stype, "at": at, "rot": rot % 6, "cells": cells, "cost": dict(d["cost"])})


def recruit_problem(m, pid, s, utype):
    sd, ud = STRUCTURES[s["type"]], UNITS.get(utype)
    if ud is None or utype not in sd["recruits"]:
        return f"{sd['name']} can't train that."
    if ud["requires"] and ud["requires"] not in m.players[pid]["advances"]:
        return f"Research {ADVANCES[ud['requires']]['name']} first."
    if ud["needs"] and not any(x["owner"] == pid and x["type"] == ud["needs"] for x in m.structures.values()):
        return f"{ud['name']} needs a {STRUCTURES[ud['needs']]['name']}."
    if any(r["at"] == s["id"] for r in m.orders[pid]["recruits"]):
        return "One unit per structure per turn."
    return None


def recruit(m, pid, sid, utype):
    s = own_structure(m, pid, sid)
    problem = recruit_problem(m, pid, s, utype)
    if problem:
        raise LobbyError(problem)
    ud = UNITS[utype]
    p = m.players[pid]
    if p["pop"] < ud["people"]:
        raise LobbyError(f"{ud['name']} needs {ud['people']} people.")
    pay(m, pid, ud["cost"])
    p["pop"] -= ud["people"]
    m.orders[pid]["recruits"].append({"id": m.new_id("o"), "type": utype, "at": sid, "cost": dict(ud["cost"]),
                                      "people": ud["people"]})


def move(m, pid, uid, to):
    u = own_unit(m, pid, uid)
    if to == u["at"]:
        clear_unit(m, pid, uid)
        return
    p = path(m, uid, to)
    if p is None:
        raise LobbyError("It can't get there this turn.")
    clear_unit(m, pid, uid)
    m.orders[pid]["moves"][uid] = p


def shoot(m, pid, uid, at):
    u = own_unit(m, pid, uid)
    rng = UNITS[u["type"]]["range"]
    if not rng:
        raise LobbyError("Only ranged units shoot.")
    if at not in m.cells or dist(u["at"], at) > rng:
        raise LobbyError(f"Out of range ({rng}).")
    occ, sid = m.unit_at.get(at), m.cell_structure.get(at)
    enemy_unit = occ is not None and m.units[occ]["owner"] != pid
    enemy_building = sid is not None and m.structures[sid]["owner"] != pid and STRUCTURES[m.structures[sid]["type"]]["hp"]
    if not (enemy_unit or enemy_building):
        raise LobbyError("Shoot at an enemy unit or structure.")
    clear_unit(m, pid, uid)
    m.orders[pid]["shots"][uid] = at


def hold(m, pid, uid):
    own_unit(m, pid, uid)
    holding = uid in m.orders[pid]["holds"]
    clear_unit(m, pid, uid)
    if not holding:
        m.orders[pid]["holds"].append(uid)


def found_problem(m, pid, u, rot):
    cells = footprint(TOWN_HALL, u["at"], rot)
    problem = site_problem(m, pid, TOWN_HALL, cells)
    if problem:
        return problem
    if any(c in m.unit_at and m.unit_at[c] != u["id"] for c in cells):
        return "Move your other units off the site first."
    halls = [c for c, sid in m.cell_structure.items() if m.structures[sid]["type"] == TOWN_HALL]
    if any(dist(c, h) < CITY_SPACING for c in cells for h in halls):
        return f"Too close to a Town Hall (keep {CITY_SPACING} cells away)."
    return None


def found(m, pid, uid, rot):
    u = own_unit(m, pid, uid)
    if not UNITS[u["type"]]["settler"]:
        raise LobbyError("Only settlers found cities.")
    problem = found_problem(m, pid, u, rot)
    if problem:
        raise LobbyError(problem)
    clear_unit(m, pid, uid)
    m.orders[pid]["found"][uid] = rot % 6


def research(m, pid, aid):
    a = ADVANCES.get(aid)
    p = m.players[pid]
    pending = [r["advance"] for r in m.orders[pid]["research"]]
    if a is None:
        raise LobbyError("Unknown advance.")
    if aid in p["advances"] or aid in pending:
        raise LobbyError("Already researched.")
    missing = [ADVANCES[x]["name"] for x in a["after"] if x not in p["advances"]]
    if missing:
        raise LobbyError(f"Research {', '.join(missing)} first.")
    pay(m, pid, a["cost"])
    m.orders[pid]["research"].append({"id": m.new_id("o"), "advance": aid, "cost": dict(a["cost"])})


def cancel(m, pid, oid):
    o = m.orders[pid]
    for kind in ("builds", "recruits", "research"):
        for x in o[kind]:
            if x["id"] == oid:
                o[kind].remove(x)
                refund(m, pid, x["cost"])
                m.players[pid]["pop"] += x.get("people", 0)
                return
    raise LobbyError("No such order.")


def trade(m, pid, give, get):
    if give not in TRADE_GOODS or get not in TRADE_GOODS or give == get:
        raise LobbyError("Trade gold, food, wood, stone or metal for another one.")
    rate = report(m, pid)["tradeRate"]
    if not rate:
        raise LobbyError("You need a working Market or Trading Hall.")
    if get in logistics.GOODS and not logistics.room(m, pid, get):
        raise LobbyError(f"No room left for {get} in your stores.")
    pay(m, pid, {give: rate})
    refund(m, pid, {get: 1})


def toggle(m, pid, sid):
    s = own_structure(m, pid, sid)
    if not STRUCTURES[s["type"]]["jobs"]:
        raise LobbyError("That structure has no workers to send home.")
    s["active"] = not s["active"]


def disband(m, pid, uid):
    u = own_unit(m, pid, uid)
    clear_unit(m, pid, uid)
    m.players[pid]["pop"] += UNITS[u["type"]]["people"]
    m.remove_unit(uid)

