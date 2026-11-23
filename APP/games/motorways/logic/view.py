"""What clients see (the contract with client/*.js). Everything is public (no hidden information).

public(match):
    {"w", "h", "rows": [terrain strings, "." land, "~" water, "^" mountain], "area": [x0, y0, x1, y1],
     "colors": [shop/house colours], "colorNames": [...],
     "week" (1-based), "time": s into the week, "weekLen": s, "overflow": s (a full timer loses),
     "fullPins": pins at which a shop's timer runs, "trips": team total, "light": "h" | "v" (green now),
     "players": {pid: {"name", "color", "points", "trips", "stock": {item: n},
                       "picked"?: 0 | 1, "gone"?: true, "cur"?: [x, y]}},
     "roads": {"<t>": {"o": pid, "k": "r" | "b" | "t", "f"?: "roundabout" | "light", "fo"?: pid}},
     "links": {"<a>,<b>": 1} (a < b),
     "houses": {id: {"t", "door", "c", "home": cars at home}},
     "shops": {id: {"t": top-left tile, "node", "door", "c", "pins", "timer": 0-1, "parked"}},
     "cars": {id: {"x", "y", "c"}} (cars on the road; tile units, centre of tile (x, y) is x+0.5),
     "pick"?: {"offers": [{"id", "name", "text"}, ...], "left": s},
     "rules": {"weekly", "span": {"b": n, "t": n | null (no limit)}}}
Tiles are t = y * w + x.
"""

import math

from gamekit.sync import quantize

from .city import COLOR_NAMES, COLORS, FULL_PINS
from .roads import MAX_SPAN
from .upgrades import UPGRADES, WEEKLY

_RULES = {"weekly": WEEKLY["roads"], "span": dict(MAX_SPAN)}


def _player(p):
    out = {"name": p.name, "color": p.color, "points": round(p.points), "trips": p.trips, "stock": dict(p.stock)}
    if p.picked is not None:
        out["picked"] = p.picked
    if p.gone:
        out["gone"] = True
    if p.cursor is not None:
        out["cur"] = p.cursor
    return out


def _road(r):
    out = {"o": r.owner, "k": r.kind}
    if r.feature:
        out["f"], out["fo"] = r.feature, r.feat_owner
    return out


def public(m):
    net, city, traffic, g = m.net, m.city, m.traffic, m.grid
    state = {
        "w": g.w, "h": g.h, "rows": g.rows(), "area": g.area(),
        "colors": COLORS, "colorNames": COLOR_NAMES,
        "week": m.week + 1, "time": quantize(m.time, 0.1), "weekLen": m.week_len,
        "overflow": m.overflow, "fullPins": FULL_PINS, "trips": traffic.trips, "light": traffic.green(),
        "players": {pid: _player(p) for pid, p in m.players.items()},
        "roads": {str(t): _road(r) for t, r in net.roads.items()},
        "links": {f"{a},{b}": 1 for a, linked in net.links.items() for b in linked if a < b},
        "houses": {h.id: {"t": h.node, "door": h.door, "c": h.color, "home": h.home} for h in city.houses.values()},
        "shops": {s.id: {"t": s.tiles[0], "node": s.node, "door": s.door, "c": s.color, "pins": s.pins,
                         "timer": quantize(min(1.0, s.timer / m.overflow), 0.01), "parked": traffic.parked(s)}
                  for s in city.shops.values()},
        "cars": {},
        "rules": _RULES,
    }
    for car in traffic.cars.values():
        if car.path is not None:
            x, y = traffic.position(car)
            state["cars"][car.id] = {"x": quantize(x, 0.02), "y": quantize(y, 0.02), "c": car.color}
    if m.offers is not None:
        state["pick"] = {"offers": [{"id": o, "name": UPGRADES[o]["name"], "text": UPGRADES[o]["text"]} for o in m.offers],
                         "left": math.ceil(max(0.0, m.pick_left))}
    return state
