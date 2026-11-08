"""Deep Colony: Match, one colony from start to finish (no lobby, network or members).

    match = Match({"p1": "Ann"}, {"colonists": 3, "mapSize": "medium"}, rng, colors={"p1": "#e6194b"})
    Match.blank(w, h, fill="oxygen")   # tests: a plain world, no pod, no colonists
    match.step(dt)            # advance the simulation by dt game seconds (server: speed x per tick)
    match.set_paused(pid, bool) / match.set_speed(pid, 1-3)   # any player; logged
    orders.dig(match, ...) etc.  (logic/orders.py)  player orders
    match.remove(pid)         # pid left: the colony goes on (their orders stay)
    match.public(cursors) / match.private(pid, cursor)   # view.py builds them
    match.result              # None while playing; then {"reason": ...} (all colonists dead)

State it holds: world (grid.World), items (items.Items), buildings (buildings.Buildings),
digs (orders.py), dupes {id: dupes.Dupe}, networks (networks.Networks), time (game seconds),
paused, speed, log.

One step: every FLUID_DT of game time the grid updates (fluids, heat, germs, debris falling,
decor when buildings/debris changed); every step: power networks, machines, colonists (chores).
"""

import random

from gamekit import LobbyError

from . import chores, dupes, fluids, germs, heat, machines, mapgen, view
from .buildings import Buildings
from .grid import World
from .items import Items
from .networks import Networks

CYCLE = 600.0         # game seconds per cycle (day)
FLUID_DT = 0.5        # game seconds between grid updates
SPEEDS = (1, 2, 3)
LOG_KEEP = 30
MAP_SIZES = {"small": (48, 32), "medium": (64, 40), "large": (80, 48)}
START_STOCK = {"nutrient_bar": 8.0}   # in the Arrival Pod at the start


class Match:
    def __init__(self, names, settings, rng=None, colors=None, world=None):
        self.names = dict(names)  # public id -> name, fixed at the start
        self.colors = dict(colors or {})
        self.settings = dict(settings)
        self.rng = rng or random.Random()
        pod = None
        if world is None:
            w, h = MAP_SIZES.get(self.settings.get("mapSize", "medium"), MAP_SIZES["medium"])
            world, pod = mapgen.generate(w, h, self.rng)
        self.world = world
        self.items = Items()
        self.buildings = Buildings(world, self.items)
        self.digs = {}
        self.dupes = {}
        self.networks = Networks(self)
        self.time = 0.0
        self.cycle_length = CYCLE
        self.paused = False
        self.speed = 1
        self.result = None
        self.log_entries = {}
        self.log_count = 0
        self._fluid_acc = 0.0
        self._decor_version = None
        self._had_dupes = False
        if pod is not None:
            px, py = pod
            b = self.buildings.place("arrival_pod", px, py, "", built=True)
            b.store.update(START_STOCK)
            dupes.spawn(self, int(self.settings.get("colonists", 3)), px + 1, py + 2)
        germs.update_decor(self.world, self.buildings, self.items)

    @classmethod
    def blank(cls, w, h, fill="oxygen", temp=20.0, names=None):
        """A match on a plain world (bedrock-free, all `fill`), for tests."""
        return cls(names or {"p1": "Ann"}, {}, random.Random(1), world=World(w, h, fill, temp))

    # --- time -----------------------------------------------------------------------------

    @property
    def cycle(self):
        return int(self.time // CYCLE) + 1

    def set_paused(self, pid, paused):
        if paused == self.paused:
            return
        self.paused = paused
        self.log(f"{self.names.get(pid, pid)} {'paused' if paused else 'resumed'}.")

    def set_speed(self, pid, speed):
        if speed not in SPEEDS:
            raise LobbyError("Speed must be 1, 2 or 3.")
        if speed != self.speed:
            self.speed = speed
            self.log(f"{self.names.get(pid, pid)} set speed {speed}x.")

    def step(self, dt):
        if self.result is not None:
            return
        self.time += dt
        world = self.world
        self._fluid_acc += dt
        while self._fluid_acc >= FLUID_DT:
            self._fluid_acc -= FLUID_DT
            fluids.step(world, FLUID_DT)
            heat.step(world, FLUID_DT)
            germs.step(world, self.items, FLUID_DT)
            self.items.settle(world)
        version = (self.buildings.version, self.items.version)
        if version != self._decor_version:
            self._decor_version = version
            germs.update_decor(world, self.buildings, self.items)
        self.networks.step(dt)
        machines.step(self, dt)
        chores.step(self, dt)
        for d in [d for d in self.dupes.values() if d.dead]:
            del self.dupes[d.id]
            chores.cancel_for(self, ("dupe", d.id))
            self.log(f"{d.name} died ({d.death}).")
        if self.dupes:
            self._had_dupes = True
        elif self._had_dupes:
            self.result = {"reason": "Every colonist has died."}

    # --- players --------------------------------------------------------------------------

    def remove(self, pid):
        """A player left: the colony carries on; their orders stay."""

    def log(self, text):
        self.log_entries[self.log_count] = text
        self.log_entries.pop(self.log_count - LOG_KEEP, None)
        self.log_count += 1

    # --- releasing work when its target goes away -----------------------------------------

    def release_building(self, b):
        chores.cancel_for(self, ("building", b.id))
        b.reserved.clear()

    def release_dig(self, i):
        chores.cancel_for(self, ("dig", i))

    # --- what clients see -----------------------------------------------------------------

    def public(self, cursors=None):
        return view.public(self, cursors or {})

    def private(self, pid, cursor=None):
        return view.private(self, pid, cursor)
