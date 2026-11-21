"""Hex Realms: production, upkeep, trade, eating and new people.

A structure works if its crew is there: people fill jobs, food producers first, then oldest first.
Gold goes to the realm; wood, stone and metal go into the stores (logistics.py). Faith and science are
flat: what working structures give right now, minus what advances spent (flat(), logistics.stock). Everyone eats
FOOD_PER_PERSON food, units eat their upkeep, bought land costs LAND_UPKEEP gold per cell, and each
working trade structure with a trade set gives `trade` of one resource for 1 of another (only when
affordable). Production and upkeep happen together; only what is left is capped by store room.
Gold below 0 gives up bought land, or else the newest paid unit deserts. No Town Hall: none of this.

Food is never stored: each turn's production feeds everyone. A surplus becomes new people (as many as
it feeds, while housing has room) and the rest is lost. A shortfall starves: idle people first, then
units that eat (newest first), then people at work (jobs and building).

    output(m, s, on=None)             what structure s makes when it works (on: ids of working structures,
                                      for boosts from its neighbours; default: staffing now)
    jobs(m, s)                        workers s needs (0 while a freeNear structure touches its terrain)
    housing(m, s)                     the housing structure s gives (with advance bonuses)
    staffing(m, pid)                  (working structures in job order, idle people)
    flat(m, pid)                      {faith, science, swords} that pid's working structures give now
    report(m, pid, resolving=False)   the turn's forecast (see report())
    end_of_turn(m, pid, events)       apply the report: goods, gold, hunger, new people
    starvation(m, pid, short, idle)   ([unit ids], people) who die when food production is `short`
"""

from gamekit.hexes import neighbors

from . import construction, logistics, territory
from .content import ADVANCES, CAPPED, FLAT, GLOBAL, HELD, RESOURCES, STRUCTURES, UNITS

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

def jobs(m, s):
    d = STRUCTURES[s["type"]]
    if d["jobs"] and d["freeNear"] and any(m.cells.get(n) == d["freeNear"] for c in s["cells"] for n in neighbors(c)):
        return 0
    return d["jobs"]


def output(m, s, on=None):
    d = STRUCTURES[s["type"]]
    out = dict(d["onTerrain"].get(m.cells[s["at"]], {})) if d["onTerrain"] else dict(d["produce"])
    for c in s["cells"]:
        _add(out, d["perCell"].get(m.cells[c], {}))
    around = {n for c in s["cells"] for n in neighbors(c) if n in m.cells} - set(s["cells"])
    near = [STRUCTURES[m.structures[sid]["type"]] for sid in {m.cell_structure[n] for n in around if n in m.cell_structure}
            if m.structures[sid]["owner"] == s["owner"]]
    for adj in d["perAdjacent"]:
        if adj["terrain"]:
            count = sum(1 for n in around if m.cells[n] == adj["terrain"] and n not in m.cell_structure and n not in m.cell_site)
        elif adj["unique"]:
            count = len({o["id"] for o in near})
        else:
            count = sum(1 for o in near if (o["id"] == adj["type"] if adj["type"] else adj["tag"] in o["tags"]))
        times = (1 if count >= adj["needs"] else 0) if adj["needs"] else min(count, adj["max"])
        _add(out, {r: n * times for r, n in adj["gain"].items()})
    _add(out, type_bonus(m, s["owner"]).get(s["type"], {}))
    out = {r: n for r, n in out.items() if n > 0}  # penalties never make it negative
    boosters = [m.structures[sid] for sid in {m.cell_structure[n] for n in around if n in m.cell_structure}]
    boosters = [b for b in boosters if b["owner"] == s["owner"] and STRUCTURES[b["type"]]["boost"]]
    if out and boosters:
        on = {x["id"] for x in staffing(m, s["owner"])[0]} if on is None else on
        add = sum(b["add"] for o in boosters if o["id"] in on for b in STRUCTURES[o["type"]]["boost"]
                  if (b["type"] == s["type"] if b["type"] else b["tag"] in d["tags"]))
        out = {r: n + add for r, n in out.items()}
    return out


def housing(m, s, bonus=None):
    d = STRUCTURES[s["type"]]
    bonus = housing_bonus(m, s["owner"]) if bonus is None else bonus
    return d["housing"] + sum(n for tag, n in bonus.items() if tag in d["tags"])


def makes_food(stype):
    d = STRUCTURES[stype]
    return any("food" in gains for gains in [d["produce"], *d["onTerrain"].values(), *d["perCell"].values()]) or \
        any("food" in adj["gain"] and adj["gain"]["food"] > 0 for adj in d["perAdjacent"]) or \
        any(makes_food(b["type"]) if b["type"] else b["tag"] == "food" for b in d["boost"])  # boosts food makers


def staffing(m, pid):
    """(working structures in job order, idle people): food producers first, then oldest."""
    own = sorted(m.structures_of(pid), key=lambda s: (not makes_food(s["type"]), s["n"]))
    left, working = m.players[pid]["pop"], []
    for s in own:
        n = jobs(m, s)
        if n:
            if not s["active"] or n > left:
                continue
            left -= n
        working.append(s)
    return working, left


def flat(m, pid):
    out = dict.fromkeys(FLAT + HELD, 0)
    working = staffing(m, pid)[0]
    on = {s["id"] for s in working}
    for s in working:
        for r, n in output(m, s, on).items():
            if r in out:
                out[r] += n
    return out


