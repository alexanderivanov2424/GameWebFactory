"""Hex Realms: production, upkeep, trade, eating and new people.

A structure works if its crew is there: people fill jobs, food producers first, then oldest first.
Gold, faith and science go to the realm; goods go into the stores (logistics.py). Everyone eats
FOOD_PER_PERSON food, units eat their upkeep, bought land costs LAND_UPKEEP gold per cell, and each
working trade structure with a trade set gives `trade` of one resource for 1 of another (only when
affordable). Production and upkeep happen together; only what is left is capped by store room.
Gold below 0 gives up bought land, or else the newest paid unit deserts. No Town Hall: none of this.

Food: this turn's production is eaten first, then the stores; only when both run out do the ones who
can't be fed die (units first). Population grows only from a production surplus: as many new people
as it feeds, while housing has room.

    output(m, s)                      what structure s makes when it works
    housing(m, s)                     the housing structure s gives (with advance bonuses)
    staffing(m, pid)                  (working structures in job order, idle people)
    report(m, pid, resolving=False)   the turn's forecast (see report())
    end_of_turn(m, pid, events)       apply the report: goods, gold, hunger, new people
"""

from gamekit.hexes import neighbors

from . import construction, logistics, territory
from .content import ADVANCES, CAPPED, RESOURCES, STRUCTURES, UNITS

FOOD_PER_PERSON = 1
TRADE_GOODS = ["gold", "food", "wood", "stone", "metal"]


# --- Advances ---------------------------------------------------------------------------------

def _advances(m, pid):
    return [ADVANCES[a] for a in m.players[pid]["advances"] if a in ADVANCES]


def effect(m, pid, name):
    """Sum of a dice effect (towerDice, attackDice, defendDice) over pid's advances."""
    return sum(a["effect"].get(name, 0) for a in _advances(m, pid))


def type_bonus(m, pid):
    """{structure type: {res: n}} that pid's advances add to its output."""
    out = {}
    for a in _advances(m, pid):
        for stype, gain in a["bonus"].items():
            _add(out.setdefault(stype, {}), gain)
    return out


def housing_bonus(m, pid):
    """{tag: n}: extra housing per own structure with that tag."""
    out = {}
    for a in _advances(m, pid):
        _add(out, a["housing"])
    return out


def _add(into, amounts, sign=1):
    for r, n in amounts.items():
        into[r] = into.get(r, 0) + sign * n
    return into


# --- Structures -------------------------------------------------------------------------------

def output(m, s):
    d = STRUCTURES[s["type"]]
    out = dict(d["onTerrain"].get(m.cells[s["at"]], {})) if d["onTerrain"] else dict(d["produce"])
    for c in s["cells"]:
        _add(out, d["perCell"].get(m.cells[c], {}))
    around = {n for c in s["cells"] for n in neighbors(c) if n in m.cells} - set(s["cells"])
    near = [STRUCTURES[m.structures[sid]["type"]] for sid in {m.cell_structure[n] for n in around if n in m.cell_structure}
            if m.structures[sid]["owner"] == s["owner"]]
    for adj in d["perAdjacent"]:
        if adj["terrain"]:
            count = sum(1 for n in around if m.cells[n] == adj["terrain"])
        else:
            count = sum(1 for o in near if (o["id"] == adj["type"] if adj["type"] else adj["tag"] in o["tags"]))
        _add(out, {r: n * min(count, adj["max"]) for r, n in adj["gain"].items()})
    _add(out, type_bonus(m, s["owner"]).get(s["type"], {}))
    return {r: n for r, n in out.items() if n > 0}  # penalties never make it negative


def housing(m, s, bonus=None):
    d = STRUCTURES[s["type"]]
    bonus = housing_bonus(m, s["owner"]) if bonus is None else bonus
    return d["housing"] + sum(n for tag, n in bonus.items() if tag in d["tags"])


def makes_food(stype):
    d = STRUCTURES[stype]
    return any("food" in gains for gains in [d["produce"], *d["onTerrain"].values(), *d["perCell"].values()]) or \
        any("food" in adj["gain"] and adj["gain"]["food"] > 0 for adj in d["perAdjacent"])


def staffing(m, pid):
    """(working structures in job order, idle people): food producers first, then oldest."""
    own = sorted(m.structures_of(pid), key=lambda s: (not makes_food(s["type"]), s["n"]))
    left, working = m.players[pid]["pop"], []
    for s in own:
        jobs = STRUCTURES[s["type"]]["jobs"]
        if jobs:
            if not s["active"] or jobs > left:
                continue
            left -= jobs
        working.append(s)
    return working, left


# --- The turn's forecast -----------------------------------------------------------------------

