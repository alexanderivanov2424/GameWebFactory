"""Hex Realms: territory, road connections, workers, production, upkeep and growth.

    territory(m)             {key: pid}: each cell within a structure's claim radius belongs to
                             the owner of the nearest structure cell (a tie between players = no one)
    connected(m, pid)        set of pid's structure ids linked to one of their Town Halls by roads
                             (only these work): a Town Hall always is; roads chain from a road
                             touching a Town Hall; any other structure counts once one of its cells
                             touches a linked road (touching another structure isn't enough)
    effect(m, pid, name)     sum of an advance effect key over pid's advances
    report(m, pid)           this turn's forecast: {"income", "upkeep", "net", "staffed": [sid],
                             "workers", "idle", "housing", "caps", "growth", "tradeRate"}
    end_of_turn(m, pid, events)  applies the report: stock, caps, starvation, desertion, growth

Rules: people (population) work structures with jobs, food producers first, then oldest first;
a structure needs its full crew and a road connection to produce. Everyone eats: pop // 2 food,
plus each unit's upkeep. Food below 0 starves 1 person (or disbands a unit); gold below 0 makes
the newest paid unit desert. With food left over and free housing, population grows by 1 (+1 per
working Granary). Food, wood, stone and metal are capped by storage; gold, faith, science aren't.
"""

from gamekit.hexes import disk, dist, neighbors, parse

from .content import ADVANCES, CAPPED, RESOURCES, ROAD, STRUCTURES, TOWN_HALL, UNITS

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


def connected(m, pid):
    own = [s for s in m.structures.values() if s["owner"] == pid]
    roads = {c for s in own if s["type"] == ROAD for c in s["cells"]}
    halls = [s for s in own if s["type"] == TOWN_HALL]
    todo = [n for s in halls for c in s["cells"] for n in neighbors(c) if n in roads]
    linked_roads = set(todo)
    while todo:
        for n in neighbors(todo.pop()):
            if n in roads and n not in linked_roads:
                linked_roads.add(n)
                todo.append(n)
    return {s["id"] for s in own if s["type"] == TOWN_HALL or (s["cells"][0] in linked_roads if s["type"] == ROAD else
            any(n in linked_roads for c in s["cells"] for n in neighbors(c)))}


def effect(m, pid, name):
    return sum(ADVANCES[a]["effect"].get(name, 0) for a in m.players[pid]["advances"] if a in ADVANCES)


def output(m, s):
    """What structure s makes in a turn when it works."""
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
    return out


def makes_food(s):
    return output_keys(s["type"]) & set(FOOD_FIRST)


def output_keys(stype):
    d = STRUCTURES[stype]
    keys = set(d["produce"]) | {r for v in d["onTerrain"].values() for r in v} | {r for v in d["perCell"].values() for r in v}
    if d.get("perAdjacent"):
        keys |= set(d["perAdjacent"]["gain"])
    return keys


def report(m, pid):
    p = m.players[pid]
    linked = connected(m, pid)
    own = sorted((s for s in m.structures.values() if s["owner"] == pid), key=lambda s: (not makes_food(s), s["n"]))
    workers = left = p["pop"]
    income = {r: 0 for r in RESOURCES}
    staffed, caps, housing, growth, rates = [], {r: 0 for r in CAPPED}, 0, 0, []
    home_bonus = effect(m, pid, "homeHousing")
    for s in own:
        d = STRUCTURES[s["type"]]
        housing += d["housing"] + (home_bonus if d["home"] else 0)
        if s["id"] not in linked:
            continue
        if d["jobs"]:
            if not s["active"] or d["jobs"] > left:
                continue
            left -= d["jobs"]
        if s["type"] != ROAD:
            staffed.append(s["id"])
        for r, n in output(m, s).items():
            income[r] += n
        for r in CAPPED:
            caps[r] += d["storage"] + d["store"].get(r, 0)
        growth += d["growth"]
        if d["trade"]:
            rates.append(d["trade"])
    upkeep = {r: 0 for r in RESOURCES}
    upkeep["food"] = p["pop"] // 2
    for u in m.units.values():
        if u["owner"] == pid:
            for r, n in UNITS[u["type"]]["upkeep"].items():
                upkeep[r] += n
    net = {r: income[r] - upkeep[r] for r in RESOURCES}
    return {"income": income, "upkeep": upkeep, "net": net, "staffed": staffed, "workers": workers, "idle": left,
            "housing": housing, "caps": caps, "growth": 1 + growth, "tradeRate": min(rates) if rates else 0}


def end_of_turn(m, pid, events):
    p = m.players[pid]
    rep = report(m, pid)
    res = p["res"]
    for r in RESOURCES:
        res[r] += rep["net"][r]
    if res["food"] < 0:
        res["food"] = 0
        if p["pop"] > 0:
            p["pop"] -= 1
            events.append({"t": "starve", "owner": pid})
        else:
            _disband_newest(m, pid, lambda u: True, events)
    if res["gold"] < 0:
        res["gold"] = 0
        _disband_newest(m, pid, lambda u: UNITS[u["type"]]["upkeep"].get("gold", 0) > 0, events)
    for r in CAPPED:
        res[r] = min(res[r], rep["caps"][r])
    if rep["net"]["food"] > 0 and p["pop"] < rep["housing"]:
        grow = min(rep["growth"], rep["housing"] - p["pop"])
        p["pop"] += grow


def _disband_newest(m, pid, which, events):
    units = sorted((u for u in m.units.values() if u["owner"] == pid and which(u)), key=lambda u: u["n"])
    if units:
        u = units[-1]
        events.append({"t": "desert", "owner": pid, "unit": u["id"], "type": u["type"], "at": u["at"]})
        m.remove_unit(u["id"])
