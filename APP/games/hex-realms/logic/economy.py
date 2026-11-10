"""Hex Realms: territory, workers, production, upkeep and growth.

    territory(m)             {key: pid}: each cell within a structure's claim radius belongs to
                             the owner of the nearest structure cell (a tie between players = no one)
    effect(m, pid, name)     sum of an advance effect key over pid's advances
    output(m, s)             what structure s makes in a turn when it works
    report(m, pid)           this turn's forecast: {"income", "upkeep", "net", "staffed": [sid],
                             "stranded": [sid], "workers", "idle", "housing", "caps", "unusable",
                             "held", "growth", "tradeRate"}
    end_of_turn(m, pid, events)  production, deliveries, eating, wages, growth

Rules: every structure works, wherever it is, as long as it has its crew: people (population)
fill jobs, food producers first, then oldest first. Gold, faith and science go straight to the
realm. Goods (food, wood, stone, metal) go into the producer's own stock if it is a store (the
Town Hall), else into its held buffer (one turn's output at most), and from there along road
networks to stores (logistics.py). Only goods in usable stores (linked to a Town Hall) can be
spent or eaten. "stranded" lists working road producers with no store on their networks.
Everyone eats: pop // 2 food, plus each unit's upkeep. Not enough food starves 1 person (or
disbands a unit); gold below 0 makes the newest paid unit desert. If more food reached usable
stores this turn than was eaten and there is free housing, population grows by 1 (+1 per
Granary).
"""

from gamekit.hexes import disk, dist, neighbors, parse

from . import logistics
from .content import ADVANCES, CAPPED, RESOURCES, STRUCTURES, UNITS

FOOD_FIRST = ("food",)


def territory(m):
    best = {}
    for s in m.structures.values():
        radius = STRUCTURES[s["type"]]["territory"]
        for c in s["cells"]:
            for k in disk(radius, parse(c)):
                if k not in m.cells:
                    continue
                d = dist(k, c)
                cur = best.get(k)
                if cur is None or d < cur[0]:
                    best[k] = (d, s["owner"])
                elif d == cur[0] and cur[1] != s["owner"]:
                    best[k] = (d, None)
    return {k: p for k, (d, p) in best.items() if p}


def effect(m, pid, name):
    return sum(ADVANCES[a]["effect"].get(name, 0) for a in m.players[pid]["advances"] if a in ADVANCES)


def output(m, s):
    d = STRUCTURES[s["type"]]
    out = dict(d["onTerrain"].get(m.cells[s["at"]], {})) if d["onTerrain"] else dict(d["produce"])
    for c in s["cells"]:
        for r, n in d["perCell"].get(m.cells[c], {}).items():
            out[r] = out.get(r, 0) + n
    adj = d.get("perAdjacent")
    if adj:
        around = {n for c in s["cells"] for n in neighbors(c) if n in m.cells} - set(s["cells"])
        if adj["terrain"]:
            count = sum(1 for n in around if m.cells[n] == adj["terrain"])
        else:
            sids = {m.cell_structure[n] for n in around if n in m.cell_structure}
            others = [m.structures[x] for x in sids if m.structures[x]["owner"] == s["owner"]]
            count = sum(1 for o in others if (o["type"] == adj["type"] if adj["type"] else STRUCTURES[o["type"]]["home"]))
        for r, n in adj["gain"].items():
            out[r] = out.get(r, 0) + n * min(count, adj["max"])
    if s["type"] == "farm":
        out["food"] = out.get("food", 0) + effect(m, s["owner"], "farmFood")
    if s["type"] == "chapel":
        out["gold"] = out.get("gold", 0) + effect(m, s["owner"], "chapelGold")
    return {r: n for r, n in out.items() if n}


def output_keys(stype):
    d = STRUCTURES[stype]
    keys = set(d["produce"]) | {r for v in d["onTerrain"].values() for r in v} | {r for v in d["perCell"].values() for r in v}
    if d.get("perAdjacent"):
        keys |= set(d["perAdjacent"]["gain"])
    return keys


def staffing(m, pid):
    """(working structures in job order, idle people)."""
    own = sorted((s for s in m.structures.values() if s["owner"] == pid),
                 key=lambda s: (not output_keys(s["type"]) & set(FOOD_FIRST), s["n"]))
    left, working = m.players[pid]["pop"], []
    for s in own:
        jobs = STRUCTURES[s["type"]]["jobs"]
        if jobs:
            if not s["active"] or jobs > left:
                continue
            left -= jobs
        working.append(s)
    return working, left


