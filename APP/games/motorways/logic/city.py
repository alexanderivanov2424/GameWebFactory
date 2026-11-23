"""Metro Lanes city: houses and shops appearing over time, shop demand, and the overflow timer.

- Shops are 2x2 buildings in one colour with a driveway (a door tile next to one of their sides).
  They make demand ("pins") over time, faster each week. A car from a house of the same colour
  drives there to take one pin away (traffic.py).
- Houses are 1 tile with a driveway, in one colour, each with CARS_PER_HOUSE cars. They appear
  near shops of their colour until each colour has HOUSES_PER_SHOP houses per shop.
- A new colour unlocks every 2 weeks (up to MAX_COLORS); a new shop appears every SHOP_EVERY
  seconds (scaled by growth), using a colour without a shop first.
- Overflow: while a shop has FULL_PINS or more pins its timer runs; below that it drains
  TIMER_RECOVER times as fast. A full timer (the overflow setting, seconds) loses the game for
  everyone.
Spawn rates are divided by `growth` (host setting x player count factor, see match.py); demand is
scaled by `demand` (the host setting only).
"""

COLORS = ["#e5534b", "#3f8fd8", "#efb320", "#43a96f", "#9566cf", "#ee8538"]
COLOR_NAMES = ["Red", "Blue", "Yellow", "Green", "Purple", "Orange"]
MAX_COLORS = len(COLORS)
CARS_PER_HOUSE = 2
HOUSES_PER_SHOP = 4
HOUSE_EVERY = 7.0        # seconds between new houses at growth 1
SHOP_EVERY = 55.0        # seconds between new shops at growth 1
PIN_EVERY = 9.0          # seconds per pin per shop in week 1
PIN_SPEEDUP = 0.08       # demand grows by this share of week 1's each week
FULL_PINS = 6
MAX_PINS = 12
TIMER_RECOVER = 2.0
SHOP_SPACING = 4         # shops' corners at least this far apart (tiles, either axis)
HOUSE_RADIUS = (2, 6)    # houses appear this far (tiles) from a shop of their colour


class House:
    def __init__(self, hid, color, node, door, side):
        self.id, self.color, self.node, self.door, self.side = hid, color, node, door, side
        self.home = CARS_PER_HOUSE   # cars parked at home


class Shop:
    def __init__(self, sid, color, tiles, node, door, side):
        self.id, self.color, self.tiles, self.node, self.door, self.side = sid, color, tiles, node, door, side
        self.pins = 0
        self.assigned = 0        # cars on their way for a pin
        self.timer = 0.0         # seconds overflowing
        self.clock = 0.5         # pin progress (a pin at 1)


