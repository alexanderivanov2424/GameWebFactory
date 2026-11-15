"""Hex Realms: fog of war: what each player sees, has explored and remembers, and their map view.

    update(m)              recompute visible / explored / memory for every player
    sees(m, pid, k)        pid sees cell k now
    known_at(m, pid)       {key: (owner, type)} of structures pid knows (own + remembered)
    view(m, pid, staffed)  the map part of pid's state (pid None = everything)
"""

from gamekit.hexes import disk, parse

from .content import STRUCTURES, UNITS


def sight(m, pid):
    out = set()
    for u in m.units.values():
        if u["owner"] == pid:
            out.update(disk(UNITS[u["type"]]["vision"], parse(u["at"])))
    for s in m.structures.values():
        if s["owner"] == pid:
            radius = STRUCTURES[s["type"]]["vision"]
            for c in s["cells"]:
                out.update(disk(radius, parse(c)))
    return out & m.cells.keys()


def snapshot(m, s, working=True):
    return {"type": s["type"], "owner": s["owner"], "at": s["at"], "cells": s["cells"], "hp": s["hp"],
            "maxHp": STRUCTURES[s["type"]]["hp"], "working": working, "active": s["active"]}


def sees_all(m, pid):
    return pid is None or not m.fog or pid not in m.players or not m.players[pid]["alive"] or m.result is not None


def update(m):
    for pid in m.seats:
        if sees_all(m, pid):
            m.visible[pid] = set(m.cells)
            m.explored[pid] = set(m.cells)
            continue
        vis = sight(m, pid)
        m.visible[pid] = vis
        m.explored[pid] |= vis
        mem = m.memory[pid]
        for sid in list(mem):
            if sid not in m.structures and any(c in vis for c in mem[sid]["cells"]):
                del mem[sid]
        for sid, s in m.structures.items():
            if s["owner"] != pid and any(c in vis for c in s["cells"]):
                mem[sid] = snapshot(m, s)


def sees(m, pid, k):
    return sees_all(m, pid) or k in m.visible.get(pid, ())


def known_at(m, pid):
    out = {}
    if sees_all(m, pid):
        for c, sid in m.cell_structure.items():
            out[c] = (m.structures[sid]["owner"], m.structures[sid]["type"])
        return out
    for s in m.structures.values():
        if s["owner"] == pid:
            for c in s["cells"]:
                out[c] = (pid, s["type"])
    for s in m.memory[pid].values():
        for c in s["cells"]:
            out.setdefault(c, (s["owner"], s["type"]))
    return out


def event_cells(e):
    cells = [e.get("at")] + list(e.get("cells", []))
    for k in ("a", "b"):
        if isinstance(e.get(k), dict):
            cells.append(e[k].get("at"))
    return [c for c in cells if c]


def _sites(m, keep):
    return {cid: {"type": x["type"], "owner": x["owner"], "at": x["at"], "cells": x["cells"], "done": x["done"],
                  "hammers": STRUCTURES[x["type"]]["hammers"]}
            for cid, x in m.sites.items() if keep(x)}


def view(m, pid, staffed):
    structures = {sid: snapshot(m, s, sid in staffed) for sid, s in m.structures.items()}
    if sees_all(m, pid):
        return {"cells": m.cells, "dim": [], "structures": structures, "units": _units(m, lambda u: True),
                "sites": _sites(m, lambda x: True),
                "territory": m.territory, "claims": m.claims, "events": {str(i): e for i, e in enumerate(m.events)}}
    explored, vis = m.explored[pid], m.visible[pid]
    before = m.vis_before.get(pid, set())
    shown = {sid: s for sid, s in structures.items() if s["owner"] == pid}
    for sid, s in m.memory[pid].items():
        shown.setdefault(sid, s)
    events = [e for e in m.events if e.get("owner") == pid or e["t"] == "eliminated"
              or any(c in vis or c in before for c in event_cells(e))]
    return {
        "cells": {k: t for k, t in m.cells.items() if k in explored},
        "dim": sorted(explored - vis),
        "structures": shown,
        "units": _units(m, lambda u: u["owner"] == pid or u["at"] in vis),
        "sites": _sites(m, lambda x: x["owner"] == pid or any(c in vis for c in x["cells"])),
        "territory": {k: p for k, p in m.territory.items() if k in explored},
        "claims": {k: p for k, p in m.claims.items() if k in explored},
        "events": {str(i): e for i, e in enumerate(events)},
    }


def _units(m, keep):
    return {uid: {"type": u["type"], "owner": u["owner"], "at": u["at"], "hp": u["hp"], "maxHp": UNITS[u["type"]]["hp"]}
            for uid, u in m.units.items() if keep(u)}