def report(m, pid):
    p = m.players[pid]
    nets = logistics.networks(m, pid)
    stores = logistics.usable(m, pid, nets)
    store_nets = set().union(*(nets[s["id"]] for s in m.structures.values() if s["owner"] == pid and logistics.capacity(s)))
    working, left = staffing(m, pid)
    income = {r: 0 for r in RESOURCES}
    stranded, growth, rates, housing = [], 0, [], 0
    home_bonus = effect(m, pid, "homeHousing")
    for s in m.structures.values():
        if s["owner"] == pid:
            d = STRUCTURES[s["type"]]
            housing += d["housing"] + (home_bonus if d["home"] else 0)
            growth += d["growth"]
    for s in working:
        d = STRUCTURES[s["type"]]
        out = output(m, s)
        for r, n in out.items():
            income[r] += n
        if d["road"] and set(out) & set(CAPPED) and not nets[s["id"]] & store_nets:
            stranded.append(s["id"])
        if d["trade"]:
            rates.append(d["trade"])
    upkeep = {r: 0 for r in RESOURCES}
    upkeep["food"] = p["pop"] // 2
    for u in m.units.values():
        if u["owner"] == pid:
            for r, n in UNITS[u["type"]]["upkeep"].items():
                upkeep[r] += n
    caps = {r: sum(logistics.capacity(s).get(r, 0) for s in stores) for r in CAPPED}
    usable_ids = {s["id"] for s in stores}
    unusable, held = {r: 0 for r in CAPPED}, {r: 0 for r in CAPPED}
    for s in m.structures.values():
        if s["owner"] != pid:
            continue
        for r, n in s["held"].items():
            held[r] += n
        if s["id"] not in usable_ids:
            for r, n in s["stock"].items():
                unusable[r] += n
    return {"income": income, "upkeep": upkeep, "net": {r: income[r] - upkeep[r] for r in RESOURCES},
            "staffed": [s["id"] for s in working], "stranded": stranded, "workers": p["pop"], "idle": left,
            "housing": housing, "caps": caps, "unusable": unusable, "held": held, "growth": 1 + growth,
            "tradeRate": min(rates) if rates else 0}


def end_of_turn(m, pid, events):
    p = m.players[pid]
    rep = report(m, pid)
    nets = logistics.networks(m, pid)
    stores = logistics.usable(m, pid, nets)
    usable_ids = {s["id"] for s in stores}
    food_in = 0
    working, _ = staffing(m, pid)
    for s in working:
        d = STRUCTURES[s["type"]]
        for r, n in output(m, s).items():
            if r not in CAPPED:
                p["res"][r] += n
            elif logistics.capacity(s):
                left = logistics.fill(s, r, n)
                if s["id"] in usable_ids and r == "food":
                    food_in += n - left
            elif d["road"]:
                s["held"][r] = n  # a full buffer stays full: one turn's output at most
    food_in += logistics.deliver(m, pid, nets)["food"]
    eat = rep["upkeep"]["food"]
    have = logistics.stock(m, pid, stores)["food"]
    logistics.take(m, pid, {"food": min(eat, have)})
    if have < eat:
        if p["pop"] > 0:
            p["pop"] -= 1
            events.append({"t": "starve", "owner": pid})
        else:
            _disband_newest(m, pid, lambda u: True, events)
    p["res"]["gold"] -= rep["upkeep"]["gold"]
    if p["res"]["gold"] < 0:
        p["res"]["gold"] = 0
        _disband_newest(m, pid, lambda u: UNITS[u["type"]]["upkeep"].get("gold", 0) > 0, events)
    if food_in > eat and p["pop"] < rep["housing"]:
        p["pop"] += min(rep["growth"], rep["housing"] - p["pop"])


def _disband_newest(m, pid, which, events):
    units = sorted((u for u in m.units.values() if u["owner"] == pid and which(u)), key=lambda u: u["n"])
    if units:
        u = units[-1]
        events.append({"t": "desert", "owner": pid, "unit": u["id"], "type": u["type"], "at": u["at"]})
        m.remove_unit(u["id"])
