"""Metro Lanes match: one game in progress. Players, the week clock and weekly picks, and the
order of a tick; the rules themselves are in the other logic/ modules.

Tick order (step): pick countdown (the city is paused while picking) -> city growth, demand and
overflow timers (city.py) -> traffic (traffic.py) -> lost? -> end of week. Building, erasing and
placing work any time, picks included. Weeks: every `weekLength` seconds the area grows
(grid.py), everyone gets upgrades.WEEKLY and picks one of two offers.
"""

import random

from gamekit import LobbyError

from .city import COLOR_NAMES, City
from .grid import Grid
from .players import Player, start_roads
from .roads import FEATURES, RoadNet
from .traffic import Traffic
from .upgrades import UPGRADES, WEEKLY, give, offers

PLAYER_GROWTH = 0.4   # each extra player makes the city grow this much faster (they bring roads too)


class Match:
    def __init__(self, names, settings, colors=None, rng=None):
        self.rng = rng or random.Random()
        colors = colors or {}
        self.players = {pid: Player(pid, name, colors.get(pid, "#888888")) for pid, name in names.items()}
        for player, roads in zip(self.players.values(), start_roads(len(self.players))):
            player.stock["roads"] = roads
        self.settings = settings
        self.week_len = settings["weekLength"]
        self.overflow = settings["overflow"]
        self.pick_time = settings["pickTime"]
        self.grid = Grid(settings["mapSize"], self.rng)
        self.net = RoadNet(self.grid, self.players)
        demand = settings["growth"] / 100
        growth = demand * (1 + PLAYER_GROWTH * (len(names) - 1))
        self.city = City(self.grid, self.net, self.rng, growth=growth, demand=demand)
        self.traffic = Traffic(self.net, self.city, self.players)
        self.week = 0            # 0-based; shown as week + 1
        self.time = 0.0          # seconds into this week
        self.offers = None       # this week's two upgrade ids while picking
        self.pick_left = 0.0
        self.result = None
        for house in self.city.start():
            self.traffic.add_house(house)

    def active(self):
        return [p for p in self.players.values() if not p.gone]

    # --- time -------------------------------------------------------------------------

    def step(self, dt):
        if self.result is not None:
            return
        if self.offers is not None:
            self.pick_left -= dt
            if self.pick_left <= 0:
                self._end_pick()
            return
        self.time += dt
        new, lost = self.city.step(dt, self.week, self.overflow)
        for house in new:
            self.traffic.add_house(house)
        self.traffic.step(dt)
        if lost is not None:
            self.result = self._result(f"The {COLOR_NAMES[lost.color]} shop waited too long. Everyone loses!")
            return
        if self.time >= self.week_len:
            self._new_week()

    def _new_week(self):
        self.week += 1
        self.time = 0.0
        self.grid.grow()
        for player in self.active():
            give(player, WEEKLY)
            player.picked = None
        self.offers = offers(self.rng)
        self.pick_left = self.pick_time

    def pick(self, pid, option):
        if self.offers is None:
            raise LobbyError("There's nothing to pick right now.")
        player = self.players[pid]
        if player.picked is not None:
            raise LobbyError("You already picked this week.")
        if option not in (0, 1):
            raise LobbyError("Pick one of the two.")
        player.picked = option
        give(player, UPGRADES[self.offers[option]]["gives"])
        if all(p.picked is not None for p in self.active()):
            self._end_pick()

    def _end_pick(self):
        """Time's up (or everyone picked): whoever hasn't picked gets the first offer."""
        for player in self.active():
            if player.picked is None:
                player.picked = 0
                give(player, UPGRADES[self.offers[0]]["gives"])
        self.offers = None

    # --- building ---------------------------------------------------------------------

    def road(self, pid, a, b):
        self.net.draw(pid, a, b)

    def erase(self, pid, t):
        self.net.erase(pid, t)

    def motorway(self, pid, a, b):
        self.net.motorway(pid, a, b)

    def place(self, pid, t, feature):
        if feature not in FEATURES:
            raise LobbyError("Unknown piece.")
        self.net.place(pid, t, feature)

    def cursor(self, pid, xy):
        self.players[pid].cursor = xy

    # --- players ----------------------------------------------------------------------

    def remove(self, pid):
        player = self.players.get(pid)
        if player is None or player.gone:
            return
        player.gone = True
        player.cursor = None
        if not self.active():
            self.result = self._result("Everyone left.")
        elif self.offers is not None and all(p.picked is not None for p in self.active()):
            self.offers = None

    def _result(self, reason):
        return {"reason": reason, "week": self.week + 1, "trips": self.traffic.trips,
                "points": {pid: round(p.points) for pid, p in self.players.items()},
                "names": {pid: p.name for pid, p in self.players.items()}}