class City:
    def __init__(self, grid, net, rng, growth=1.0, demand=1.0):
        self.grid, self.net, self.rng = grid, net, rng
        self.growth, self.demand = growth, demand
        self.houses = {}
        self.shops = {}
        self._next = 1
        self.house_clock = 0.0
        self.shop_clock = 0.0

    def colors(self, week):
        return min(MAX_COLORS, 1 + week // 2)

    def houses_of(self, color):
        return [h for h in self.houses.values() if h.color == color]

    def shops_of(self, color):
        return [s for s in self.shops.values() if s.color == color]

    # --- growth -----------------------------------------------------------------------

    def start(self):
        """The first shop and two houses of its colour. Returns the new houses."""
        shop = self.spawn_shop(0)
        return [h for h in (self.spawn_house(0, near=shop), self.spawn_house(0, near=shop)) if h]

    def step(self, dt, week, limit):
        """Advance spawning, demand and timers. Returns (new houses, shop that overflowed or None)."""
        new = []
        self.shop_clock += dt * self.growth
        if self.shop_clock >= SHOP_EVERY:
            self.shop_clock -= SHOP_EVERY
            self.spawn_shop(self._shop_color(week))
        self.house_clock += dt * self.growth
        if self.house_clock >= HOUSE_EVERY:
            self.house_clock -= HOUSE_EVERY
            color = self._house_color()
            if color is not None:
                shops = self.shops_of(color)
                house = self.spawn_house(color, near=self.rng.choice(shops))
                if house:
                    new.append(house)
        rate = self.demand * (1 + PIN_SPEEDUP * week) / PIN_EVERY
        lost = None
        for shop in self.shops.values():
            shop.clock += dt * rate
            if shop.clock >= 1:
                shop.clock -= 1
                shop.pins = min(MAX_PINS, shop.pins + 1)
            if shop.pins >= FULL_PINS:
                shop.timer += dt
                if shop.timer >= limit and lost is None:
                    lost = shop
            else:
                shop.timer = max(0.0, shop.timer - dt * TIMER_RECOVER)
        return new, lost

    def _shop_color(self, week):
        unlocked = range(self.colors(week))
        empty = [c for c in unlocked if not self.shops_of(c)]
        if empty:
            return empty[0]
        fewest = min(len(self.shops_of(c)) for c in unlocked)
        return self.rng.choice([c for c in unlocked if len(self.shops_of(c)) == fewest])

    def _house_color(self):
        best, color = 0, None
        for c in sorted({s.color for s in self.shops.values()}):
            deficit = HOUSES_PER_SHOP * len(self.shops_of(c)) - len(self.houses_of(c))
            if deficit > best:
                best, color = deficit, c
        return color

    def _id(self):
        self._next += 1
        return str(self._next - 1)

    # --- placement --------------------------------------------------------------------

    def _door_ok(self, t):
        """A driveway may lead onto free land or an existing road (never water or a building)."""
        g = self.grid
        return t is not None and g.in_area(t) and g.terrain[t] == "." and t not in self.net.blocked

    def _site_ok(self, t):
        return self.grid.in_area(t) and self.net.free_land(t) and t not in self.net.attached

    def _sides(self):
        sides = ["N", "S", "E", "W"]
        self.rng.shuffle(sides)
        return sides

    def spawn_house(self, color, near=None):
        g, rng = self.grid, self.rng
        for attempt in range(120):
            if near is not None and attempt < 80:
                nx, ny = g.xy(near.tiles[0])
                lo, hi = HOUSE_RADIUS
                x, y = nx + rng.randint(-hi, hi), ny + rng.randint(-hi, hi)
                if max(abs(x - nx), abs(y - ny)) < lo or not g.on_map(x, y):
                    continue
            else:
                x, y = rng.randint(g.x0, g.x1), rng.randint(g.y0, g.y1)
            t = g.idx(x, y)
            if not self._site_ok(t):
                continue
            for side in self._sides():
                door = _beside(g, t, side)
                if self._door_ok(door):
                    house = House(self._id(), color, t, door, side)
                    self.houses[house.id] = house
                    self.net.add_building([t], t, door)
                    return house
        return None

    def spawn_shop(self, color):
        g, rng = self.grid, self.rng
        for attempt in range(300):
            x, y = rng.randint(g.x0, g.x1 - 1), rng.randint(g.y0, g.y1 - 1)
            tiles = [g.idx(x, y), g.idx(x + 1, y), g.idx(x, y + 1), g.idx(x + 1, y + 1)]
            if not all(self._site_ok(t) for t in tiles):
                continue
            if attempt < 200 and any(max(abs(x - sx), abs(y - sy)) < SHOP_SPACING
                                     for sx, sy in (g.xy(s.tiles[0]) for s in self.shops.values())):
                continue
            for side in self._sides():
                # The node is the footprint tile next to the door; pick one of the two on that side.
                options = {"N": tiles[:2], "S": tiles[2:], "W": tiles[0::2], "E": tiles[1::2]}[side]
                node = rng.choice(options)
                door = _beside(g, node, side)
                if self._door_ok(door) and door not in tiles:
                    shop = Shop(self._id(), color, tiles, node, door, side)
                    self.shops[shop.id] = shop
                    self.net.add_building(tiles, node, door)
                    return shop
        return None


def _beside(grid, t, side):
    dx, dy = {"N": (0, -1), "S": (0, 1), "E": (1, 0), "W": (-1, 0)}[side]
    return grid.step(t, dx, dy)
