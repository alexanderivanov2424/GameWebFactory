"""Metro Lanes traffic: cars driving pins from shops home, lanes, junctions and points.

- Dispatch (every DISPATCH_EVERY s): for each shop with more pins than cars on the way, the
  nearest idle cars (by driving time) of houses in its colour that can reach it set off.
- Cars drive tile centre to tile centre along a route (roads.RoadNet.route), keeping right.
  Each direction of each link is a lane: a car stays GAP tiles behind the car ahead in its lane
  and waits to enter a lane whose last car hasn't moved GAP tiles in.
- Junctions (road tiles where 3+ ways meet): a car must hold the junction from NODE_ZONE tiles
  before it until NODE_ZONE tiles after. A plain junction holds 1 car, which crawls through at
  JUNCTION_SLOW speed; a traffic light holds 2 cars, but only from the green direction
  (horizontal and vertical alternate every LIGHT_PHASE s, all lights in step); a roundabout
  holds 4 at full speed. A car stuck for GIVE_UP s squeezes through (no permanent gridlock).
- At the shop the car takes a pin (one trip), parks PARK_TIME s and drives home.
  Each trip is worth TRIP_POINTS, split between the players who built the tiles it drove on
  to the shop (by tiles; motorways count their length).
- When roads change, cars take the new best route from their next tile; a car whose link was
  erased, or that can no longer reach where it's going, is sent straight home (its pin waits
  for another car).
"""

import math

GAP = 0.5
NODE_ZONE = 0.45
JUNCTION_SLOW = 0.5
CAPACITY = {None: 1, "light": 2, "roundabout": 4}
LIGHT_PHASE = 4.0
GIVE_UP = 6.0
PARK_TIME = 1.2
DISPATCH_EVERY = 0.5
TRIP_POINTS = 10
LANE_OFFSET = 0.16        # keep right: tiles from the road's centre line


class Car:
    def __init__(self, cid, house):
        self.id, self.house, self.color = cid, house, house.color
        self.state = "home"      # home | out | park | back
        self.shop = None
        self.path, self.k, self.d = None, 0, 0.0
        self.driven = []         # tiles passed on the way to the shop (for points)
        self.held = set()        # junctions this car holds
        self.wait = 0.0
        self.park_left = 0.0
        self.version = -1


