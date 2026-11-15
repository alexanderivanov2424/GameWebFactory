"""Hex Realms: workers, production, upkeep and growth (territory is territory.py; bought land's gold
upkeep is counted here).

    effect(m, pid, name)     sum of an advance effect key over pid's advances
    output(m, s)             what structure s makes in a turn when it works
    staffing(m, pid)         (working structures in job order, people without a job)
    report(m, pid, resolving=False)  this turn's forecast (resolving: claims are already land, not orders): {"income", "upkeep", "net" (income - upkeep, not
                             capped by your stores), "wasted" {good: n that won't fit in your stores
                             at the end of the turn and is lost}, "staffed": [sid], "workers" (in jobs), "builders" (on
                             construction sites), "idle" (neither), "housing", "soldiers" (people in
                             units, plus this turn's recruits while planning: they use housing too), "caps", "starve"
                             ({"units": n, "people": n} who will die of hunger this turn), "growth"
                             (people you will gain, 0 if none), "growthWhy" (why not), "tradeRate",
                             "land" (cells of bought land paid for, in upkeep gold; with this turn's
                             claims while planning), "flows" (see flows())}
    flows(m, pid, working, building, land=0, idle=0)  what each of pid's things adds or takes this turn, for the
                             client's resource view: [[id, res, n, on], ...], n > 0 made, n < 0 used, on = False
                             for a structure that isn't working this turn (what it would make / need); plus
                             "people" (where your population is: [id, "people", n, True, tag], tag "work" (jobs),
                             "build" (on a site, or a build order placed this turn: its order id), "unit" (in a unit), "train" (recruits ordered at a structure),
                             "idle" (at home: spread over the homes, oldest first, up to their housing)) and
                             "housing" (the cap: [id, "housing", n, True] per structure that houses people)
    split_upkeep(have, made, need)  (from the stores, from production): where a good's upkeep comes from
    starvation(m, pid, food, pop)   ([unit ids], people) who die when `food` (stores + this turn's
                             production) can't feed pid's units and `pop` people: units first
    end_of_turn(m, pid, events)  production and upkeep together (then the stores' cap), eating, wages, growth

Rules: every structure works, wherever it is, as long as it has its crew: people (population)
fill jobs, food producers first, then oldest first. Gold, faith and science go straight to the
realm; goods (food, wood, stone, metal) go into the realm's stores (logistics.py). Everyone eats: pop // 2 food, plus each unit's
upkeep, plus LAND_UPKEEP gold per cell of bought land (territory.py). Production and upkeep happen at the same time (upkeep can use this turn's production), and
only what is left is capped by the room in the stores; the rest is lost. Not enough food: everyone who can't eat dies, units first (newest first,
until the rest can be fed), then people (starvation()); gold below 0 gives up
that many cells of bought land (territory.give_up), or with no bought land, the newest paid unit deserts. If the realm makes more food this turn than it eats (whether or not it all fits in
the stores) and there is free housing (units use housing too: population + the people in your units
must fit), population grows by 1 (+1 per Granary). People without a
job build (construction.py). A realm without a Town Hall (settlers before their first city)
skips all of this.
"""

from gamekit.hexes import neighbors

from . import construction, logistics, territory
from .content import ADVANCES, CAPPED, RESOURCES, STRUCTURES, TOWN_HALL, UNITS

FOOD_FIRST = ("food",)


def effect(m, pid, name):
    return sum(ADVANCES[a]["effect"].get(name, 0) for a in m.players[pid]["advances"] if a in ADVANCES)


def output(m, s):
    d = STRUCTURES[s["type"]]
    out = dict(d["onTerrain"].get(m.cells[s["at"]], {})) if d["onTerrain"] else dict(d["produce"])
    for c in s["cells"]:
        for r, n in d["perCell"].get(m.cells[c], {}).items():
            out[r] = out.get(r, 0) + n
    around = {n for c in s["cells"] for n in neighbors(c) if n in m.cells} - set(s["cells"])
    for adj in d["perAdjacent"]:
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
    for adj in d["perAdjacent"]:
        keys |= set(adj["gain"])
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


