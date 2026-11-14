"""Hex Realms: where recruited units appear, and structures that recruit on their own.

    spawn_cell(m, pid, s, utype)   the cell a new unit appears on: the structure itself (its anchor,
                                   then its other cells), else a cell next to it (naval units need
                                   water, so they appear beside their Shipyard); None if all are taken
    resolve(m, events)             this turn's recruit orders appear (or fail: refunded, people back);
                                   a unit trained at a structure with an auto order gets that standing order
    can_auto(stype)                structures that can recruit on their own: every one that trains units
                                   except the Town Hall
    set_auto(m, pid, sid, kind, order)  the "autorecruit" message: kind (a unit type it trains, or None =
                                   off) and order (a standing.MODES order for every unit trained there:
                                   explore / fight / pillage, or None). Takes effect at once: this turn's
                                   automatic order is replaced
    plan(m)                        as planning starts (and on set_auto): every structure with an auto kind
                                   orders one unit (an ordinary recruit order, paid now, cancellable) when
                                   it could be recruited by hand and the realm has enough people without a
                                   job for it (so jobs never empty); otherwise it skips the turn

State on each structure: s["autoRecruit"] (unit type or None), s["autoOrder"] (mode or None); private
(Match.private's "autoRecruit"). Automatic orders carry "auto": True.
"""

from gamekit import LobbyError
from gamekit.hexes import neighbors

from . import movement, orders
from .content import STRUCTURES, TERRAIN, TOWN_HALL, UNITS
from .economy import staffing

AUTO_ORDERS = ("explore", "fight", "pillage")


def spawn_cell(m, pid, s, utype):
    naval = UNITS[utype]["naval"]
    around = sorted({n for c in s["cells"] for n in neighbors(c)} - set(s["cells"]))
    for k in [*s["cells"], *around]:
        if k not in m.cells or k in m.unit_at or movement.enemy_structure(m, pid, k):
            continue
        if (m.cells[k] == "water") if naval else TERRAIN[m.cells[k]]["move"] is not None:
            return k
    return None


def resolve(m, events):
    for pid in m.alive():
        for r in m.orders[pid]["recruits"]:
            s = m.structures.get(r["at"])
            spot = spawn_cell(m, pid, s, r["type"]) if s and s["owner"] == pid else None
            if spot is None:
                orders.refund(m, pid, r["cost"])
                m.players[pid]["pop"] += r["people"]
                events.append({"t": "failed", "owner": pid, "what": r["type"], "at": s["at"] if s else None,
                               "why": "No room to place it."})
                continue
            uid = m.add_unit(pid, r["type"], spot)
            events.append({"t": "recruited", "owner": pid, "type": r["type"], "at": spot})
            mode = s.get("autoOrder")
            if mode and uid in m.units and not UNITS[r["type"]]["settler"] and (mode != "explore" or m.fog):
                m.units[uid]["auto"] = mode  # standing.plan_all plans it as the next turn starts


def can_auto(stype):
    return bool(STRUCTURES[stype]["recruits"]) and stype != TOWN_HALL


def set_auto(m, pid, sid, kind, order):
    s = orders.own_structure(m, pid, sid)
    if not can_auto(s["type"]):
        raise LobbyError("Only military structures recruit on their own.")
    if kind is not None and kind not in STRUCTURES[s["type"]]["recruits"]:
        raise LobbyError(f"{STRUCTURES[s['type']]['name']} can't train that.")
    if order is not None and order not in AUTO_ORDERS:
        raise LobbyError("Unknown order.")
    if order == "explore" and not m.fog:
        raise LobbyError("There's no fog of war to clear.")
    s["autoRecruit"], s["autoOrder"] = kind, order
    for r in [r for r in m.orders[pid]["recruits"] if r["at"] == sid and r.get("auto")]:
        orders.cancel(m, pid, r["id"])
    _plan_one(m, pid, s)


def plan(m):
    for s in sorted(m.structures.values(), key=lambda s: s["n"]):
        if m.players[s["owner"]]["alive"]:
            _plan_one(m, s["owner"], s)


def _plan_one(m, pid, s):
    kind = s.get("autoRecruit")
    if not kind or any(r["at"] == s["id"] for r in m.orders[pid]["recruits"]):
        return
    if staffing(m, pid)[1] < UNITS[kind]["people"]:
        return
    try:
        orders.recruit(m, pid, s["id"], kind)
    except LobbyError:
        return
    m.orders[pid]["recruits"][-1]["auto"] = True
