"""Hex Realms: dice combat. Every die is a d6.

    battle(m, a, b, a_attacks, b_attacks, events)  two units fight; both stop for the turn
    shoot(m, uid, cell, events)                    ranged unit shoots an enemy unit or structure on cell
    siege(m, uid, sid, events)                     unit hits a structure; the structure rolls back
    towers(m, events)                              each tower shoots the nearest enemy in range

A die hits on HIT (4+), or COVER_HIT (5+) against a unit in cover (forest, hills, mountains, or on
its owner's structure). Battles run up to ROUNDS rounds; each hit takes 1 hp, 0 hp dies.
Dice: attack value when attacking, defense value when standing (+1 holding, +defendDice in own
territory, +vsMounted against knights, +attackDice when attacking).
Each fight appends an event to `events`; the client's panels.js and replay.js read them.
"""

from gamekit.hexes import dist

from .content import STRUCTURES, TERRAIN, UNITS
from .economy import effect

HIT = 4
COVER_HIT = 5
ROUNDS = 3


def roll(m, n):
    return [m.rng.randint(1, 6) for _ in range(max(0, n))]


def need(m, u):
    """The roll needed to hit unit u."""
    sid = m.cell_structure.get(u["at"])
    own = sid is not None and m.structures[sid]["owner"] == u["owner"]
    return COVER_HIT if own or TERRAIN[m.cells[u["at"]]]["cover"] else HIT


def dice(m, u, attacking, foe=None):
    d = UNITS[u["type"]]
    if attacking:
        n = d["attack"] + (effect(m, u["owner"], "attackDice") if d["attack"] else 0)
    else:
        n = d["defense"] + (1 if u["id"] in m.orders[u["owner"]]["holds"] else 0)
        if m.territory.get(u["at"]) == u["owner"]:
            n += effect(m, u["owner"], "defendDice")
    if foe is not None and UNITS[foe["type"]]["mounted"]:
        n += d["vsMounted"]
    return n


def side(m, u):
    """hp before the fight; need = the roll that hits it (for the client's dice)."""
    return {"unit": u["id"], "type": u["type"], "owner": u["owner"], "at": u["at"], "hp": u["hp"], "need": need(m, u)}


def battle(m, a, b, a_attacks, b_attacks, events):
    ua, ub = m.units[a], m.units[b]
    ev = {"t": "battle", "a": side(m, ua), "b": side(m, ub), "rounds": [], "dead": []}
    da, db = dice(m, ua, a_attacks, ub), dice(m, ub, b_attacks, ua)
    for _ in range(ROUNDS):
        if da <= 0 and db <= 0:
            break
        ra, rb = roll(m, da), roll(m, db)
        ub["hp"] -= sum(1 for x in ra if x >= need(m, ub))
        ua["hp"] -= sum(1 for x in rb if x >= need(m, ua))
        ev["rounds"].append([ra, rb])
        if ua["hp"] <= 0 or ub["hp"] <= 0:
            break
    m.fought.update((a, b))
    for u in (ua, ub):
        if u["hp"] <= 0:
            ev["dead"].append(u["id"])
            m.remove_unit(u["id"])
    ev["hp"] = [max(0, ua["hp"]), max(0, ub["hp"])]
    events.append(ev)


def damage_structure(m, sid, amount, by, events):
    s = m.structures[sid]
    s["hp"] -= amount
    if s["hp"] <= 0:
        events.append({"t": "destroyed", "type": s["type"], "owner": s["owner"], "by": by, "at": s["at"], "cells": s["cells"]})
        m.remove_structure(sid)


def shoot(m, uid, cell, events):
    u = m.units[uid]
    d = UNITS[u["type"]]
    target = m.unit_at.get(cell)
    sid = m.cell_structure.get(cell)
    m.fought.add(uid)
    if target is not None and m.units[target]["owner"] != u["owner"]:
        t = m.units[target]
        r = roll(m, dice(m, u, True))
        hits = sum(1 for x in r if x >= need(m, t))
        t["hp"] -= hits
        ev = {"t": "shot", "a": side(m, u), "b": side(m, t), "roll": r, "hits": hits, "dead": []}
        m.fought.add(target)
        if t["hp"] <= 0:
            ev["dead"].append(target)
            m.remove_unit(target)
        events.append(ev)
    elif sid is not None and m.structures[sid]["owner"] != u["owner"] and STRUCTURES[m.structures[sid]["type"]]["hp"]:
        r = roll(m, dice(m, u, True))
        hits = sum(1 for x in r if x >= HIT)
        events.append({"t": "shot", "a": side(m, u), "structure": sid, "stype": m.structures[sid]["type"], "owner": m.structures[sid]["owner"], "at": cell,
                       "roll": r, "hits": hits, "damage": hits * d["siege"]})
        damage_structure(m, sid, hits * d["siege"], u["owner"], events)


def siege(m, uid, sid, events):
    u = m.units[uid]
    s = m.structures[sid]
    sd = STRUCTURES[s["type"]]
    r = roll(m, dice(m, u, True))
    back = roll(m, sd["defense"])
    hits = sum(1 for x in r if x >= HIT)
    taken = sum(1 for x in back if x >= HIT)
    ev = {"t": "siege", "a": side(m, u), "structure": sid, "stype": s["type"], "owner": s["owner"], "at": s["at"],
          "roll": r, "back": back, "damage": hits * UNITS[u["type"]]["siege"], "dead": []}
    m.fought.add(uid)
    u["hp"] -= taken
    if u["hp"] <= 0:
        ev["dead"].append(uid)
        m.remove_unit(uid)
    events.append(ev)
    damage_structure(m, sid, ev["damage"], u["owner"], events)


def towers(m, events):
    for sid in sorted(m.structures, key=lambda x: m.structures[x]["n"]):
        s = m.structures.get(sid)
        if s is None:
            continue
        sd = STRUCTURES[s["type"]]
        if not sd["shoots"]:
            continue
        foes = [u for u in m.units.values() if u["owner"] != s["owner"] and dist(u["at"], s["at"]) <= sd["range"]]
        if not foes:
            continue
        t = min(foes, key=lambda u: (dist(u["at"], s["at"]), u["hp"], u["n"]))
        r = roll(m, sd["shoots"] + effect(m, s["owner"], "towerDice"))
        hits = sum(1 for x in r if x >= need(m, t))
        t["hp"] -= hits
        ev = {"t": "tower", "structure": sid, "owner": s["owner"], "at": s["at"], "b": side(m, t), "roll": r, "hits": hits, "dead": []}
        m.fought.add(t["id"])
        if t["hp"] <= 0:
            ev["dead"].append(t["id"])
            m.remove_unit(t["id"])
        events.append(ev)
