"""View: the public and private state clients get (the wire contract with client/*.js).

Sent with gamekit's Snapshots (per-tick deltas), so: collections are dicts keyed by id, floats
are quantized, no None values (a key is left out instead).

public(match, cursors) = {
  "w", "h", "cycleLength",
  "clock": {"time" (game s, 0.1), "cycle", "paused" (bool), "speed" (1-3)},
  "defs": content.defs() (elements, element order/chars, buildings; never changes),
  "rows": {layer: {"<row y>": "<string, one char per cell>"}} for layers
      "el"    element: defs.chars[index of element in defs.order]
      "mass"  "0"-"9": gas 0.25 kg steps, liquid 100 kg steps ("0" for solids/vacuum)
      "temp"  ROW_CHARS[(°C + 40) / 4] clamped (so "0" <= -40 °C, 4 °C steps); "-" vacuum
      "germ"  "0"-"9": log10(germs + 1)
      "decor" ROW_CHARS[decor + 30] clamped (-30..+31)
    rebuilt at most every half game second (or when buildings change), so a row is resent
    only when something in it changed.
  "buildings": {id: {"t" type, "x", "y", "b" (1 built / 0 site), "p" (progress %), "by", "prio",
      "on" (0/1), "pw" (0/1 powered), "st"? status text, "store"? {el: kg}, "need"? {cost key:
      kg still missing}, "dc"? 1 marked for deconstruction, "dcBy"?}},
  "digs": {"<cell index>": {"by", "prio", "p" (progress %)}},
  "items": {id: {"el", "kg", "x", "y"}},
  "dupes": {id: {"name", "x", "y" (cells, 0.05), "task", "breath", "kcal", "bladder", "stress",
      "health", "germs", "sick" (0/1), "carry"? {"el", "kg"}}},
  "power": networks.power_summary(), "pipes": networks.pipe_summary(),
  "colony": {el: kg} (debris + everything in storage),
  "players": {pid: {"name", "color", "cursor"? [x, y], "tool"?, "drag"? [x0, y0, x1, y1]}},
  "log": {"<n>": text} (last 30), "logCount",
}
private(match, pid, cursor) = {"cell"?: {"x", "y", "el", "kg", "temp", "germs", "decor"}}
for the cell under that player's cursor (exact values for the hover panel).
"""

import math

from gamekit.sync import quantize

from . import content
from .content import CHARS, PHASE, ROW_CHARS

ROW_STEP = 0.5  # game seconds between grid row rebuilds


def _clamp(n, low, high):
    return low if n < low else high if n > high else n


