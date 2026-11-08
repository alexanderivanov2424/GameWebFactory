"""Buildings: placement rules, construction sites, finished buildings and the cell layers they use.

A Building starts as a site (built False): colonists deliver its cost (supply chores), then build
it (build chores add work until progress reaches 1). Finished buildings run their behaviour in
machines.py (by their def's "kind"). Three layers per cell: "main" (most buildings), "pipe"
(liquid pipes) and "wire" (wires); a pipe and a wire can share a cell with a main building.

Rotation: rot 0-3 (quarter turns clockwise; only defs with "rotatable"). x, y is the top-left of
the rotated footprint; b.w, b.h its rotated size; cells(), bottom_cells() and port_cell() apply
the rotation (use them, never d["w"]/d["h"] for a placed building).

Building fields:
    id ("b12"), type (buildings/<type>.json id), d (its def), x, y (top-left), rot, by (player id who
    placed it), prio (1-9, higher first), built, progress (0..1 of build or deconstruct work),
    delivered {element: kg} (construction materials received), reserved {key: kg} (on the way),
    enabled (players can switch machines off), deconstruct (marked for removal), decon_by,
    store {element: kg} (inputs it holds / storage contents), store_temp {element: °C} (mass-
    averaged on every deliver), germs (germs on the structure itself: containers pass a share to
    whatever is taken out; colonists who touch it pick some up — germs.py), filter (storage
    kinds: list of accepted element ids, or None = everything), powered (networks.py sets it
    every step for power users), status (short text for players), state {kind-specific data,
    e.g. "charge", "growth", "uses", "work", "operator"}.
Methods: cells(), port_cell(key) (x, y or None), bottom_cells(), site_needs(),
supply_needs(), deliver(element, kg, temp, germs), take(element, kg) -> (kg, temp, germs),
accepts_element(el) (filter check) (see their docstrings).

Buildings (the manager, match.buildings):
    can_place(type, x, y, rot=0) -> reason string or None
    place(type, x, y, by, prio=5, built=False, rot=0) -> Building (raises LobbyError when it can't)
    complete(b)   a site becomes a building (world flags; fluids in solid tiles are pushed out
                  with world.release, so no mass is lost)
    remove(b)     drops its materials and contents as debris and takes it off the map
    at(x, y, layer="main") -> Building or None
    version       goes up whenever buildings appear/disappear/finish (nav, decor, networks
                  rebuild their caches when it changes)
"""

from gamekit import LobbyError

from . import content

MAX_PRIO = 9


def footprint(d, rot):
    """(w, h, [(dx, dy) offsets of the unrotated cells after rotating]) for a def and rotation."""
    w, h = d["w"], d["h"]
    cells = [(dx, dy) for dy in range(h) for dx in range(w)]
    for _ in range(rot % 4):
        cells = [(h - 1 - dy, dx) for dx, dy in cells]
        w, h = h, w
    return w, h, cells


def rotate_offset(d, rot, off):
    """An unrotated [dx, dy] offset (port) after rot quarter turns clockwise."""
    w, h = d["w"], d["h"]
    dx, dy = off
    for _ in range(rot % 4):
        dx, dy = h - 1 - dy, dx
        w, h = h, w
    return dx, dy


class Building:
    def __init__(self, bid, btype, x, y, by, prio, rot=0):
        self.id = bid
        self.type = btype
        self.d = content.BUILDINGS[btype]
        self.x, self.y = x, y
        self.rot = rot % 4
        self.w, self.h, self._offsets = footprint(self.d, self.rot)
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
        self.store_temp = {}
        self.germs = 0.0
        self.filter = None
        self.powered = False
        self.status = ""
        self.state = {}

    @property
    def layer(self):
        return self.d["layer"]

    def cells(self):
        return [(self.x + dx, self.y + dy) for dx, dy in self._offsets]

    def bottom_cells(self):
        y = self.y + self.h - 1
        return [(self.x + dx, y) for dx in range(self.w)]

    def port_cell(self, key):
        """(x, y) of a port (content.PORTS: powerPort, pipeIn, pipeOut, gasIn, gasOut) or None."""
        off = self.d.get(key)
        if off is None:
            return None
        dx, dy = rotate_offset(self.d, self.rot, off)
        return self.x + dx, self.y + dy

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

    def deliver(self, element, kg, temp=20.0, germs=0.0):
        """Materials arrive: construction materials for a site, inputs/contents for a building.
        Temperature is averaged by mass per element; germs settle on the structure."""
        target = self.store if self.built else self.delivered
        have = target.get(element, 0.0)
        total = have + kg
        if total > 0:
            old = self.store_temp.get(element, temp)
            self.store_temp[element] = (old * have + temp * kg) / total
        target[element] = total
        self.germs += max(0.0, germs)

    def take(self, element, kg):
        """Take up to kg of an element out of store. Returns (kg, temp, germs): the germs are
        the share of the structure's germs that leave with it (kg over everything stored)."""
        have = self.store.get(element, 0.0)
        got = min(kg, have)
        if got <= 0:
            return 0.0, 20.0, 0.0
        total = self.stored()
        germs = self.germs * (got / total) if total > 0 else 0.0
        self.germs -= germs
        left = have - got
        temp = self.store_temp.get(element, 20.0)
        if left > 1e-6:
            self.store[element] = left
        else:
            self.store.pop(element, None)
            self.store_temp.pop(element, None)
        return got, temp, germs

    def accepts_element(self, element):
        """Storage filter: whether players allowed this element into this building."""
        return self.filter is None or element in self.filter

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

    def can_place(self, btype, x, y, rot=0):
        d = content.BUILDINGS.get(btype)
        if d is None or not d["buildable"]:
            return "Unknown building."
        if rot % 4 and not d["rotatable"]:
            return "That building can't be turned."
        world = self.world
        layer = d["layer"]
        w, h, offsets = footprint(d, rot)
        for dx, dy in offsets:
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
            fy = y + h
            for dx in range(w):
                if not world.inside(x + dx, fy):
                    return "Needs solid ground under it."
                j = world.idx(x + dx, fy)
                if not (world.is_solid(j) or world.tile[j]):
                    return "Needs solid ground under it."
        return None

    def place(self, btype, x, y, by, prio=5, built=False, rot=0):
        reason = self.can_place(btype, x, y, rot) if not built else None
        if reason:
            raise LobbyError(reason)
        b = Building(f"b{self._next}", btype, x, y, by, prio, rot)
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
                    world.release(cx, cy, eid, kg, temp, germs)
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
            here = world.temp[world.idx(drop_x, drop_y)]
            parts = [(el, kg) for el, kg in list(b.delivered.items()) + list(b.store.items()) if kg > 0.01]
            total = sum(kg for _, kg in parts) or 1.0
            for el, kg in parts:
                self.items.add(el, kg, drop_x, drop_y, b.store_temp.get(el, here), b.germs * kg / total)
        self.by_id.pop(b.id, None)
        self.version += 1
