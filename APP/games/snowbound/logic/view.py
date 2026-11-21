"""What clients see (the contract with client/*.js).

public(match):
    {"w", "h", "cabin": [x, y], "time": s, "rows": World.rows(), "defs": content.defs(),
     "players": {pid: {"name", "color", "cash", "cleared", "rate" (machine snow/s now), "food",
                       "warmth", "status": "ok" | "frenzy" | "starving" | "frostbite",
                       "focus"?: [x, y], "cursor"?: [x, y], "owned": {machine id: n}}},
     "crews": {"<pid>:<machine>": {"x", "y", "m", "p", "n", "s": idle|driving|working|stalled}},
     "weather": {"kind": clear|warning|blizzard, "left": s}, "woodpile": logs,
     "stove": {"lit": bool, "burn": logs per minute}, "flake"?: {"x", "y", "left"},
     "progress": {"reached", "total", "goal": %}, "shared": {upgrade id: pid},
     "log": {"<n>": text}, "logCount": n, "prices": {item: $}}
private(match, pid): your shop and supplies
    {"click": snow per click, "rations", "diesel", "dieselUse": L/s, "frenzy": s,
     "machines": {id: {"owned", "cost1", "cost10", "rate"}}, "upgrades": [visible ids by cost],
     "owned": [your upgrade ids], "auto": [delivered items]}
"""

from . import crews, survival
from .content import MACHINES, UPGRADES, defs, machine_cost
from .economy import PRICES

_DEFS = defs()


def _status(p):
    if p.frostbite:
        return "frostbite"
    if p.starving:
        return "starving"
    return "frenzy" if p.frenzy > 0 else "ok"


def public(match):
    world = match.world
    blizzard = match.weather.blizzard
    players = {}
    for pid, p in match.players.items():
        entry = {"name": p.name, "color": p.color, "cash": int(p.cash), "cleared": int(p.cleared),
                 "rate": round(p.base_rate() * p.work_mult(blizzard), 1), "food": int(p.food),
                 "warmth": int(p.warmth), "status": _status(p),
                 "owned": {mid: n for mid, n in p.owned.items() if n}}
        if p.focus is not None:
            entry["focus"] = list(world.xy(p.focus))
        if p.cursor is not None:
            entry["cursor"] = list(p.cursor)
        players[pid] = entry
    state = {
        "w": world.w, "h": world.h, "cabin": [world.cx, world.cy], "time": int(match.time),
        "rows": world.rows(), "defs": _DEFS, "players": players, "crews": crews.public(match),
        "weather": match.weather.public(), "woodpile": round(match.woodpile, 1),
        "stove": {"lit": match.woodpile > 0, "burn": round(survival.stove_burn(match) * 60, 1)},
        "progress": {"reached": len(world.reached_list), "total": world.w * world.h,
                     "goal": round(match.goal * 100)},
        "shared": dict(match.shared_upgrades),
        "log": {str(n): text for n, text in match.log}, "logCount": match.log_count,
        "prices": PRICES,
    }
    if match.flake is not None:
        x, y = world.xy(match.flake["i"])
        state["flake"] = {"x": x, "y": y, "left": int(match.flake["left"])}
    return state


def private(match, pid):
    p = match.players.get(pid)
    if p is None:
        return None
    visible = sorted((uid for uid in UPGRADES if p.upgrade_visible(uid, match.shared_upgrades)),
                     key=lambda uid: UPGRADES[uid]["cost"])
    return {
        "click": round(p.click_power(), 2), "rations": p.rations, "diesel": round(p.diesel, 1),
        "dieselUse": round(p.diesel_use(), 2), "frenzy": int(p.frenzy),
        "machines": {mid: {"owned": p.owned[mid], "cost1": machine_cost(mid, p.owned[mid]),
                           "cost10": machine_cost(mid, p.owned[mid], 10),
                           "rate": round(p.machine_rate(mid), 1)} for mid in MACHINES},
        "upgrades": visible, "owned": sorted(p.upgrades),
        "auto": sorted(item for item in ("rations", "diesel", "logs") if p.has_auto(item)),
    }
