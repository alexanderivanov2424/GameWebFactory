"""Buildings: placement rules, construction sites, finished buildings and the cell layers they use.

A Building starts as a site (built False): colonists deliver its cost (supply chores), then build
it (build chores add work until progress reaches 1). Finished buildings run their behaviour in
machines.py (by their def's "kind"). Three layers per cell: "main" (most buildings), "pipe"
(liquid pipes) and "wire" (wires); a pipe and a wire can share a cell with a main building.

Building fields:
    id ("b12"), type (buildings/<type>.json id), d (its def), x, y (top-left), by (player id who
    placed it), prio (1-9, higher first), built, progress (0..1 of build or deconstruct work),
    delivered {element: kg} (construction materials received), reserved {key: kg} (on the way),
    enabled (players can switch machines off), deconstruct (marked for removal), decon_by,
    store {element: kg} (inputs it holds / storage contents), powered (networks.py sets it
    every step for power users), status (short text for players), state {kind-specific data,
    e.g. "charge", "growth", "uses", "work", "operator"}.
Methods: cells(), port_cell(key) (x, y or None), bottom_cells(), site_needs(),
supply_needs() and deliver(element, kg, temp) (see their docstrings).

Buildings (the manager, match.buildings):
    can_place(type, x, y) -> reason string or None
    place(type, x, y, by, prio=5, built=False) -> Building (raises LobbyError when it can't)
    complete(b)   a site becomes a building (world flags, fluids pushed out of solid tiles)
    remove(b)     drops its materials and contents as debris and takes it off the map
    at(x, y, layer="main") -> Building or None
    version       goes up whenever buildings appear/disappear/finish (nav, decor, networks
                  rebuild their caches when it changes)
"""

from gamekit import LobbyError

from . import content

MAX_PRIO = 9


class Building:
    def __init__(self, bid, btype, x, y, by, prio):
        self.id = bid
        self.type = btype
        self.d = content.BUILDINGS[btype]
        self.x, self.y = x, y
        self.by = by
        self.prio = prio
        self.built = False
        self.progress = 0.0
        self.delivered = {}
        self.reserved = {}
        self.enabled = True
        self.deconstruct = False
        self.decon_by = ""
        self.store = {}
        self.powered = False
        self.status = ""
        self.state = {}

    @property
    def layer(self):
        return self.d["layer"]

    def cells(self):
        return [(self.x + dx, self.y + dy) for dy in range(self.d["h"]) for dx in range(self.d["w"])]

    def bottom_cells(self):
        y = self.y + self.d["h"] - 1
        return [(self.x + dx, y) for dx in range(self.d["w"])]

    def port_cell(self, key):
        """(x, y) of a port ("powerPort", "pipeIn", "pipeOut"), or None if it has none."""
        off = self.d.get(key)
        return None if off is None else (self.x + off[0], self.y + off[1])

    def stored(self, key=None):
        """kg held in store, of one element/class key or of everything."""
        return sum(kg for el, kg in self.store.items() if key is None or content.matches(el, key))

    def site_needs(self):
        """Construction materials still to bring: {cost key: kg} (minus deliveries and reservations)."""
        if self.built:
            return {}
        out = {}
        for key, kg in self.d["cost"].items():
            have = sum(v for el, v in self.delivered.items() if content.matches(el, key))
            left = kg - have - self.reserved.get(key, 0.0)
            if left > 0.01:
                out[key] = left
        return out

    def materials_ready(self):
        if self.built:
            return True
        for key, kg in self.d["cost"].items():
            if sum(v for el, v in self.delivered.items() if content.matches(el, key)) < kg - 0.01:
                return False
        return True

    def supply_needs(self):
        """Inputs a finished, enabled machine wants topped up: {accepts key: kg} (minus reservations).
        Asks only once it has dropped below half its capacity, so colonists bring big loads."""
        if not self.built or not self.enabled or self.deconstruct:
            return {}
        out = {}
        for key, cap in self.d["accepts"].items():
            have = self.stored(key) + self.reserved.get(key, 0.0)
            if have < cap / 2:
                out[key] = cap - have
        return out

    def deliver(self, element, kg):
        """Materials arrive: construction materials for a site, inputs/contents for a building."""
        target = self.store if self.built else self.delivered
        target[element] = target.get(element, 0.0) + kg

    def reserve(self, key, kg):
        self.reserved[key] = self.reserved.get(key, 0.0) + kg

    def unreserve(self, key, kg):
        left = self.reserved.get(key, 0.0) - kg
        if left > 0.01:
            self.reserved[key] = left
        else:
            self.reserved.pop(key, None)


