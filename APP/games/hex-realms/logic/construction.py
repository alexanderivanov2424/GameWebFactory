"""Hex Realms: construction sites. Structures take time and builders.

A build order that resolves becomes a site (m.sites, cells in m.cell_site), not a structure yet. A
site holds its cells (nothing else can be built or founded there) but does nothing: it doesn't
work, house, store, carry goods, claim territory, see, count for score or take hits.

    start(m, pid, b)              a resolved build order (orders.build) becomes a site
    plan(m, pid, idle)            [(site, works)] oldest first: which sites get their builders this
                                  turn from `idle` people
    forecast(m, pid)              {"builders": people building this turn, "works": [site ids]}
                                  for the planning screen (idle = economy.staffing's idle people)
    progress(m, pid, idle, ev)    sites that get their builders advance one turn; finished ones
                                  become structures; people still idle lay roads (roads.lay)
    remove(m, cid)                take a site off the map (orders.demolish refunds its cost)

Rules: a structure needs `buildTurns` turns of work (content, default 1), and every turn of work
needs `builders` idle people (default 1), people without a job (economy.staffing: jobs are filled
first, so switch structures off or demolish them to free builders). Sites are served oldest first;
one that can't get all its builders waits this turn, and a later site that needs fewer may still
get them. Each idle person works on one site a turn, so you build only as much as you have people
for. Work happens at the end of resolution with the people idle this turn (after production), so a
1-turn Hut ordered now stands next turn and a finished structure starts working the turn after. A
finished site with an enemy unit on it waits (without builders) until the unit has gone.
"""

from .content import STRUCTURES
from . import economy, roads


def start(m, pid, b):
    cid = m.new_id("c")
    m.sites[cid] = {"id": cid, "n": m.counter, "type": b["type"], "owner": pid, "at": b["at"], "rot": b["rot"],
                    "cells": list(b["cells"]), "cost": dict(b["cost"]), "done": 0}
    for c in b["cells"]:
        m.cell_site[c] = cid
    return m.sites[cid]


def remove(m, cid):
    site = m.sites.pop(cid)
    for c in site["cells"]:
        if m.cell_site.get(c) == cid:
            del m.cell_site[c]
    return site


def finished(site):
    return site["done"] >= STRUCTURES[site["type"]]["buildTurns"]


def plan(m, pid, idle):
    out = []
    for site in sorted((x for x in m.sites.values() if x["owner"] == pid), key=lambda x: x["n"]):
        need = STRUCTURES[site["type"]]["builders"]
        works = not finished(site) and need <= idle
        if works:
            idle -= need
        out.append((site, works))
    return out


def forecast(m, pid):
    idle = economy.staffing(m, pid)[1]
    works = [site["id"] for site, ok in plan(m, pid, idle) if ok]
    return {"builders": sum(STRUCTURES[m.sites[c]["type"]]["builders"] for c in works), "works": works}


def blocked(m, site):
    return any(c in m.unit_at and m.units[m.unit_at[c]]["owner"] != site["owner"] for c in site["cells"])


def progress(m, pid, idle, events):
    for site, works in plan(m, pid, idle):
        if works:
            site["done"] += 1
            idle -= STRUCTURES[site["type"]]["builders"]
        if finished(site) and not blocked(m, site):
            remove(m, site["id"])
            m.add_structure(pid, site["type"], site["at"], site["rot"])
            events.append({"t": "built", "owner": pid, "type": site["type"], "at": site["at"]})
    roads.lay(m, pid, idle, events)