def _rows(match):
    world = match.world
    key = (int(match.time / ROW_STEP), match.buildings.version, len(match.digs), match.items.version)
    cache = getattr(match, "_rows_cache", None)
    if cache and cache[0] == key:
        return cache[1]
    w = world.w
    el, mass, temp, germs, decor = world.el, world.mass, world.temp, world.germs, world.decor
    layers = {"el": {}, "mass": {}, "temp": {}, "germ": {}, "decor": {}}
    top = len(ROW_CHARS) - 1
    for y in range(world.h):
        r = range(y * w, y * w + w)
        e_row, m_row, t_row, g_row, d_row = [], [], [], [], []
        for i in r:
            e = el[i]
            phase = PHASE[e]
            e_row.append(CHARS[e])
            if phase == "gas":
                m_row.append(str(_clamp(int(mass[i] / 0.25), 0, 9)))
            elif phase == "liquid":
                m_row.append(str(_clamp(int(mass[i] / 100), 0, 9)))
            else:
                m_row.append("0")
            t_row.append("-" if phase == "vacuum" else ROW_CHARS[_clamp(int((temp[i] + 40) // 4), 0, top)])
            g = germs[i]
            g_row.append(str(_clamp(int(math.log10(g + 1)), 0, 9)) if g > 0 else "0")
            d_row.append(ROW_CHARS[_clamp(int(round(decor[i])) + 30, 0, top)])
        k = str(y)
        layers["el"][k] = "".join(e_row)
        layers["mass"][k] = "".join(m_row)
        layers["temp"][k] = "".join(t_row)
        layers["germ"][k] = "".join(g_row)
        layers["decor"][k] = "".join(d_row)
    match._rows_cache = (key, layers)
    return layers


def _kg(v):
    return quantize(v, 0.1) if v < 100 else int(round(v))


def _building(b):
    out = {"t": b.type, "x": b.x, "y": b.y, "b": 1 if b.built else 0, "p": int(b.progress * 100),
           "by": b.by, "prio": b.prio, "on": 1 if b.enabled else 0, "pw": 1 if b.powered else 0}
    if b.status:
        out["st"] = b.status
    if b.store:
        out["store"] = {el: _kg(kg) for el, kg in b.store.items() if kg >= 0.05}
    if not b.built:
        need = {}
        for key, kg in b.d["cost"].items():
            have = sum(v for el, v in b.delivered.items() if content.matches(el, key))
            if kg - have > 0.01:
                need[key] = _kg(kg - have)
        if need:
            out["need"] = need
    if b.deconstruct:
        out["dc"] = 1
        out["dcBy"] = b.decon_by
    return out


def _dupe(d):
    out = {"name": d.name, "x": quantize(d.x, 0.05), "y": quantize(d.y, 0.05), "task": d.task,
           "breath": int(d.breath), "kcal": int(d.kcal), "bladder": int(d.bladder),
           "stress": int(d.stress), "health": int(d.health), "germs": int(d.germs),
           "sick": 1 if d.sick > 0 else 0}
    if d.carry:
        out["carry"] = {"el": d.carry["el"], "kg": _kg(d.carry["kg"])}
    return out


def colony_totals(match):
    totals = match.items.totals()
    for b in match.buildings:
        if b.built and b.d["kind"] in ("storage", "ration_box"):
            for el, kg in b.store.items():
                totals[el] = totals.get(el, 0.0) + kg
    return {el: _kg(kg) for el, kg in totals.items() if kg >= 0.05}


def _players(match, cursors):
    out = {}
    for pid, name in match.names.items():
        entry = {"name": name, "color": match.colors.get(pid, "#888888")}
        entry.update(cursors.get(pid, {}))
        out[pid] = entry
    return out


def public(match, cursors):
    return {
        "w": match.world.w, "h": match.world.h, "cycleLength": int(match.cycle_length),
        "clock": {"time": quantize(match.time, 0.1), "cycle": match.cycle,
                  "paused": match.paused, "speed": match.speed},
        "defs": _defs(),
        "rows": _rows(match),
        "buildings": {b.id: _building(b) for b in match.buildings},
        "digs": {str(i): {"by": o["by"], "prio": o["prio"], "p": int(o["progress"] * 100)}
                 for i, o in match.digs.items()},
        "items": {it.id: {"el": it.el, "kg": _kg(it.kg), "x": it.x, "y": it.y} for it in match.items},
        "dupes": {d.id: _dupe(d) for d in match.dupes.values()},
        "power": match.networks.power_summary(),
        "pipes": match.networks.pipe_summary(),
        "colony": colony_totals(match),
        "players": _players(match, cursors),
        "log": {str(n): text for n, text in match.log_entries.items()},
        "logCount": match.log_count,
    }


def private(match, pid, cursor):
    if not cursor:
        return {}
    x, y = cursor
    world = match.world
    if not world.inside(x, y):
        return {}
    i = world.idx(x, y)
    return {"cell": {"x": x, "y": y, "el": world.element_id(i), "kg": quantize(world.mass[i], 0.01),
                     "temp": quantize(world.temp[i], 0.1), "germs": int(world.germs[i]),
                     "decor": quantize(world.decor[i], 0.1)}}


_DEFS = None


def _defs():
    global _DEFS
    if _DEFS is None:
        _DEFS = content.defs()
    return _DEFS

