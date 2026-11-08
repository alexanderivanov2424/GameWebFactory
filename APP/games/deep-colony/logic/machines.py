"""Machines: per-kind building behaviour (params come from each building JSON's "params").

step(match, dt) runs KINDS[kind](match, b, dt) for every finished building whose kind isn't "none".
A disabled building does nothing (status "Disabled"). Each machine sets b.status and, for power
users, b.state["active"] (wants power this step; networks.py decides b.powered from the previous
step); generators set b.state["producing"]. A machine that is active (and powered) or producing
adds its def's "heat" (kJ/s) at its bottom-left cell.

Chore API (called by chores.py):
    wants_operator(match, b)      manual generator / nutrient press wants a colonist now
    operate(match, b, dupe, dt)   called every step a colonist works at an operated building
    toilet_usable(match, b), use_toilet(match, b, dupe) -> bool   (bladder 0, germs, needs_wash)
    basin_usable(match, b), wash(match, b, dupe) -> bool          (germs 0, needs_wash False)
    harvest_ready(b), harvest(match, b)                           fungus bed crop as debris
    needs_emptying(b), empty(match, b)                            outhouse contents as debris
    storage_room(b, el) -> kg     storage: anything; ration box: food only; others 0
"""

from . import content

NO_TIME = -1e9
OPERATE_WINDOW = 0.5


def _top(b):
    return b.x, b.y


def _bottom_left(b):
    return b.x, b.y + b.d["h"] - 1


def _gas_full(match, x, y, limit):
    w = match.world
    i = w.idx(x, y)
    return w.is_gas(i) and w.mass[i] > limit


def _need_power(b, active, idle_status="Working"):
    """Common ending for power users: set active, status, and say whether it can run now."""
    b.state["active"] = active
    if not active:
        return False
    if not b.powered:
        b.status = "No power"
        return False
    b.status = idle_status
    return True


# --- air -----------------------------------------------------------------------------------

def oxygenator(match, b, dt):
    p = b.d["params"]
    algae = b.store.get(p["input"], 0.0)
    if algae <= 0.001:
        b.state["active"] = False
        b.status = "No algae"
        return
    x, y = _top(b)
    if _gas_full(match, x, y, p["maxPressure"]):
        b.state["active"] = False
        b.status = "Full"
        return
    if not _need_power(b, True):
        return
    used = min(p["inRate"] * dt, algae)
    b.store[p["input"]] = algae - used
    match.world.emit(x, y, p["output"], used * p["outRate"] / p["inRate"], p["outTemp"])


def electrolyzer(match, b, dt):
    p = b.d["params"]
    nets = match.networks
    if nets.pipe_has(b, "pipeIn", "water") <= 0.001:
        b.state["active"] = False
        b.status = "No water"
        return
    x, y = _top(b)
    x2 = b.x + b.d["w"] - 1
    if _gas_full(match, x, y, p["maxPressure"]) or _gas_full(match, x2, y, p["maxPressure"]):
        b.state["active"] = False
        b.status = "Full"
        return
    if not _need_power(b, True):
        return
    _, kg, _, _ = nets.pipe_take(b, "pipeIn", ["water"], p["inRate"] * dt)
    match.world.emit(x, y, "oxygen", kg * p["oxygen"], p["outTemp"])
    match.world.emit(x2, y, "hydrogen", kg * p["hydrogen"], p["outTemp"])


def deodorizer(match, b, dt):
    p = b.d["params"]
    w = match.world
    sand = b.stored("sand")
    cells = []
    for cy in range(b.y - p["radius"], b.y + b.d["h"] + p["radius"]):
        for cx in range(b.x - p["radius"], b.x + b.d["w"] + p["radius"]):
            if w.inside(cx, cy) and w.element_id(w.idx(cx, cy)) == "polluted_oxygen":
                cells.append(w.idx(cx, cy))
    if sand <= 0.001:
        b.status = "No sand"
        return
    if not cells:
        b.status = "Idle"
        return
    b.status = "Working"
    credit = min(b.state.get("credit", 0.0) + p["rate"] * dt, p["rate"])
    per_kg = p["sandRate"] / p["rate"]
    for i in cells:
        if credit <= 0 or sand <= 0.001:
            break
        mass = w.mass[i]
        cost = mass * per_kg
        if cost > sand:
            continue
        w.set_cell(i, "oxygen", mass, w.temp[i], 0.0)
        credit -= mass
        sand -= cost
        b.store["sand"] = max(0.0, b.stored("sand") - cost)
    b.state["credit"] = credit