class Traffic:
    def __init__(self, net, city, players):
        self.net, self.city, self.players = net, city, players
        self.cars = {}
        self.lanes = {}          # (u, v) -> [cars], first entered first
        self.holders = {}        # junction tile -> set of car ids
        self.clock = 0.0
        self.dispatch_clock = 0.0
        self.trips = 0
        self._next = 1

    def add_house(self, house):
        for _ in range(house.home):
            car = Car(str(self._next), house)
            self._next += 1
            self.cars[car.id] = car

    def green(self):
        """The direction lights let through now: "h" or "v"."""
        return "h" if int(self.clock / LIGHT_PHASE) % 2 == 0 else "v"

    # --- one tick ---------------------------------------------------------------------

    def step(self, dt):
        self.clock += dt
        self.dispatch_clock += dt
        if self.dispatch_clock >= DISPATCH_EVERY:
            self.dispatch_clock -= DISPATCH_EVERY
            self.dispatch()
        for car in list(self.cars.values()):
            if car.state == "park":
                car.park_left -= dt
                if car.park_left <= 0:
                    self._leave_shop(car)
            elif car.state in ("out", "back"):
                self._drive(car, dt)

    def dispatch(self):
        net, city = self.net, self.city
        for shop in city.shops.values():
            want = shop.pins - shop.assigned
            if want <= 0 or shop.door not in net.roads:
                continue
            tree = net.tree(shop.node)
            houses = sorted((tree[h.node][0], h.id) for h in city.houses_of(shop.color) if h.home > 0 and h.node in tree)
            for _cost, hid in houses:
                house = city.houses[hid]
                while house.home > 0 and want > 0:
                    car = next(c for c in self.cars.values() if c.house is house and c.state == "home")
                    path = net.route(house.node, shop.node)
                    house.home -= 1
                    shop.assigned += 1
                    want -= 1
                    car.state, car.shop, car.driven = "out", shop, [house.node]
                    self._set_path(car, path)
                if want <= 0:
                    break

    def _set_path(self, car, path):
        car.path, car.k, car.d, car.wait = path, 0, 0.0, 0.0
        car.version = self.net.version
        self.lanes.setdefault((path[0], path[1]), []).append(car)

    def _target(self, car):
        return car.shop.node if car.state == "out" else car.house.node

    def _drive(self, car, dt):
        net = self.net
        u, v = car.path[car.k], car.path[car.k + 1]
        if car.version != net.version and not net.has_edge(u, v):
            self.send_home(car)
            return
        ghost = car.wait >= GIVE_UP
        slow = any(net.roads.get(n) is not None and net.roads[n].feature is None for n in car.held)
        dist = net.speed(u, v) * dt * (JUNCTION_SLOW if slow else 1.0)
        moved = False
        while True:
            u, v = car.path[car.k], car.path[car.k + 1]
            lane = self.lanes[(u, v)]
            length = net.length(u, v)
            if car.d >= length - 1e-9:  # at node v
                if car.k + 2 >= len(car.path):
                    self._arrive(car)
                    return
                if car.version != net.version:
                    rest = net.route(v, self._target(car))
                    if rest is None:
                        self.send_home(car)
                        return
                    car.path, car.k, car.version = [u, *rest], 0, net.version
                w = car.path[car.k + 2]
                nxt = self.lanes.setdefault((v, w), [])
                if nxt and nxt[-1].d < GAP and not ghost:
                    break
                lane.remove(car)
                if not lane:
                    del self.lanes[(u, v)]
                nxt.append(car)
                car.k += 1
                car.d = 0.0
                if car.state == "out":
                    car.driven.append(v)
                ghost, moved = False, True
                continue
            if dist <= 1e-9:
                break
            stop = length
            i = lane.index(car)
            if i > 0 and not ghost:
                stop = min(stop, lane[i - 1].d - GAP)
            if v not in car.held and net.junction(v) and car.d + dist >= length - NODE_ZONE:
                if not self._hold(car, u, v, ghost):
                    stop = min(stop, length - NODE_ZONE)
            to = min(car.d + dist, stop)
            if to <= car.d + 1e-9:
                break
            dist -= to - car.d
            car.d, moved = to, True
            if u in car.held and car.d >= min(NODE_ZONE, length / 2):
                self._release(car, u)
        car.wait = 0.0 if moved else car.wait + dt

    def _hold(self, car, u, v, ghost):
        road = self.net.roads[v]
        holders = self.holders.setdefault(v, set())
        if not ghost:
            if road.feature == "light":
                (ux, uy), (vx, vy) = self.net.grid.xy(u), self.net.grid.xy(v)
                if ("h" if abs(vx - ux) >= abs(vy - uy) else "v") != self.green():
                    return False
            if len(holders) >= CAPACITY[road.feature]:
                return False
        holders.add(car.id)
        car.held.add(v)
        return True

    def _release(self, car, n):
        car.held.discard(n)
        holders = self.holders.get(n)
        if holders is not None:
            holders.discard(car.id)
            if not holders:
                del self.holders[n]

    def _off_road(self, car):
        if car.path is not None and car.k + 1 < len(car.path):
            lane = self.lanes.get((car.path[car.k], car.path[car.k + 1]))
            if lane and car in lane:
                lane.remove(car)
                if not lane:
                    del self.lanes[(car.path[car.k], car.path[car.k + 1])]
        for n in list(car.held):
            self._release(car, n)
        car.path, car.k, car.d, car.wait = None, 0, 0.0, 0.0

    def _arrive(self, car):
        self._off_road(car)
        if car.state == "out":
            shop = car.shop
            shop.pins = max(0, shop.pins - 1)
            shop.assigned -= 1
            self.trips += 1
            self._credit(car.driven + [shop.node])
            car.state, car.park_left = "park", PARK_TIME
        else:
            car.state, car.shop = "home", None
            car.house.home += 1

    def _leave_shop(self, car):
        path = self.net.route(car.shop.node, car.house.node)
        if path is None:
            self.send_home(car)
            return
        car.state = "back"
        self._set_path(car, path)

    def send_home(self, car):
        """Back home at once (its route is gone); an unfinished pin waits for another car."""
        self._off_road(car)
        if car.state == "out":
            car.shop.assigned -= 1
        if car.state != "home":
            car.state, car.shop = "home", None
            car.house.home += 1

    def _credit(self, path):
        shares = self.net.owner_shares(path)
        total = sum(shares.values())
        for pid, share in shares.items():
            player = self.players.get(pid)
            if player is not None and total > 0:
                player.points += TRIP_POINTS * share / total
                player.trips += 1

    # --- drawing ----------------------------------------------------------------------

    def position(self, car):
        """(x, y) of the car's centre in tiles, on the right-hand side of its lane."""
        g = self.net.grid
        u, v = car.path[car.k], car.path[car.k + 1]
        (ux, uy), (vx, vy) = g.xy(u), g.xy(v)
        length = max(1e-9, math.hypot(vx - ux, vy - uy))
        f = min(1.0, car.d / length)
        dx, dy = (vx - ux) / length, (vy - uy) / length
        return (ux + 0.5 + (vx - ux) * f - dy * LANE_OFFSET, uy + 0.5 + (vy - uy) * f + dx * LANE_OFFSET)

    def parked(self, shop):
        return sum(1 for c in self.cars.values() if c.state == "park" and c.shop is shop)
