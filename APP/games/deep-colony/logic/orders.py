"""Orders: what players ask the colony to do, and finishing that work.

Any player may give any order at any time (paused or not); every order records who gave it
("by", a public id) so everyone sees whose plan it is. Orders are shared by the whole colony.

    dig(match, pid, cells, prio)          mark diggable solid cells (match.digs)
    build(match, pid, btype, cells, prio) place sites: one per cell for 1x1 pipe/wire/ladder/tile
                                          drags, else one site at cells[0] (its top-left)
    deconstruct(match, pid, cells)        mark buildings/sites touching the cells for removal
                                          (sites that haven't started are removed at once)
    cancel(match, pid, cells)             remove dig marks, unstarted sites, deconstruct marks
    set_priority(match, pid, cells, prio) re-prioritize dig marks and buildings there
    toggle(match, pid, bid)               switch a finished machine on/off

match.digs: {cell index: {"by", "prio", "progress" (0..1), "claimed" (colonist id or "")}}.
Work done by colonists (chores.py) ends in:
    finish_dig(match, i)            rock -> debris (DIG_YIELD of its mass) on that cell
    finish_build(match, b)          site -> building
    finish_deconstruct(match, b)    building -> its materials as debris
Each returns nothing; they log nothing (the log is for rarer events).

Limits: MAX_CELLS cells per order message; the server checks shapes and types first.
"""

from gamekit import LobbyError

from . import content

MAX_CELLS = 1600  # a full 40x40 area (server.MAX_RECT)
DIG_YIELD = 0.5      # share of a dug cell's mass that drops as debris
DIG_TIME = 4.0       # s of work per hardness point
DECON_TIME = 0.5     # share of build time it takes to deconstruct


def _check_cells(match, cells):
    if not cells or len(cells) > MAX_CELLS:
        raise LobbyError(f"Choose 1-{MAX_CELLS} cells.")
    world = match.world
    for x, y in cells:
        if not world.inside(x, y):
            raise LobbyError("Outside the map.")


def _prio(prio):
    if type(prio) is not int or not 1 <= prio <= 9:
        raise LobbyError("Priority must be 1-9.")
    return prio


def dig(match, pid, cells, prio=5):
    _check_cells(match, cells)
    _prio(prio)
    world = match.world
    added = 0
    for x, y in cells:
        i = world.idx(x, y)
        e = content.ELEMENTS[world.element_id(i)]
        if e["phase"] == "solid" and e["diggable"] and i not in match.digs:
            match.digs[i] = {"by": pid, "prio": prio, "progress": 0.0, "claimed": ""}
            added += 1
    if not added:
        raise LobbyError("Nothing to dig there.")


def build(match, pid, btype, cells, prio=5):
    _check_cells(match, cells)
    _prio(prio)
    d = content.BUILDINGS.get(btype)
    if d is None or not d["buildable"]:
        raise LobbyError("Unknown building.")
    multi = d["w"] == 1 and d["h"] == 1
    targets = cells if multi else cells[:1]
    placed, reason = 0, None
    for x, y in targets:
        reason = match.buildings.can_place(btype, x, y)
        if reason:
            if not multi:
                raise LobbyError(reason)
            continue
        match.buildings.place(btype, x, y, pid, prio)
        placed += 1
    if not placed:
        raise LobbyError(reason or "Can't build there.")


def _buildings_at(match, cells):
    found = {}
    for x, y in cells:
        for layer in content.LAYERS:
            b = match.buildings.at(x, y, layer)
            if b:
                found[b.id] = b
    return list(found.values())


def _drop_site(match, b):
    """Cancel a site: release reservations and give back what was delivered."""
    match.release_building(b)
    match.buildings.remove(b)


def deconstruct(match, pid, cells):
    _check_cells(match, cells)
    marked = 0
    for b in _buildings_at(match, cells):
        if not b.d["deconstructable"]:
            continue
        if not b.built:
            _drop_site(match, b)
        else:
            b.deconstruct, b.decon_by, b.progress = True, pid, 0.0
        marked += 1
    if not marked:
        raise LobbyError("Nothing to deconstruct there.")


def cancel(match, pid, cells):
    _check_cells(match, cells)
    world = match.world
    for x, y in cells:
        i = world.idx(x, y)
        if i in match.digs:
            match.release_dig(i)
            del match.digs[i]
    for b in _buildings_at(match, cells):
        if not b.built:
            _drop_site(match, b)
        elif b.deconstruct:
            b.deconstruct, b.decon_by, b.progress = False, "", 0.0


def set_priority(match, pid, cells, prio):
    _check_cells(match, cells)
    _prio(prio)
    world = match.world
    for x, y in cells:
        order = match.digs.get(world.idx(x, y))
        if order:
            order["prio"] = prio
    for b in _buildings_at(match, cells):
        b.prio = prio


def toggle(match, pid, bid):
    b = match.buildings.get(bid)
    if b is None or not b.built or b.d["kind"] == "none":
        raise LobbyError("That building can't be switched.")
    b.enabled = not b.enabled


def finish_dig(match, i):
    world = match.world
    order = match.digs.pop(i, None)
    if order is None or not world.is_solid(i):
        return
    eid, kg, temp, germs = world.dig(i)
    x, y = world.xy(i)
    match.items.add(eid, kg * DIG_YIELD, x, y, temp, germs * DIG_YIELD)


def finish_build(match, b):
    match.buildings.complete(b)  # b.delivered is kept: refunded on deconstruct


def finish_deconstruct(match, b):
    match.release_building(b)
    match.buildings.remove(b)