def report(m, pid, resolving=False):
    """The forecast for this turn, as it will really resolve (see the module header)."""
    p = m.players[pid]
    working, left = staffing(m, pid)
    building = construction.forecast(m, pid, orders=not resolving)
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
    soldiers = sum(UNITS[u["type"]]["people"] for u in m.units.values() if u["owner"] == pid)
    if not resolving:  # recruits ordered this turn: their people already left the population
        soldiers += sum(r.get("people", 0) for r in m.orders[pid]["recruits"])
    upkeep = {r: 0 for r in RESOURCES}
    upkeep["food"] = p["pop"] // 2
    for u in m.units.values():
        if u["owner"] == pid:
            for r, n in UNITS[u["type"]]["upkeep"].items():
                upkeep[r] += n
    land = territory.bought(m, pid, pending=not resolving)
    upkeep["gold"] += land * territory.LAND_UPKEEP
    stores = logistics.stores(m, pid)
    caps = {r: sum(logistics.capacity(s).get(r, 0) for s in stores) for r in CAPPED}
    have, wasted = logistics.stock(m, pid), {}
    for r in CAPPED:  # as end_of_turn does it: upkeep first, then what's left of production must fit
        from_stock, from_income = split_upkeep(have[r], income[r], upkeep[r])
        over = (income[r] - from_income) - (logistics.room(m, pid, r) + from_stock)
        if over > 0:
            wasted[r] = over
    starve = {"units": 0, "people": 0}
    has_hall = any(s["owner"] == pid and s["type"] == TOWN_HALL for s in m.structures.values())
    if has_hall and have["food"] + income["food"] < upkeep["food"]:
        dead, people = starvation(m, pid, have["food"] + income["food"], p["pop"])
        starve = {"units": len(dead), "people": people}
    if income["food"] <= upkeep["food"]:
        growth, why = 0, "Make more food than your people eat to grow."
    elif p["pop"] + soldiers >= housing:
        growth, why = 0, "Housing is full (units use housing too): build homes to grow."
    else:
        growth, why = min(1 + bonus, housing - p["pop"] - soldiers), ""
    return {"income": income, "upkeep": upkeep, "net": {r: income[r] - upkeep[r] for r in RESOURCES},
            "wasted": wasted,
            "staffed": [s["id"] for s in working], "workers": p["pop"] - left, "builders": building["builders"],
            "idle": left - building["builders"], "housing": housing, "soldiers": soldiers, "caps": caps, "starve": starve, "growth": growth,
            "growthWhy": why, "tradeRate": min(rates) if rates else 0, "land": land,
            "flows": flows(m, pid, working, building, land, left - building["builders"])}


