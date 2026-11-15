"""Hex Realms: construction sites. Structures cost hammers (🔨), and idle people make them.

A build order that resolves becomes a site (m.sites, cells in m.cell_site), not a structure yet. A
site holds its cells (nothing else can be built or founded there) but does nothing: it doesn't
work, house, store, carry goods, claim territory, see, count for score or take hits.

    start(m, pid, b)              a resolved build order (orders.build) becomes a site
    left(site)                    hammers still needed
    plan(m, pid, idle)            ([(site, n)], idle left): hammers each of pid's sites gets this turn
                                  from `idle` people, oldest first
    forecast(m, pid, orders=True) {"builders": people building this turn, "works": {site id: n},
                                  "orders": {build order id: n}} for the planning screen (idle =
                                  economy.staffing's idle people): sites first, then this turn's build
                                  orders, which take their builders as soon as they're placed
    progress(m, pid, idle, ev)    sites get their hammers; finished ones become structures
    remove(m, cid)                take a site off the map (orders.demolish refunds its cost)

Rules (2026-11-15, the user's): a structure costs `hammers` (content, default 1) besides its goods.
Every idle person (no job: economy.staffing fills jobs first, so switch structures off or demolish
them to free people) builds 1 hammer a turn on one site: sites are served oldest first, each taking
as many idle people as it still needs hammers, then this turn's build orders in the order they were
placed (they take their builders as soon as they're placed; with nobody idle they just wait). So a
3-hammer structure with 3 idle people is built in one turn. Work happens at the end of resolution
with the people idle this turn (after production), and a finished structure starts working the turn
after. A site with an enemy unit on any of its cells gets no work (its builders go to other sites)
and doesn't finish until the unit has gone.
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
