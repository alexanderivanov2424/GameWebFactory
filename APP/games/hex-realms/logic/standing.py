"""Hex Realms: standing orders, kept across turns until the player gives the unit another order.

A unit's standing order is u["auto"] (one of MODES; travel also keeps u["goal"]). It survives the
per-turn order reset: as each turn's planning starts, plan_all gives every such unit this turn's
order (Match.resolve), as its owner sees the map (fog). Any other order for the unit
(orders.clear_unit) ends it.

    MODES                   explore, fight, pillage (orders.auto toggles them) and travel
                            (orders.move to a cell out of this turn's reach)
    start(m, uid, mode, goal=None)   set the mode and plan this turn; False (and nothing set) when
                            there's nothing to do (nothing left to explore, no known way there)
    plan(m, uid)            this turn's order for the unit's mode; False when the mode is over
    plan_all(m)             every unit with a standing order; ended ones are dropped
    stop(u)                 drop the unit's standing order

Modes:
    explore   walk to clear the fog (explore.target); ends when nothing is left to explore
    travel    walk toward u["goal"] along movement.route, as far as this turn's movement allows;
              ends on arrival (or next to the goal when one of your units stands on it), or when no
              known way is left
    fight     the nearest enemy unit its owner sees: ranged units shoot the nearest one in range;
              otherwise walk toward the one cheapest to get to (moving into it attacks; ranged
              units stop once it is in range); hold
              (+1 defence die) when none is seen or none can be reached
    pillage   the same against the nearest seen enemy structure that can take hits (moving into
              it is a siege); while a seen enemy unit is within ALERT cells it fights that unit
              instead, then goes back to pillaging
"""

from gamekit.hexes import dist

from . import explore, movement, orders, vision
from .content import STRUCTURES, UNITS

MODES = ("explore", "fight", "pillage", "travel")
ALERT = 3  # pillagers fight enemy units this close (hex distance) first


def stop(u):
    u.pop("auto", None)
    u.pop("goal", None)


def start(m, uid, mode, goal=None):
    u = m.units[uid]
    u["auto"] = mode
    if goal is not None:
        u["goal"] = goal
    if plan(m, uid):
        return True
    stop(u)
    return False


def plan_all(m):
    for uid, u in sorted(m.units.items()):
        if u.get("auto") and m.result is None and not plan(m, uid):
            stop(u)


def plan(m, uid):
    u = m.units[uid]
    mode = u.get("auto")
    orders.clear_unit(m, u["owner"], uid, keep_auto=True)
    if mode == "explore":
        return walk(m, uid, explore.target(m, uid))
    if mode == "travel":
        return travel(m, uid)
    if mode == "pillage":
        near = [k for k in enemy_units(m, u) if dist(k, u["at"]) <= ALERT]
        attack(m, uid, near or enemy_structures(m, u))
        return True
    if mode == "fight":
        attack(m, uid, enemy_units(m, u))
        return True
    return False


def walk(m, uid, goal):
    """Move this turn to `goal` (a cell in reach)."""
    p = goal and movement.path(m, uid, goal)
    if not p:
        return False
    m.orders[m.units[uid]["owner"]]["moves"][uid] = p
    return True


def travel(m, uid):
    u = m.units[uid]
    goal = u.get("goal")
    friend = m.unit_at.get(goal)
    if goal is None or u["at"] == goal or (friend is not None and m.units[friend]["owner"] == u["owner"]
                                            and dist(u["at"], goal) <= 1):
        return False
    keys = movement.route(m, uid, [goal])
    step = keys and movement.this_turn(m, uid, keys)
    if not step:
        return False
    m.orders[u["owner"]]["moves"][uid] = step
    return True


def enemy_units(m, u):
    """Cells of the enemy units u's owner sees right now."""
    pid = u["owner"]
    return [x["at"] for x in m.units.values() if x["owner"] != pid and vision.sees(m, pid, x["at"])]


def enemy_structures(m, u):
    """Cells of the enemy structures (that can take hits) u's owner sees right now."""
    pid = u["owner"]
    return [c for s in m.structures.values() if s["owner"] != pid and STRUCTURES[s["type"]]["hp"]
            for c in s["cells"] if vision.sees(m, pid, c)]


def attack(m, uid, targets):
    """Shoot the nearest target in range (ranged units), else head for the cheapest one to get to;
    hold when there's none or no way to any."""
    u = m.units[uid]
    o = m.orders[u["owner"]]
    rng = UNITS[u["type"]]["range"]
    in_range = sorted((k for k in targets if dist(k, u["at"]) <= rng), key=lambda k: (dist(k, u["at"]), k))
    if rng and in_range:
        o["shots"][uid] = in_range[0]
        return
    keys = movement.route(m, uid, targets) if targets else None
    step = keys and movement.this_turn(m, uid, keys)
    if step and rng:  # stop where it can shoot from next turn
        near = [i for i, k in enumerate(step) if dist(k, keys[-1]) <= rng]
        step = step[:near[0] + 1] if near else step
    if step:
        o["moves"][uid] = step
    else:
        o["holds"].append(uid)
