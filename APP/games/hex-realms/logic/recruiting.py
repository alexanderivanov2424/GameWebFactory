"""Hex Realms: where recruited units appear.

    spawn_cell(m, pid, s, utype)  free cell for a new unit: the structure's cells, then beside it
                                  (naval units need water)
    resolve(m, events)            this turn's recruit orders appear, or fail (refunded, people back)
"""

from gamekit.hexes import neighbors

from . import movement, orders
from .content import TERRAIN, UNITS


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
            m.add_unit(pid, r["type"], spot)
            events.append({"t": "recruited", "owner": pid, "type": r["type"], "at": spot})