# --- power ---------------------------------------------------------------------------------

def manual_generator(match, b, dt):
    on = match.time - b.state.get("operated_at", NO_TIME) <= OPERATE_WINDOW
    b.state["producing"] = on
    b.status = "Running" if on else ("Waiting for colonist" if match.networks.needs_power(b) else "Idle")


def coal_generator(match, b, dt):
    p = b.d["params"]
    coal = b.store.get("coal", 0.0)
    if coal <= 0.001:
        b.state["producing"] = False
        b.status = "No coal"
        return
    on = match.networks.needs_power(b)
    b.state["producing"] = on
    if not on:
        b.status = "Idle"
        return
    b.status = "Burning"
    b.store["coal"] = max(0.0, coal - p["coalRate"] * dt)
    x, y = _top(b)
    match.world.emit(x, y, "carbon_dioxide", p["co2Rate"] * dt, p["co2Temp"])


def battery(match, b, dt):
    cap = b.d["power"]["capacity"]
    charge = max(0.0, b.state.get("charge", 0.0) - b.d["params"].get("leak", 0.0) * dt)
    b.state["charge"] = charge
    b.status = f"Charge {int(100 * charge / cap)}%" if cap else ""


def heater(match, b, dt):
    p = b.d["params"]
    x, y = _bottom_left(b)
    if match.world.temp[match.world.idx(x, y)] >= p["maxTemp"]:
        b.state["active"] = False
        b.status = "Warm enough"
        return
    if _need_power(b, True, "Heating"):
        cells = b.cells()
        for cx, cy in cells:
            match.world.add_heat(match.world.idx(cx, cy), p["heat"] * dt / len(cells))


# --- food ----------------------------------------------------------------------------------

def fungus_bed(match, b, dt):
    p = b.d["params"]
    x, y = _bottom_left(b)
    temp = match.world.temp[match.world.idx(x, y)]
    growth = b.state.get("growth", 0.0)
    if growth >= p["growTime"]:
        b.status = "Ripe"
    elif temp < p["minTemp"]:
        b.status = "Too cold"
    elif temp > p["maxTemp"]:
        b.status = "Too hot"
    else:
        growth = min(p["growTime"], growth + dt)
        b.state["growth"] = growth
        b.status = "Ripe" if growth >= p["growTime"] else f"Growing {int(100 * growth / p['growTime'])}%"


def harvest_ready(b):
    return b.built and b.d["kind"] == "fungus_bed" and b.state.get("growth", 0.0) >= b.d["params"]["growTime"]


def harvest(match, b):
    x, y = _bottom_left(b)
    match.items.add("fungus", b.d["params"]["yield"], x, y, match.world.temp[match.world.idx(x, y)])
    b.state["growth"] = 0.0
    b.status = "Growing 0%"


def colony_food(match):
    """kg of food (elements with phase "food") in stores and lying around as debris."""
    total = 0.0
    for el, kg in match.items.totals().items():
        if content.ELEMENTS[el]["phase"] == "food":
            total += kg
    for b in match.buildings:
        for el, kg in b.store.items():
            if content.ELEMENTS.get(el, {}).get("phase") == "food":
                total += kg
    return total


def _press_ready(match, b):
    p = b.d["params"]
    return (b.enabled and b.stored("dirt") >= p["dirt"]
            and match.networks.pipe_has(b, "pipeIn", "water") >= p["water"]
            and colony_food(match) < p["maxFood"])


def nutrient_press(match, b, dt):
    p = b.d["params"]
    ready = _press_ready(match, b)
    b.state["active"] = ready
    if not ready:
        b.status = "No dirt" if b.stored("dirt") < p["dirt"] else (
            "No water" if match.networks.pipe_has(b, "pipeIn", "water") < p["water"] else "Enough food")
        return
    b.status = "Needs colonist" if b.powered else "No power"
    if b.state.get("work", 0.0) < p["work"]:
        return
    el, kg, _, _ = match.networks.pipe_take(b, "pipeIn", ["water"], p["water"])
    if kg < p["water"] - 1e-6:
        if kg:
            match.networks.pipe_put(b, "pipeIn", el, kg, 20.0, 0.0)
        return
    left = p["dirt"]
    for key in list(b.store):
        if content.matches(key, "dirt"):
            took = min(left, b.store[key])
            b.store[key] -= took
            left -= took
    b.state["work"] = 0.0
    x, y = _bottom_left(b)
    match.items.add(p["product"], p["productKg"], x, y, 20.0)


