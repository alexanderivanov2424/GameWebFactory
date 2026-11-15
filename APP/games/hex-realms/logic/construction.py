"""Hex Realms: construction sites. Structures cost hammers (🔨) that idle people build.

A build order that resolves becomes a site (m.sites, cells in m.cell_site). A site holds its cells
but does nothing (no work, housing, storage, territory, sight, score or hits) until finished.

    start(m, pid, b)                 a resolved build order becomes a site
    left(site)                       hammers still needed
    plan(m, pid, idle)               ([(site, n)], idle left): hammers per site this turn, oldest first
    forecast(m, pid, orders=True)    {"builders", "works": {site: n}, "orders": {build order: n}} for the planning screen
    progress(m, pid, idle, events)   sites get hammers; finished ones become structures
    remove(m, cid)                   take a site off the map (demolish refunds its cost)

Rules: a structure costs `hammers` (content, default 1). Each idle person (no job: staffing fills
jobs first) builds 1 hammer a turn; sites are served oldest first, then this turn's build orders in
placement order (they take builders as soon as placed). Work happens at the end of resolution with
the people idle after production; a finished structure works from the next turn. A site with an
enemy unit on any of its cells gets no work and doesn't finish until it leaves.
"""

from .content import STRUCTURES
from . import economy


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


def left(site):
    return max(0, STRUCTURES[site["type"]]["hammers"] - site["done"])


def finished(site):
    return left(site) == 0


def plan(m, pid, idle):
    out = []
    for site in sorted((x for x in m.sites.values() if x["owner"] == pid), key=lambda x: x["n"]):
        n = 0 if blocked(m, site) else min(max(idle, 0), left(site))
        idle -= n
        out.append((site, n))
    return out, idle


def forecast(m, pid, orders=True):
    sites, idle = plan(m, pid, economy.staffing(m, pid)[1])
    works = {site["id"]: n for site, n in sites if n}
    placed = {}
    for b in m.orders[pid]["builds"] if orders else ():
        n = min(max(idle, 0), STRUCTURES[b["type"]]["hammers"])
        if n:
            placed[b["id"]] = n
            idle -= n
    return {"builders": sum(works.values()) + sum(placed.values()), "works": works, "orders": placed}


def blocked(m, site):
    return any(c in m.unit_at and m.units[m.unit_at[c]]["owner"] != site["owner"] for c in site["cells"])


def progress(m, pid, idle, events):
    for site, n in plan(m, pid, idle)[0]:
        site["done"] += n
        if finished(site) and not blocked(m, site):
            remove(m, site["id"])
            m.add_structure(pid, site["type"], site["at"], site["rot"])
            events.append({"t": "built", "owner": pid, "type": site["type"], "at": site["at"]})
