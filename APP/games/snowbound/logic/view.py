"""What clients see (the contract with client/*.js).

public(match):
    {"w", "h", "cabin": [x, y] (lot), "time": s, "rows": World.rows(), "defs": content.defs(),
     "players": {pid: {"name", "color", "x", "y" (world coordinates), "swing": bool,
                       "cash" (the team's), "cleared", "rate" (machine snow/s now), "food", "warmth",
                       "status": "ok" | "frenzy" | "starving" | "frostbite",
                       "owned": {machine id: n} (the team's), "goods": $ from goods}},
     "rally"?: [x, y] lot | {"follow": pid} (the team's rally point; none: anywhere),
     "team": {"cash", "diesel", "rations", "dieselUse"} (shared by every player),
     "huts": {"<n>": [x, y]}, "hutCost": $, "heat": {"cabin": lots, "hut": lots},
     "depots": {"<n>": [x, y]} (Snow Depots), "depotCost": $, "markets": {"<n>": [x, y]} (Old Rail
     Stations), "landmarks": landmarks.public(), "effects": [team effect ids from landmarks],
     "roadLevels": [{"name", "cost", "unit", "walk"}] (roads.LEVELS; index = level),
     "weather": {"kind": clear|warning|blizzard, "left": s}, "woodpile": logs,
     "stove": {"lit": bool, "burn": logs per minute}, "flake"?: {"x", "y", "left"},
     "progress": {"reached" (clear now), "dusted" (reached, snowed on again), "total", "goal": %},
     "shared": {upgrade id: pid who bought it} (every upgrade is the team's), "log": {"<n>": text}, "logCount": n, "prices": {item: $},
     "move": {"radius", "speed", "dusted", "road": [walk x per road level], "frostbite", "starving", "wade", "reach"},
     "beams": {"<n>": {"x0", "y0", "x1", "y1", "c"}} (Jet Blower shots, kept 1.5 s)}
     (move: the character rules client/grid.js needs to predict your walking)
private(match, pid): your shop, supplies and the units near you
    {"click": snow per swing, "reach": lots, "splash": share hitting the 4 lots around (Shovel
     Buddy), "wade": deepest snow level you can walk on, "rations", "diesel", "dieselUse": L/s (team's), "frenzy": s,
     "machines": {id: {"owned", "cost1", "cost10", "rate"}}, "upgrades": [visible ids by cost],
     "owned": [the team's upgrade ids], "auto": [delivered items],
     "carried": snow the team's machines are carrying, "waiting": $ of goods waiting in processors,
     "cargo": $ of goods on sleds (all team-wide),
     "units": {uid: {"x", "y", "m", "p", "s": idle|moving|working|hauling|full|stalled|unlit|charging,
                     "l"?: load 0-1, "f"?: [processor input 0-1, goods waiting]}}}
spectator(match): {"units": ...} near any character (spectators follow a player).
"""

from . import avatars, hauling, landmarks, survival, units
from .content import GOODS, MACHINES, UPGRADES, defs, machine_cost
from .economy import PRICES
from .roads import LEVELS
from .world import WADE_LEVEL

VIEW = 36  # units within this many lots (square) of your character are sent to you

_DEFS = defs()
_MOVE = {"radius": avatars.RADIUS, "speed": avatars.WALK_SPEED, "dusted": avatars.DUSTED_SLOW,
         "road": [level["walk"] for level in LEVELS],
         "frostbite": avatars.FROSTBITE_SLOW, "starving": avatars.STARVING_SLOW,
         "wade": WADE_LEVEL, "reach": avatars.REACH}


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
        entry = {"name": p.name, "color": p.color, "x": round(p.x, 2), "y": round(p.y, 2),
                 "swing": p.swinging > 0, "cash": int(p.cash), "cleared": int(p.cleared),
                 "rate": round(p.base_rate() * p.work_mult(blizzard), 1), "food": int(p.food),
                 "warmth": int(p.warmth), "status": _status(p),
                 "owned": {mid: n for mid, n in p.owned.items() if n}, "goods": int(p.goods_sold)}
        players[pid] = entry
    state = {
        "w": world.w, "h": world.h, "cabin": [world.cx, world.cy], "time": int(match.time),
        "rows": world.rows(), "defs": _DEFS, "players": players,
        "team": {"cash": int(match.stores.cash), "diesel": round(match.stores.diesel, 1),
                 "rations": match.stores.rations, "dieselUse": round(match.diesel_use(), 2)},
        "huts": {str(k): list(xy) for k, xy in enumerate(match.huts)}, "hutCost": match.hut_cost(),
        "heat": {"cabin": survival.CABIN_HEAT, "hut": survival.HUT_HEAT},
        "depots": {str(k): list(world.xy(i)) for k, i in enumerate(match.depots)},
        "depotCost": hauling.depot_cost(match),
        "markets": {str(k): list(world.xy(i)) for k, i in enumerate(match.markets)},
        "landmarks": landmarks.public(match), "effects": sorted(match.effects), "roadLevels": LEVELS,
        "weather": match.weather.public(), "woodpile": round(match.woodpile, 1),
        "stove": {"lit": match.woodpile > 0, "burn": round(survival.stove_burn(match) * 60, 1)},
        "progress": {"reached": world.cleared(), "dusted": len(world.dusted), "total": world.w * world.h,
                     "goal": round(match.goal * 100)},
        "shared": dict(match.shared_upgrades),
        "log": {str(n): text for n, text in match.log}, "logCount": match.log_count,
        "prices": PRICES, "move": _MOVE,
        "beams": {k: {key: v for key, v in b.items() if key != "left"} for k, b in match.beams.items()},
    }
    if isinstance(match.rally_spot, tuple):
        state["rally"] = {"follow": match.rally_spot[1]}
    elif match.rally_spot is not None:
        state["rally"] = list(world.xy(match.rally_spot))
    if match.flake is not None:
        x, y = world.xy(match.flake["i"])
        state["flake"] = {"x": x, "y": y, "left": int(match.flake["left"])}
    return state


def private(match, pid):
    p = match.players.get(pid)
    if p is None:
        return None
    visible = sorted((uid for uid in UPGRADES if p.upgrade_visible(uid)),
                     key=lambda uid: UPGRADES[uid]["cost"])
    power, reach, splash = match.shovel(p)
    carried = waiting = cargo = 0.0
    for u in match.units.values():
        carried += u.load
        if u.outbox:
            waiting += u.outbox * GOODS[MACHINES[u.mid]["recipe"]["out"]]["value"]
        cargo += sum(n * GOODS[g]["value"] for g, n in u.cargo.items())
    return {
        "click": round(power, 2), "reach": reach, "splash": splash, "wade": p.wade_level(),
        "rations": p.rations, "diesel": round(p.diesel, 1),
        "dieselUse": round(match.diesel_use(), 2), "frenzy": int(p.frenzy),
        "machines": {mid: {"owned": p.owned[mid], "cost1": machine_cost(mid, p.owned[mid]),
                           "cost10": machine_cost(mid, p.owned[mid], 10),
                           "rate": round(p.machine_rate(mid), 1)} for mid in MACHINES},
        "upgrades": visible, "owned": sorted(p.upgrades),
        "auto": sorted(item for item in ("rations", "diesel", "logs") if p.has_auto(item)),
        "carried": int(carried), "waiting": int(waiting), "cargo": int(cargo),
        "units": units.visible(match, [(p.x, p.y)], VIEW),
    }


def spectator(match):
    return {"units": units.visible(match, [(p.x, p.y) for p in match.players.values()], VIEW)}