class Buildings:
    def __init__(self, world, items):
        self.world = world
        self.items = items
        self.by_id = {}
        self.layers = {layer: {} for layer in content.LAYERS}  # layer -> {cell index: building id}
        self.version = 0
        self._next = 1

    def __iter__(self):
        return iter(list(self.by_id.values()))

    def get(self, bid):
        return self.by_id.get(bid)

    def at(self, x, y, layer="main"):
        if not self.world.inside(x, y):
            return None
        bid = self.layers[layer].get(self.world.idx(x, y))
        return self.by_id.get(bid) if bid else None

    def of_kind(self, *kinds, built=True):
        return [b for b in self.by_id.values() if b.d["kind"] in kinds and (b.built or not built)]

    # --- placement ------------------------------------------------------------------------

    def can_place(self, btype, x, y):
        d = content.BUILDINGS.get(btype)
        if d is None or not d["buildable"]:
            return "Unknown building."
        world = self.world
        layer = d["layer"]
        for dy in range(d["h"]):
            for dx in range(d["w"]):
                cx, cy = x + dx, y + dy
                if not world.inside(cx, cy) or cx == 0 or cy == 0 or cx == world.w - 1 or cy == world.h - 1:
                    return "Outside the map."
                i = world.idx(cx, cy)
                if world.is_solid(i):
                    return "Dig out the rock first."
                if i in self.layers[layer]:
                    return "Something is already there."
                if layer == "main" and d["solid"] and world.tile[i]:
                    return "Something is already there."
        if d["floor"]:
            fy = y + d["h"]
            for dx in range(d["w"]):
                if not world.inside(x + dx, fy):
                    return "Needs solid ground under it."
                j = world.idx(x + dx, fy)
                if not (world.is_solid(j) or world.tile[j]):
                    return "Needs solid ground under it."
        return None

    def place(self, btype, x, y, by, prio=5, built=False):
        reason = self.can_place(btype, x, y) if not built else None
        if reason:
            raise LobbyError(reason)
        b = Building(f"b{self._next}", btype, x, y, by, prio)
        self._next += 1
        self.by_id[b.id] = b
        for cx, cy in b.cells():
            self.layers[b.layer][self.world.idx(cx, cy)] = b.id
        if built:
            self.complete(b)
        self.version += 1
        return b

    def complete(self, b):
        b.built = True
        b.progress = 0.0
        b.status = ""
        world = self.world
        for cx, cy in b.cells():
            i = world.idx(cx, cy)
            if b.d["ladder"]:
                world.ladder[i] = True
            if b.d["solid"] and b.layer == "main":
                if not world.is_vacuum(i) and not world.is_solid(i):
                    eid, kg, temp, germs = world.element_id(i), world.mass[i], world.temp[i], world.germs[i]
                    world.set_cell(i, "vacuum", 0, temp)
                    world.tile[i] = True
                    for j in world.nbrs[i]:
                        jx, jy = world.xy(j)
                        if world.emit(jx, jy, eid, kg, temp, germs):
                            break
                world.tile[i] = True
                world.door[i] = b.d["door"]
                world.insul[i] = b.d["insulated"]
        self.version += 1

    def remove(self, b, refund=True):
        """Take a building or site off the map; its materials and contents drop as debris."""
        world = self.world
        for cx, cy in b.cells():
            i = world.idx(cx, cy)
            if self.layers[b.layer].get(i) == b.id:
                del self.layers[b.layer][i]
            if b.built:
                if b.d["ladder"]:
                    world.ladder[i] = False
                if b.d["solid"] and b.layer == "main":
                    world.tile[i] = world.door[i] = world.insul[i] = False
        drop_x, drop_y = b.bottom_cells()[0]
        if refund:
            for el, kg in list(b.delivered.items()) + list(b.store.items()):
                if kg > 0.01:
                    self.items.add(el, kg, drop_x, drop_y, world.temp[world.idx(drop_x, drop_y)])
        self.by_id.pop(b.id, None)
        self.version += 1