def flows(m, pid, working, building, land=0, idle=0):
    """Per structure / unit / site: production (+), unit upkeep, and the people's food and the bought
    land's gold (-, on the first Town Hall); "people" (where they are, tagged) and "housing" (the cap).
    See the module header."""
    p, on = m.players[pid], {s["id"] for s in working}
    home_bonus = effect(m, pid, "homeHousing")
    out = []
    own = sorted((s for s in m.structures.values() if s["owner"] == pid), key=lambda s: s["n"])
    for s in own:
        d = STRUCTURES[s["type"]]
        for r, n in output(m, s).items():
            out.append([s["id"], r, n, s["id"] in on])
        if d["jobs"] and s["id"] in on:
            out.append([s["id"], "people", d["jobs"], True, "work"])
        housing = d["housing"] + (home_bonus if d["home"] else 0)
        if housing:
            out.append([s["id"], "housing", housing, True])
    halls = [s for s in logistics.stores(m, pid) if s["type"] == TOWN_HALL]
    if halls and p["pop"] // 2:
        out.append([halls[0]["id"], "food", -(p["pop"] // 2), True])
    if halls and land:
        out.append([halls[0]["id"], "gold", -land * territory.LAND_UPKEEP, True])
    for cid in building["works"]:
        out.append([cid, "people", STRUCTURES[m.sites[cid]["type"]]["builders"], True, "build"])
    for b in m.orders[pid]["builds"]:
        if b["id"] in building["orders"]:
            out.append([b["id"], "people", STRUCTURES[b["type"]]["builders"], True, "build"])
    training = {}
    for r in m.orders[pid]["recruits"]:
        if r.get("people") and r["at"] in m.structures:
            training[r["at"]] = training.get(r["at"], 0) + r["people"]
    for sid, n in training.items():
        out.append([sid, "people", n, True, "train"])
    homes = [(s, h) for s, h in ((s, STRUCTURES[s["type"]]["housing"] + (home_bonus if STRUCTURES[s["type"]]["home"] else 0))
                                 for s in own) if h > 0]
    for i, (s, h) in enumerate(homes):  # idle people at home, the oldest homes first (the last takes any overflow)
        n = idle if i == len(homes) - 1 else min(idle, h)
        if n > 0:
            out.append([s["id"], "people", n, True, "idle"])
            idle -= n
    for u in sorted((u for u in m.units.values() if u["owner"] == pid), key=lambda u: u["n"]):
        for r, n in UNITS[u["type"]]["upkeep"].items():
            if n:
                out.append([u["id"], r, -n, True])
        if UNITS[u["type"]]["people"]:
            out.append([u["id"], "people", UNITS[u["type"]]["people"], True, "unit"])
    return out


def end_of_turn(m, pid, events):
    p = m.players[pid]
    if not any(s["owner"] == pid and s["type"] == TOWN_HALL for s in m.structures.values()):
        return  # settlers still looking for a home: nothing to store, eat or grow yet
    rep = report(m, pid, resolving=True)
    income, upkeep = rep["income"], rep["upkeep"]
    for r in RESOURCES:
        if r not in CAPPED:
            p["res"][r] += income[r]
    have = logistics.stock(m, pid)
    # Production and upkeep at once: upkeep comes out of the stores first, the rest out of this turn's
    # production, and only what's left of the production goes into the stores (capped: the rest is lost).
    for r in CAPPED:
        from_stock, from_income = split_upkeep(have[r], income[r], upkeep[r])
        logistics.take(m, pid, {r: from_stock})
        logistics.store(m, pid, r, income[r] - from_income)
    eat = upkeep["food"]
    have = have["food"] + income["food"]
    if have < eat:
        dead, people = starvation(m, pid, have, p["pop"])
        for uid in dead:
            u = m.units[uid]
            events.append({"t": "starved", "owner": pid, "unit": uid, "type": u["type"], "at": u["at"]})
            m.remove_unit(uid)
        if people:
            p["pop"] -= people
            events.append({"t": "starve", "owner": pid, "n": people})
    p["res"]["gold"] -= rep["upkeep"]["gold"]
    if p["res"]["gold"] < 0:
        short, p["res"]["gold"] = -p["res"]["gold"], 0
        lost = territory.give_up(m, pid, -(-short // territory.LAND_UPKEEP))
        if lost:
            events.append({"t": "landLost", "owner": pid, "n": lost})
        else:
            _disband_newest(m, pid, lambda u: UNITS[u["type"]]["upkeep"].get("gold", 0) > 0, events)
    if rep["growth"] and have >= eat:
        p["pop"] += rep["growth"]


def starvation(m, pid, food, pop):
    """([unit ids], people) who die of hunger: units that eat, newest first, until the food feeds the
    rest; then the people the food left can't feed (pop // 2 food feeds pop people)."""
    eaters = sorted((u for u in m.units.values() if u["owner"] == pid and UNITS[u["type"]]["upkeep"].get("food", 0) > 0),
                    key=lambda u: u["n"], reverse=True)
    units_eat = sum(UNITS[u["type"]]["upkeep"]["food"] for u in eaters)
    dead = []
    for u in eaters:
        if pop // 2 + units_eat <= food:
            break
        dead.append(u["id"])
        units_eat -= UNITS[u["type"]]["upkeep"]["food"]
    left = max(0, food - units_eat)
    return dead, pop - min(pop, 2 * left + 1)


def split_upkeep(have, made, need):
    """(from the stores, from this turn's production): where `need` upkeep of a good comes from."""
    from_stock = min(need, have)
    return from_stock, min(made, need - from_stock)


def _disband_newest(m, pid, which, events):
    units = sorted((u for u in m.units.values() if u["owner"] == pid and which(u)), key=lambda u: u["n"])
    if units:
        u = units[-1]
        events.append({"t": "desert", "owner": pid, "unit": u["id"], "type": u["type"], "at": u["at"]})
        m.remove_unit(u["id"])