def report(m, pid, resolving=False):
    """This turn's forecast, as it will resolve (resolving: this turn's orders have already happened).

    income / upkeep / net {res: n}, wasted {good: n} (won't fit in the stores), staffed [sid],
    workers / builders / idle (people), housing, soldiers (people in units and recruits), caps,
    starve {"units", "people"}, born, popNet, foodNet (the stored food's change), land (bought cells),
    trades [[sid, give, rate, get]] (the trades that happen), flows (see flows())."""
    p = m.players[pid]
    working, left = staffing(m, pid)
    building = construction.forecast(m, pid, orders=not resolving)
    recruits = [] if resolving else m.orders[pid]["recruits"]
    hbonus = housing_bonus(m, pid)
    room = sum(housing(m, s, hbonus) for s in m.structures_of(pid))
    soldiers = sum(UNITS[u["type"]]["people"] for u in m.units_of(pid)) + sum(r["people"] for r in recruits)
    land = territory.bought(m, pid)

    income = dict.fromkeys(RESOURCES, 0)
    for s in working:
        _add(income, output(m, s))
    upkeep = dict.fromkeys(RESOURCES, 0)
    upkeep["food"] = p["pop"] * FOOD_PER_PERSON
    upkeep["gold"] = land * territory.LAND_UPKEEP
    for utype in [u["type"] for u in m.units_of(pid)] + [r["type"] for r in recruits]:
        _add(upkeep, UNITS[utype]["upkeep"])
    have = logistics.stock(m, pid)
    trades = _trades(working, have, income, upkeep)

    food = _food(m, pid, income["food"], upkeep["food"], have["food"], room - p["pop"] - soldiers) if m.has_hall(pid) \
        else {"starve": {"units": 0, "people": 0}, "born": 0, "foodNet": income["food"], "popNet": 0}
    net = {r: income[r] - upkeep[r] for r in RESOURCES}
    net["food"] = food["foodNet"]
    idle = left - building["builders"]
    return {"income": income, "upkeep": upkeep, "net": net, "wasted": _wasted(m, pid, have, income, upkeep, food["foodNet"]),
            "staffed": [s["id"] for s in working], "workers": p["pop"] - left, "builders": building["builders"],
            "idle": idle, "housing": room, "soldiers": soldiers,
            "caps": {r: sum(logistics.capacity(s).get(r, 0) for s in logistics.stores(m, pid)) for r in CAPPED},
            **food, "land": land, "trades": trades,
            "flows": flows(m, pid, working, building, trades, hbonus, idle, p["pop"] + soldiers)}


def _trades(working, have, income, upkeep):
    """Each working trade structure's trade, oldest first, if what's left after upkeep pays for it."""
    out = []
    for s in sorted(working, key=lambda s: s["n"]):
        rate, t = STRUCTURES[s["type"]]["trade"], s.get("trade")
        if rate and t and have[t["give"]] + income[t["give"]] - upkeep[t["give"]] >= rate:
            upkeep[t["give"]] += rate
            income[t["get"]] += 1
            out.append([s["id"], t["give"], rate, t["get"]])
    return out