# --- The turn's forecast -----------------------------------------------------------------------

def report(m, pid, resolving=False):
    """This turn's forecast, as it will resolve (resolving: this turn's orders have already happened).

    income / upkeep / net {res: n} (net food: production left after everyone eats, or the shortfall),
    wasted {good: n} (won't fit in the stores), staffed [sid], workers / builders / idle (people),
    housing, soldiers (people in units and recruits), caps {good: room},
    starve {"units", "people"}, born, popNet, land (bought cells),
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
    on = {s["id"] for s in working}
    for s in working:
        _add(income, output(m, s, on))
    upkeep = dict.fromkeys(RESOURCES, 0)
    if m.has_hall(pid):  # no Town Hall (before founding): nobody eats or pays anything, as in end_of_turn
        upkeep["food"] = p["pop"] * FOOD_PER_PERSON
        upkeep["gold"] = land * territory.LAND_UPKEEP
        for utype in [u["type"] for u in m.units_of(pid)] + [r["type"] for r in recruits]:
            _add(upkeep, UNITS[utype]["upkeep"])
    have = logistics.stock(m, pid)
    trades = _trades(working, have, income, upkeep)

    idle = left - building["builders"]
    food = _food(m, pid, income["food"], upkeep["food"], room - p["pop"] - soldiers, idle) if m.has_hall(pid) \
        else {"starve": {"units": 0, "people": 0}, "born": 0, "popNet": 0}
    net = {r: 0 if r in FLAT or r in HELD else income[r] - upkeep[r] for r in RESOURCES}
    return {"income": income, "upkeep": upkeep, "net": net, "wasted": _wasted(m, pid, have, income, upkeep),
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
        if rate and t and have.get(t["give"], 0) + income[t["give"]] - upkeep[t["give"]] >= rate:
            upkeep[t["give"]] += rate
            income[t["get"]] += 1
            out.append([s["id"], t["give"], rate, t["get"]])
    return out


def _food(m, pid, made, eat, room, idle):
    """Who is born or starves: a surplus makes people while housing has room, a shortfall starves."""
    if made >= eat:
        born = max(0, min(room, (made - eat) // FOOD_PER_PERSON))
        return {"starve": {"units": 0, "people": 0}, "born": born, "popNet": born}
    dead, people = starvation(m, pid, eat - made, idle)
    return {"starve": {"units": len(dead), "people": people}, "born": 0,
            "popNet": -people - sum(UNITS[m.units[u]["type"]]["people"] for u in dead)}


def _wasted(m, pid, have, income, upkeep):
    """{good: n} of this turn's production that won't fit in the stores (as end_of_turn does it)."""
    wasted = {}
    for r in CAPPED:
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
        n = jobs(m, s)
        out += [[s["id"], r, x, s["id"] in on] for r, x in output(m, s, on).items()]
        if n and s["id"] in on:
            out += [[s["id"], "people", -n, True], [s["id"], "food", -n * FOOD_PER_PERSON, True]]
        if housing(m, s, hbonus):
            out.append([s["id"], "housing", housing(m, s, hbonus), True])
    for sid, give, rate, get in trades:
        out += [[sid, give, -rate, True, "trade"], [sid, get, 1, True, "trade"]]
    out += [[f"land:{k}", "gold", -territory.LAND_UPKEEP, True] for k in sorted(k for k, p in m.claims.items() if p == pid)]
    for cid, n in [*building["works"].items(), *building["orders"].items()]:
        out += [[cid, "people", -n, True, "build"], [cid, "food", -n * FOOD_PER_PERSON, True]]
    for r in m.orders[pid]["recruits"]:
        if r["at"] in m.structures:
            out += [[r["at"], res, -n, True] for res, n in {"people": r["people"], **UNITS[r["type"]]["upkeep"],
                                                           **{h: r["cost"].get(h, 0) for h in HELD}}.items() if n]
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
        out += [[u["id"], r, -UNITS[u["type"]]["cost"][r], True] for r in HELD if UNITS[u["type"]]["cost"].get(r)]
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
    for r in GLOBAL:
        p["res"][r] += income[r] - upkeep[r]
    have = logistics.stock(m, pid)
    for r in CAPPED:
        from_stock, from_income = split_upkeep(have[r], income[r], upkeep[r])
        logistics.take(m, pid, {r: from_stock})
        logistics.store(m, pid, r, income[r] - from_income)
    if income["food"] < upkeep["food"]:
        dead, people = starvation(m, pid, upkeep["food"] - income["food"], rep["idle"])
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


def starvation(m, pid, short, idle):
    """([unit ids], people) who die when food production is `short` of what everyone eats: idle people
    first, then units that eat (newest first), then people at work, until the rest can be fed."""
    feeds = lambda food: -(-food // FOOD_PER_PERSON)  # people whose deaths free at least `food`
    people = min(max(0, idle), feeds(short))
    short -= people * FOOD_PER_PERSON
    dead = []
    for u in reversed(m.units_of(pid)):
        eats = UNITS[u["type"]]["upkeep"].get("food", 0)
        if short > 0 and eats > 0:
            dead.append(u["id"])
            short -= eats
    if short > 0:
        people += min(m.players[pid]["pop"] - people, feeds(short))
    return dead, people


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
