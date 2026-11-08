"""Items: loose debris on the floor (dug rock, harvested food, dropped loads).

Item fields: id ("i5"), el (element id), kg, x, y (cell), temp, germs, reserved (kg a colonist
has claimed to pick up). Items of the same element on the same cell merge.

Items (the manager, match.items):
    add(el, kg, x, y, temp=20, germs=0) -> Item   (merges into an existing pile)
    take(item, kg) -> (el, kg, temp, germs)       removes up to kg (the item goes when empty)
    remove(item)
    at(x, y) -> list of items on that cell
    available(item) -> kg not reserved
    settle(world)   piles in mid-air fall to the floor; piles inside a solid cell move up
    totals() -> {el: kg} of all debris
    version         goes up when piles appear or disappear (decor recompute)
"""

ITEM_MIN = 0.01


class Item:
    __slots__ = ("id", "el", "kg", "x", "y", "temp", "germs", "reserved")

    def __init__(self, iid, el, kg, x, y, temp, germs):
        self.id, self.el, self.kg, self.x, self.y = iid, el, kg, x, y
        self.temp, self.germs, self.reserved = temp, germs, 0.0


class Items:
    def __init__(self):
        self.by_id = {}
        self._next = 1
        self.version = 0

    def __iter__(self):
        return iter(list(self.by_id.values()))

    def get(self, iid):
        return self.by_id.get(iid)

    def at(self, x, y):
        return [it for it in self.by_id.values() if it.x == x and it.y == y]

    def available(self, item):
        return max(0.0, item.kg - item.reserved)

    def add(self, el, kg, x, y, temp=20.0, germs=0.0):
        if kg < ITEM_MIN:
            return None
        for it in self.by_id.values():
            if it.el == el and it.x == x and it.y == y:
                total = it.kg + kg
                it.temp = (it.temp * it.kg + temp * kg) / total
                it.kg = total
                it.germs += germs
                return it
        it = Item(f"i{self._next}", el, float(kg), x, y, float(temp), float(germs))
        self._next += 1
        self.by_id[it.id] = it
        self.version += 1
        return it

    def take(self, item, kg):
        got = min(kg, item.kg)
        if got <= 0:
            return item.el, 0.0, item.temp, 0.0
        germs = item.germs * got / item.kg if item.kg else 0.0
        item.kg -= got
        item.germs -= germs
        item.reserved = max(0.0, min(item.reserved, item.kg))
        if item.kg < ITEM_MIN:
            self.remove(item)
        return item.el, got, item.temp, germs

    def remove(self, item):
        if self.by_id.pop(item.id, None) is not None:
            self.version += 1

    def totals(self):
        out = {}
        for it in self.by_id.values():
            out[it.el] = out.get(it.el, 0.0) + it.kg
        return out

    def settle(self, world):
        """Debris falls through open cells (not ladders' floors: ladders don't hold debris) and is
        pushed up out of solid cells (e.g. a tile built on it)."""
        for it in list(self.by_id.values()):
            i = world.idx(it.x, it.y)
            moved = False
            while world.blocks_fluid(i) and not world.door[i] and it.y > 0:
                it.y -= 1
                i = world.idx(it.x, it.y)
                moved = True
            while it.y + 1 < world.h and not world.blocks_fluid(world.idx(it.x, it.y + 1)):
                it.y += 1
                moved = True
            if moved:
                for other in self.at(it.x, it.y):
                    if other is not it and other.el == it.el:
                        other.temp = (other.temp * other.kg + it.temp * it.kg) / (other.kg + it.kg)
                        other.kg += it.kg
                        other.germs += it.germs
                        self.remove(it)
                        break