# --- operated buildings --------------------------------------------------------------------

def wants_operator(match, b):
    if not b.built or not b.enabled:
        return False
    kind = b.d["kind"]
    if kind == "manual_generator":
        return match.networks.needs_power(b)
    if kind == "nutrient_press":
        if _press_ready(match, b):
            b.state["active"] = True
            return b.powered
    return False


def operate(match, b, dupe, dt):
    kind = b.d["kind"]
    if kind == "manual_generator":
        b.state["operated_at"] = match.time
    elif kind == "nutrient_press" and b.powered:
        b.state["work"] = b.state.get("work", 0.0) + dt


# --- plumbing ------------------------------------------------------------------------------

def pump(match, b, dt):
    p = b.d["params"]
    w = match.world
    nets = match.networks
    room = nets.pipe_room(b, "pipeOut")
    r = int(p.get("radius", 1))
    cells = [w.idx(cx, cy) for cy in range(b.y + b.d["h"] - 1, b.y + b.d["h"] + r)
             for cx in range(b.x - r, b.x + b.d["w"] + r) if w.inside(cx, cy)]
    liquid = [i for i in cells if w.is_liquid(i)]
    if room <= 0.01 or not liquid:
        b.state["active"] = False
        b.status = "Pipe full" if liquid else "No liquid"
        return
    if not _need_power(b, True, "Pumping"):
        return
    want = min(p["rate"] * dt, room)
    for i in liquid:
        if want <= 0.0001:
            break
        el, kg, temp, germs = w.take(i, [w.element_id(i)], want)
        if kg:
            put = nets.pipe_put(b, "pipeOut", el, kg, temp, germs)
            want -= kg
            if put < kg:
                w.emit(*w.xy(i), el, kg - put, temp)


def vent(match, b, dt):
    p = b.d["params"]
    w = match.world
    x, y = _top(b)
    i = w.idx(x, y)
    if w.is_liquid(i) and w.mass[i] >= p["maxMass"]:
        b.status = "Full"
        return
    el, kg, temp, germs = match.networks.pipe_take(b, "pipeIn", None, p["rate"] * dt)
    if not kg:
        b.status = "Empty"
        return
    placed = w.emit(x, y, el, kg, temp, germs)
    if placed < kg:
        match.networks.pipe_put(b, "pipeIn", el, kg - placed, temp, germs * (kg - placed) / kg)
    b.status = "Venting"


def water_sieve(match, b, dt):
    p = b.d["params"]
    nets = match.networks
    sand = b.stored("sand")
    has = nets.pipe_has(b, "pipeIn", "polluted_water")
    if has <= 0.001:
        b.state["active"] = False
        b.status = "No polluted water"
        return
    if sand <= 0.001:
        b.state["active"] = False
        b.status = "No sand"
        return
    room = nets.pipe_room(b, "pipeOut")
    if room <= 0.01:
        b.state["active"] = False
        b.status = "Pipe full"
        return
    if not _need_power(b, True, "Cleaning"):
        return
    per_kg = p["sandRate"] / p["rate"]
    amount = min(p["rate"] * dt, room, has, sand / per_kg)
    _, kg, temp, _ = nets.pipe_take(b, "pipeIn", ["polluted_water"], amount)
    put = nets.pipe_put(b, "pipeOut", "water", kg, temp, 0.0)
    b.store["sand"] = max(0.0, b.stored("sand") - put * per_kg)
    for key in list(b.store):
        if content.matches(key, "sand") and key != "sand":
            b.store[key] = 0.0


# --- toilets and basins --------------------------------------------------------------------

def outhouse(match, b, dt):
    p = b.d["params"]
    if b.state.get("uses", 0) >= p["uses"]:
        b.status = "Needs emptying"
    elif b.stored("dirt") < p["dirtPerUse"]:
        b.status = "Needs dirt"
    else:
        b.status = f"Ready ({p['uses'] - b.state.get('uses', 0)} uses left)"


def lavatory(match, b, dt):
    p = b.d["params"]
    nets = match.networks
    if nets.pipe_has(b, "pipeIn", "water") < p["waterPerUse"]:
        b.status = "Needs water"
    elif nets.pipe_room(b, "pipeOut") < p["outPerUse"]:
        b.status = "Drain full"
    else:
        b.status = "Ready"


