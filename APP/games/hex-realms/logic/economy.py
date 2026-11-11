"""Hex Realms: territory, workers, production, upkeep and growth.

    territory(m)             the new {key: pid}: a player reaches the cells within a structure's
                             claim radius (or CLAIM_RADIUS of a claimed cell, m.claims). Land is
                             first come, first served: a cell stays its owner's while they still
                             reach it; a free cell goes to the one player reaching it, and to no
                             one while two or more do (they got there at the same time). Called
                             by Match.refresh, so land changes hands only as structures and claims
                             appear or vanish (at resolution).
    effect(m, pid, name)     sum of an advance effect key over pid's advances
    output(m, s)             what structure s makes in a turn when it works
    staffing(m, pid)         (working structures in job order, people without a job)
    report(m, pid)           this turn's forecast: {"income", "upkeep", "net" (what you will really
                             gain: goods only up to the room in your stores), "wasted" {good: n that
                             won't fit}, "staffed": [sid], "workers" (in jobs), "builders" (on
                             construction sites), "idle" (neither), "housing", "caps", "growth"
                             (people you will gain, 0 if none), "growthWhy" (why not), "tradeRate"}
    end_of_turn(m, pid, events)  production, eating, wages, growth

Rules: every structure works, wherever it is, as long as it has its crew: people (population)
fill jobs, food producers first, then oldest first. Gold, faith and science go straight to the
realm; goods (food, wood, stone, metal) go straight into the realm's stores (logistics.py), and what doesn't fit is lost. Everyone eats: pop // 2 food, plus each unit's
upkeep. Not enough food starves 1 person (or disbands a unit); gold below 0 makes the newest paid
unit desert. If the realm makes more food this turn than it eats (whether or not it all fits in
the stores) and there is free housing, population grows by 1 (+1 per Granary). People without a
job build (construction.py). A realm without a Town Hall (settlers before their first city)
skips all of this.
"""

from gamekit.hexes import disk, dist, neighbors, parse

from . import construction, logistics
from .content import ADVANCES, CAPPED, RESOURCES, STRUCTURES, TOWN_HALL, UNITS

FOOD_FIRST = ("food",)
CLAIM_RADIUS = 1  # a claimed cell (orders.claim) holds itself and its neighbours, like a 1-radius structure


def territory(m):
    """The new {key: pid} map from m.territory (see the module header): first come, first served."""
    reach = {}
    sources = [(c, STRUCTURES[s["type"]]["territory"], s["owner"]) for s in m.structures.values() for c in s["cells"]]
    sources += [(c, CLAIM_RADIUS, owner) for c, owner in m.claims.items()]
    for c, radius, owner in sources:
        for k in disk(radius, parse(c)):
            if k in m.cells:
                reach.setdefault(k, set()).add(owner)
    out = {}
    for k, owners in reach.items():
        cur = m.territory.get(k)
        if cur in owners:
            out[k] = cur
        elif len(owners) == 1:
            out[k] = next(iter(owners))
    return out


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
    """The forecast for this turn, as it will really resolve (see the module header)."""
    p = m.players[pid]
    working, left = staffing(m, pid)
    building = construction.forecast(m, pid)
    income = {r: 0 for r in RESOURCES}
    bonus, rates, housing = 0, [], 0
    home_bonus = effect(m, pid, "homeHousing")
    for s in m.structures.values():
        if s["owner"] == pid:
            d = STRUCTURES[s["type"]]
            housing += d["housing"] + (home_bonus if d["home"] else 0)
            bonus += d["growth"]
    for s in working:
        for r, n in output(m, s).items():
            income[r] += n
        if STRUCTURES[s["type"]]["trade"]:
            rates.append(STRUCTURES[s["type"]]["trade"])
    upkeep = {r: 0 for r in RESOURCES}
    upkeep["food"] = p["pop"] // 2
    for u in m.units.values():
        if u["owner"] == pid:
            for r, n in UNITS[u["type"]]["upkeep"].items():
                upkeep[r] += n
    stores = logistics.stores(m, pid)
    caps = {r: sum(logistics.capacity(s).get(r, 0) for s in stores) for r in CAPPED}
    kept = {r: min(n, logistics.room(m, pid, r)) if r in CAPPED else n for r, n in income.items()}
    if income["food"] <= upkeep["food"]:
        growth, why = 0, "Make more food than your people eat to grow."
    elif p["pop"] >= housing:
        growth, why = 0, "Housing is full: build homes to grow."
    else:
        growth, why = min(1 + bonus, housing - p["pop"]), ""
    return {"income": income, "upkeep": upkeep, "net": {r: kept[r] - upkeep[r] for r in RESOURCES},
            "wasted": {r: income[r] - kept[r] for r in CAPPED if income[r] > kept[r]},
            "staffed": [s["id"] for s in working], "workers": p["pop"] - left, "builders": building["builders"],
            "idle": left - building["builders"], "housing": housing, "caps": caps, "growth": growth,
            "growthWhy": why, "tradeRate": min(rates) if rates else 0}


def end_of_turn(m, pid, events):
    p = m.players[pid]
    if not any(s["owner"] == pid and s["type"] == TOWN_HALL for s in m.structures.values()):
        return  # settlers still looking for a home: nothing to store, eat or grow yet
    rep = report(m, pid)
    working, _ = staffing(m, pid)
    for s in working:
        for r, n in output(m, s).items():
            if r in CAPPED:
                logistics.store(m, pid, r, n)
            else:
                p["res"][r] += n
    eat = rep["upkeep"]["food"]
    have = logistics.stock(m, pid)["food"]
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
    if rep["growth"] and have >= eat:
        p["pop"] += rep["growth"]


def _disband_newest(m, pid, which, events):
    units = sorted((u for u in m.units.values() if u["owner"] == pid and which(u)), key=lambda u: u["n"])
    if units:
        u = units[-1]
        events.append({"t": "desert", "owner": pid, "unit": u["id"], "type": u["type"], "at": u["at"]})
        m.remove_unit(u["id"])