def _food(m, pid, made, eat, stored, room):
    """Who eats, starves or is born: production first, then the stores; only a surplus makes people."""
    starve, born, food_net, pop_net = {"units": 0, "people": 0}, 0, made - eat, 0
    if made >= eat:
        born = max(0, min(room, (made - eat) // FOOD_PER_PERSON))
        food_net, pop_net = made - eat - born * FOOD_PER_PERSON, born
    elif made + stored < eat:
        dead, people = starvation(m, pid, made + stored, m.players[pid]["pop"])
        starve = {"units": len(dead), "people": people}
        eaten = eat - people * FOOD_PER_PERSON - sum(UNITS[m.units[u]["type"]]["upkeep"].get("food", 0) for u in dead)
        food_net = max(-stored, made - eaten)
        pop_net = -people - sum(UNITS[m.units[u]["type"]]["people"] for u in dead)
    return {"starve": starve, "born": born, "foodNet": food_net, "popNet": pop_net}


def _wasted(m, pid, have, income, upkeep, food_net):
    """{good: n} of this turn's production that won't fit in the stores (as end_of_turn does it)."""
    wasted = {}
    for r in CAPPED:
        if r == "food":
            over = food_net - logistics.room(m, pid, r)
        else:
            from_stock, from_income = split_upkeep(have[r], income[r], upkeep[r])
            over = (income[r] - from_income) - (logistics.room(m, pid, r) + from_stock)
        if over > 0:
            wasted[r] = over
    return wasted


def flows(m, pid, working, building, trades, hbonus, idle, living):
    """Each thing's resource flows as [id, res, n, on, tag?] rows (n > 0 made, n < 0 used), for the
    client's resource view. Tags: "build" (people building), "of" (population x of housing y), "trade"."""
    on = {s["id"] for s in working}
    own = m.structures_of(pid)
    out = []
    for s in own:
        jobs = STRUCTURES[s["type"]]["jobs"]
        out += [[s["id"], r, n, s["id"] in on] for r, n in output(m, s).items()]
        if jobs and s["id"] in on:
            out += [[s["id"], "people", -jobs, True], [s["id"], "food", -jobs * FOOD_PER_PERSON, True]]
        if housing(m, s, hbonus):
            out.append([s["id"], "housing", housing(m, s, hbonus), True])
    for sid, give, rate, get in trades:
        out += [[sid, give, -rate, True, "trade"], [sid, get, 1, True, "trade"]]
    out += [[f"land:{k}", "gold", -territory.LAND_UPKEEP, True] for k in sorted(k for k, p in m.claims.items() if p == pid)]
    for cid, n in [*building["works"].items(), *building["orders"].items()]:
        out += [[cid, "people", -n, True, "build"], [cid, "food", -n * FOOD_PER_PERSON, True]]
    for r in m.orders[pid]["recruits"]:
        if r["at"] in m.structures:
            out += [[r["at"], res, -n, True] for res, n in {"people": r["people"], **UNITS[r["type"]]["upkeep"]}.items() if n]
    homes = [(s, housing(m, s, hbonus)) for s in own if housing(m, s, hbonus) > 0]
    for i, (s, h) in enumerate(homes):  # idle people rest at home, oldest homes first; the last takes any overflow
        n = idle if i == len(homes) - 1 else min(idle, h)
        if n > 0:
            out += [[s["id"], "people", n, True], [s["id"], "food", -n * FOOD_PER_PERSON, True]]
            idle -= n
    for i, (s, h) in enumerate(homes):
        n = living if i == len(homes) - 1 else min(living, h)
        out.append([s["id"], "population", n, True, "of", h])
        living -= n
    for u in m.units_of(pid):
        out += [[u["id"], r, -n, True] for r, n in UNITS[u["type"]]["upkeep"].items() if n]
        if UNITS[u["type"]]["people"]:
            out.append([u["id"], "people", -UNITS[u["type"]]["people"], True])
    return out


# --- Resolution ---------------------------------------------------------------------------------

def end_of_turn(m, pid, events):
    if not m.has_hall(pid):
        return
    p = m.players[pid]
    rep = report(m, pid, resolving=True)
    income, upkeep = rep["income"], rep["upkeep"]
    for r in RESOURCES:
        if r not in CAPPED:
            p["res"][r] += income[r] - upkeep[r]
    have = logistics.stock(m, pid)
    if rep["foodNet"] < 0:
        logistics.take(m, pid, {"food": -rep["foodNet"]})
    else:
        logistics.store(m, pid, "food", rep["foodNet"])
    for r in CAPPED:
        if r != "food":
            from_stock, from_income = split_upkeep(have[r], income[r], upkeep[r])
            logistics.take(m, pid, {r: from_stock})
            logistics.store(m, pid, r, income[r] - from_income)
    if income["food"] + have["food"] < upkeep["food"]:
        dead, people = starvation(m, pid, income["food"] + have["food"], p["pop"])
        for uid in dead:
            u = m.units[uid]
            events.append({"t": "starved", "owner": pid, "unit": uid, "type": u["type"], "at": u["at"]})
            m.remove_unit(uid)
        if people:
            p["pop"] -= people
            events.append({"t": "starve", "owner": pid, "n": people})
    if p["res"]["gold"] < 0:
        short, p["res"]["gold"] = -p["res"]["gold"], 0
        lost = territory.give_up(m, pid, -(-short // territory.LAND_UPKEEP))
        if lost:
            events.append({"t": "landLost", "owner": pid, "n": lost})
        else:
            _desert(m, pid, events)
    p["pop"] += rep["born"]


def starvation(m, pid, food, pop):
    """([unit ids], people) who die of hunger: units that eat, newest first, until the food feeds the
    rest; then the people the food left can't feed."""
    eaters = [u for u in reversed(m.units_of(pid)) if UNITS[u["type"]]["upkeep"].get("food", 0) > 0]
    units_eat = sum(UNITS[u["type"]]["upkeep"]["food"] for u in eaters)
    dead = []
    for u in eaters:
        if pop * FOOD_PER_PERSON + units_eat <= food:
            break
        dead.append(u["id"])
        units_eat -= UNITS[u["type"]]["upkeep"]["food"]
    left = max(0, food - units_eat)
    return dead, pop - min(pop, left // FOOD_PER_PERSON)


def split_upkeep(have, made, need):
    """(from the stores, from this turn's production): stores first."""
    from_stock = min(need, have)
    return from_stock, min(made, need - from_stock)


def _desert(m, pid, events):
    paid = [u for u in m.units_of(pid) if UNITS[u["type"]]["upkeep"].get("gold", 0) > 0]
    if paid:
        u = paid[-1]
        events.append({"t": "desert", "owner": pid, "unit": u["id"], "type": u["type"], "at": u["at"]})
        m.remove_unit(u["id"])