def wash_basin(match, b, dt):
    p = b.d["params"]
    nets = match.networks
    if nets.pipe_has(b, "pipeIn", "water") < p["waterPerUse"]:
        b.status = "Needs water"
    elif nets.pipe_room(b, "pipeOut") < p["waterPerUse"]:
        b.status = "Drain full"
    else:
        b.status = "Ready"


def toilet_usable(match, b):
    if not b.built or not b.enabled:
        return False
    p = b.d["params"]
    kind = b.d["kind"]
    if kind == "outhouse":
        return b.stored("dirt") >= p["dirtPerUse"] and b.state.get("uses", 0) < p["uses"]
    if kind == "lavatory":
        return (match.networks.pipe_has(b, "pipeIn", "water") >= p["waterPerUse"]
                and match.networks.pipe_room(b, "pipeOut") >= p["outPerUse"])
    return False


def use_toilet(match, b, dupe):
    if not toilet_usable(match, b):
        return False
    p = b.d["params"]
    if b.d["kind"] == "outhouse":
        left = p["dirtPerUse"]
        for key in list(b.store):
            if content.matches(key, "dirt") and left > 0:
                took = min(left, b.store[key])
                b.store[key] -= took
                left -= took
        b.store["polluted_dirt"] = b.store.get("polluted_dirt", 0.0) + p["dirtPerUse"]
        b.state["uses"] = b.state.get("uses", 0) + 1
    else:
        _, kg, temp, _ = match.networks.pipe_take(b, "pipeIn", ["water"], p["waterPerUse"])
        match.networks.pipe_put(b, "pipeOut", "polluted_water", p["outPerUse"], temp, p["germs"])
    dupe.bladder = 0
    dupe.germs += p["germs"]
    dupe.needs_wash = True
    return True


def basin_usable(match, b):
    if not b.built or not b.enabled or b.d["kind"] != "wash_basin":
        return False
    p = b.d["params"]
    return (match.networks.pipe_has(b, "pipeIn", "water") >= p["waterPerUse"]
            and match.networks.pipe_room(b, "pipeOut") >= p["waterPerUse"])


def wash(match, b, dupe):
    if not basin_usable(match, b):
        return False
    p = b.d["params"]
    _, kg, temp, _ = match.networks.pipe_take(b, "pipeIn", ["water"], p["waterPerUse"])
    match.networks.pipe_put(b, "pipeOut", "polluted_water", kg, temp, dupe.germs)
    dupe.germs = 0
    dupe.needs_wash = False
    return True


def needs_emptying(b):
    return b.built and b.d["kind"] == "outhouse" and b.state.get("uses", 0) >= b.d["params"]["uses"]


def empty(match, b):
    p = b.d["params"]
    x, y = _bottom_left(b)
    kg = b.store.pop("polluted_dirt", 0.0)
    uses = b.state.get("uses", 0)
    if kg > 0:
        match.items.add("polluted_dirt", kg, x, y, match.world.temp[match.world.idx(x, y)],
                        p["germs"] * uses)
    b.state["uses"] = 0


# --- storage -------------------------------------------------------------------------------

def storage_room(b, el):
    if not b.built:
        return 0.0
    kind = b.d["kind"]
    if kind == "storage" or (kind == "ration_box" and content.ELEMENTS.get(el, {}).get("phase") == "food"):
        return max(0.0, b.d["capacity"] - b.stored())
    return 0.0


def _nothing(match, b, dt):
    pass


KINDS = {
    "oxygenator": oxygenator, "electrolyzer": electrolyzer, "deodorizer": deodorizer,
    "manual_generator": manual_generator, "coal_generator": coal_generator, "battery": battery,
    "fungus_bed": fungus_bed, "nutrient_press": nutrient_press, "pump": pump, "vent": vent,
    "outhouse": outhouse, "lavatory": lavatory, "wash_basin": wash_basin, "water_sieve": water_sieve,
    "heater": heater, "storage": _nothing, "ration_box": _nothing,
}


def step(match, dt):
    for b in match.buildings:
        kind = b.d["kind"]
        if not b.built or kind == "none":
            continue
        if not b.enabled:
            b.state["active"] = False
            b.state["producing"] = False
            b.status = "Disabled"
            continue
        fn = KINDS.get(kind)
        if fn is None:
            continue
        fn(match, b, dt)
        heat = b.d["heat"]
        if heat and (b.state.get("producing")
                     or (b.state.get("active") and (b.powered or not b.d["power"].get("use")))):
            x, y = _bottom_left(b)
            match.world.add_heat(match.world.idx(x, y), heat * dt)
