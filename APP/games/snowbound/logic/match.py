"""Match: one game of Snowbound (the valley, the players' characters and units, weather, huts).

Match(names, settings, colors, rng). Players are public ids ("p1"); no lobby code here.
step(dt) advances everything (called TICK_RATE times a second by server.py):
weather -> once a second (blizzard snowfall or deliveries) -> golden snowflakes -> stove and
needs (survival.py) -> characters walk and shovel (avatars.py) -> route fields (roads.py) ->
units (units.py, hauling.py, factory.py) -> swing budgets -> goal check.
Player actions raise LobbyError when refused: dig (one swing), buy, upgrade, supply, rally,
build_hut, build_depot (hauling.py), lay_road (roads.py); set_input stores held controls.
The valley also holds hidden landmarks (landmarks.py; effects: the team effects found so far,
markets: Old Rail Station lots; depots: Snow Depot lots). swing() is quiet for lots you can't dig (the snow
may simply have been cleared a moment ago).
Golden snowflakes appear on reached ground near a random player; walking into one catches it.
result: {"reason": str, "cleared": {pid: snow}} once the goal share of lots is clear.
"""

import math
import random

from gamekit import LobbyError

from . import avatars, hauling, landmarks, roads, survival, units
from .content import MACHINES, UPGRADES
from .economy import CLICKS_PER_SECOND, MAX_OWNED, PRICES, Player
from .world import World

SIZES = {"small": 96, "medium": 160, "large": 256, "huge": 384}
FLAKE_EVERY = (40, 90)
FLAKE_LIFE = 25
FLAKE_NEAR = (4, 18)    # lots from the chosen player
FLAKE_CATCH = 1.0
FRENZY_TIME = 30
LUCKY_SECONDS = 600     # a lucky flake pays up to this many seconds of your machines...
LUCKY_SHARE = 0.15      # ...but at most this share of your cash (at least LUCKY_MIN)
LUCKY_MIN = 77
FOREST_LOGS = 4
HUT_COST = 200
HUT_GROWTH = 2.5
HUT_SPACING = 4         # lots from the cabin and other huts
MAX_HUTS = 40
LOG_KEEP = 30
MAX_SUPPLY = 10 ** 12


class Match:
    def __init__(self, names, settings, colors=None, rng=None):
        self.rng = rng or random.Random()
        colors = colors or {}
        size = settings.get("mapSize") if settings.get("mapSize") in SIZES else "large"
        self.world = World(SIZES[size], self.rng)
        w = self.world
        landmarks.place(w, self.rng, size)
        self.roads = roads.Network(w)
        self.depots = []            # Snow Depot lots
        self.markets = []           # Old Rail Station lots
        self.effects = set()        # team effects from landmarks
        self.players = {}
        for k, (pid, name) in enumerate(names.items()):
            angle = 2 * math.pi * k / max(1, len(names))
            self.players[pid] = Player(pid, name, colors.get(pid, "#4fc3f7"),
                                       w.cx + 0.5 + 1.2 * math.cos(angle), w.cy + 0.5 + 1.2 * math.sin(angle))
        self.names = dict(names)
        self.goal = settings.get("goal", 75) / 100
        self.harshness = survival.HARSHNESS.get(settings.get("survival"), 1.0)
        self.weather = survival.Weather(self.rng)
        self.woodpile = float(survival.START_LOGS)
        self.shared_upgrades = {}   # upgrade id -> pid who bought it
        self.units = {}             # uid -> units.Unit
        self.unit_counter = 0
        self.huts = []              # [(x, y)] lots
        self.beams = {}             # n -> {"x0", "y0", "x1", "y1", "c", "left"}: Jet Blower shots to draw
        self.beam_count = 0
        self.flake = None           # {"i": lot, "left": seconds}
        self.flake_timer = self.rng.uniform(*FLAKE_EVERY)
        self.time = 0.0
        self._second = 0.0
        self.log = []               # [(number, text)]
        self.log_count = 0
        self.result = None
        self.say("Dig out the valley! Walk with WASD, hold the mouse on snow next to you to shovel. "
                 "Stay near the cabin's stove to keep warm.")

    # --- helpers ---------------------------------------------------------------------

    def say(self, text):
        self.log_count += 1
        self.log.append((self.log_count, text))
        del self.log[:-LOG_KEEP]

    def player(self, pid):
        if pid not in self.players:
            raise LobbyError("You're not in this game.")
        return self.players[pid]

    def progress(self):
        return self.world.cleared() / (self.world.w * self.world.h)

    def team_has(self, uid):
        """Has anyone bought shared upgrade uid?"""
        return uid in self.shared_upgrades

    def beam(self, x0, y0, x1, y1, color):
        self.beam_count += 1
        self.beams[str(self.beam_count)] = {"x0": round(x0, 2), "y0": round(y0, 2), "x1": round(x1, 2),
                                            "y1": round(y1, 2), "c": color, "left": 1.5}

    def buddies_near(self, p):
        """How many of p's Shovel Buddies are close enough to help."""
        near = [u for u in self.units.values() if u.pid == p.id and MACHINES[u.mid]["kind"] == "buddy"
                and math.hypot(u.x - p.x, u.y - p.y) <= MACHINES[u.mid]["params"].get("near", 2)]
        return len(near), (MACHINES[near[0].mid]["params"].get("boost", 0.5) if near else 0)

    def shovel(self, p):
        """(power per swing, reach, splash share) for p right now, Shovel Buddies included."""
        n, boost = self.buddies_near(p)
        grip = p.has("heated-grip")
        power = p.click_power() * (1 + n * (1.0 if grip else boost))
        return power, avatars.REACH + (1 if n else 0), (1.0 if grip else 0.5) if n else 0

    def hut_cost(self):
        return round(HUT_COST * HUT_GROWTH ** len(self.huts))

    def occupied(self, i):
        """Is something built on lot i (a placed machine, depot, rail station or hut)?"""
        x, y = self.world.xy(i)
        return units.placed_at(self, i) or i in self.depots or i in self.markets or (x, y) in self.huts

    # --- time ------------------------------------------------------------------------

    def step(self, dt):
        if self.result is not None:
            return
        self.time += dt
        changed = self.weather.step(dt)
        if changed == "warning":
            self.say(f"A blizzard is coming in {self.weather.warning} seconds! Stock up on logs and head for shelter.")
        elif changed == "blizzard":
            self.say("Blizzard! Snow is piling back up and the stove burns fast.")
        elif changed == "clear":
            self.say("The blizzard has passed.")
        self._second += dt
        if self._second >= 1:
            self._second -= 1
            if self.weather.blizzard:
                survival.dust(self)
            else:
                survival.deliveries(self)
        self._flakes(dt)
        survival.step(self, dt)
        avatars.step(self, dt)
        self.roads.update()
        units.step(self, dt)
        for key in [k for k, b in self.beams.items() if b["left"] <= dt]:
            del self.beams[key]
        for b in self.beams.values():
            b["left"] -= dt
        for p in self.players.values():
            p.clicks = min(CLICKS_PER_SECOND, p.clicks + CLICKS_PER_SECOND * dt)
        if self.progress() >= self.goal - 1e-9:
            self.result = {"reason": f"The valley is dug out: {round(self.progress() * 100)}% cleared "
                                     f"in {int(self.time // 60)} min {int(self.time % 60)} s.",
                           "cleared": {pid: round(p.cleared) for pid, p in self.players.items()}}

    def _flakes(self, dt):
        if self.flake is not None:
            fx, fy = self.world.xy(self.flake["i"])
            for p in self.players.values():
                if math.hypot(p.x - fx - 0.5, p.y - fy - 0.5) <= FLAKE_CATCH:
                    self.catch_flake(p.id)
                    return
            self.flake["left"] -= dt
            if self.flake["left"] <= 0:
                self.flake = None
            return
        self.flake_timer -= dt
        if self.flake_timer <= 0 and self.players:
            self.flake_timer = self.rng.uniform(*FLAKE_EVERY) * (0.5 if "observatory" in self.effects else 1)
            self.flake = {"i": self._flake_spot(), "left": float(FLAKE_LIFE)}

    def _flake_spot(self):
        """A reached lot FLAKE_NEAR lots from a random player (any reached lot if none found)."""
        p = self.rng.choice(list(self.players.values()))
        lots = self.world.reached_list
        for _ in range(80):
            i = self.rng.choice(lots)
            x, y = self.world.xy(i)
            if FLAKE_NEAR[0] <= math.hypot(x + 0.5 - p.x, y + 0.5 - p.y) <= FLAKE_NEAR[1]:
                return i
        return self.rng.choice(lots)

    def catch_flake(self, pid):
        p = self.players[pid]
        self.flake = None
        mult = p.effect("flake")
        if self.rng.random() < 0.5:
            p.frenzy = FRENZY_TIME * mult
            self.say(f"{p.name} caught a golden snowflake: Frenzy! x5 snow for {round(p.frenzy)} s.")
        else:
            bonus = round(max(LUCKY_MIN, min(p.cash * LUCKY_SHARE, LUCKY_SECONDS * p.base_rate())) * mult)
            p.cash += bonus
            p.earned += bonus
            self.say(f"{p.name} caught a golden snowflake: Lucky! +${bonus:,}.")

    def found(self, pid, kind, i):
        """Lot i was cleared for the first time by pid or pid's unit; kind is its feature."""
        p = self.players[pid]
        if kind == "site":
            landmarks.found(self, pid, i)
        elif kind == "forest":
            self.woodpile += FOREST_LOGS
        elif kind == "house":
            bonus = round(max(50, 30 * p.base_rate()))
            p.cash += bonus
            p.earned += bonus
            self.say(f"{p.name} dug out a buried cabin and found ${bonus:,} inside.")
        elif kind == "gas":
            fuel = round(max(300, 120 * p.diesel_use()))
            p.diesel += fuel
            self.say(f"{p.name} reached an old gas station: +{fuel:,} L diesel.")
        elif kind == "cache":
            p.rations += 3
            p.diesel += 30
            self.say(f"{p.name} found a supply cache: +3 rations, +30 L diesel.")
        elif kind == "skier" and "kid" in MACHINES and p.owned["kid"] + 2 <= MAX_OWNED:
            p.owned["kid"] += 2
            x, y = self.world.xy(i)
            units.add(self, pid, "kid", 2, x + 0.5, y + 0.5)
            self.say(f"{p.name} rescued two lost skiers. They join the crew as Neighbour Kids!")

    # --- actions ---------------------------------------------------------------------

    def set_input(self, pid, keys, aim, dig):
        p = self.player(pid)
        p.keys, p.aim, p.dig = tuple(keys), aim, dig

    def swing(self, pid, x, y):
        """One swing of pid's shovel at lot (x, y). Returns the snow removed (0 if nothing)."""
        p = self.player(pid)
        i = self.world.index(x, y)
        power, reach, splash = self.shovel(p)
        if i is None or not self.world.workable(i) or not avatars.in_reach(p, x, y, reach) or p.clicks < 1:
            return 0.0
        if p.frostbite:
            return 0.0
        p.clicks -= 1
        p.swinging = 0.3
        survival.clicked(self, p)
        hits = [(i, power)] + [(j, power * splash) for j in self.world.neighbours(i)] if splash else [(i, power)]
        total = 0.0
        for j, amount in hits:
            removed, found = self.world.dig(j, amount)
            p.earn(removed)
            total += removed
            if found:
                self.found(pid, found, j)
        return total

    def dig(self, pid, x, y):
        """A click: one swing now (refused with a message only for frostbite)."""
        if self.player(pid).frostbite:
            raise LobbyError("Your hands are frozen! Warm up by the stove or a hut first.")
        return self.swing(pid, x, y)

    def buy(self, pid, mid, count):
        p = self.player(pid)
        if mid in MACHINES and MACHINES[mid]["placed"]:
            w = self.world
            x, y = math.floor(p.x), math.floor(p.y)
            i = w.index(x, y)
            if count != 1:
                raise LobbyError("Placed machines are built one at a time, where you stand.")
            if i is None or not w.reached[i] or w.kind[i] in ("cabin", "site"):
                raise LobbyError("Stand on cleared ground (not the cabin or a landmark) to place it.")
            if self.occupied(i):
                raise LobbyError("Something is already built on this spot.")
            p.buy_machine(mid, 1)
            units.add(self, pid, mid, 1, x + 0.5, y + 0.5, home=i)
            return
        p.buy_machine(mid, count)
        units.add(self, pid, mid, count, p.x if MACHINES.get(mid, {}).get("kind") == "buddy" else None,
                  p.y if MACHINES.get(mid, {}).get("kind") == "buddy" else None)

    def upgrade(self, pid, uid):
        p = self.player(pid)
        if uid not in UPGRADES:
            raise LobbyError("Unknown upgrade.")
        if not p.upgrade_visible(uid, self.shared_upgrades):
            raise LobbyError("That upgrade isn't available.")
        u = UPGRADES[uid]
        p.pay(u["cost"])
        if u["shared"]:
            self.shared_upgrades[uid] = pid
            self.say(f"{p.name} bought {u['name']} for everyone.")
        else:
            p.upgrades.add(uid)

    def supply(self, pid, item, qty):
        p = self.player(pid)
        if item not in PRICES:
            raise LobbyError("Unknown supply.")
        if not 0 < qty <= MAX_SUPPLY:
            raise LobbyError("Bad amount.")
        if self.weather.blizzard and item != "rations":
            raise LobbyError("No deliveries during a blizzard!")
        p.buy_supply(item, qty)
        if item == "logs":
            self.woodpile += qty

    def rally(self, pid, where):
        """Where pid's units look for work: None, "follow" (you) or lot [x, y]."""
        p = self.player(pid)
        if where is None or where == "follow":
            p.rally = where
        else:
            i = self.world.index(*where)
            if i is None:
                raise LobbyError("That's off the map.")
            p.rally = i
        for u in self.units.values():
            if u.pid == pid:
                u.target = None
                hauling.cancel_back(u)

    def build_hut(self, pid):
        """A warming hut on the lot pid stands on (paid by pid; heats everyone)."""
        p = self.player(pid)
        w = self.world
        x, y = math.floor(p.x), math.floor(p.y)
        i = w.index(x, y)
        if len(self.huts) >= MAX_HUTS:
            raise LobbyError(f"The valley has the most huts it can take ({MAX_HUTS}).")
        if i is None or not w.reached[i] or w.kind[i] in ("cabin", "site"):
            raise LobbyError("Build huts on cleared ground.")
        if self.occupied(i):
            raise LobbyError("Something is already built on this spot.")
        if math.hypot(x - w.cx, y - w.cy) < HUT_SPACING or any(
                math.hypot(x - hx, y - hy) < HUT_SPACING for hx, hy in self.huts):
            raise LobbyError(f"Too close to the cabin or another hut (keep {HUT_SPACING} lots apart).")
        p.pay(self.hut_cost())
        self.huts.append((x, y))
        self.say(f"{p.name} built a warming hut.")

    def build_depot(self, pid):
        hauling.build_depot(self, pid)

    def lay_road(self, pid, lots, level):
        return roads.lay(self, pid, lots, level)

    def remove(self, pid):
        p = self.players.pop(pid, None)
        if p is None:
            return
        units.remove_player(self, pid)
        self.say(f"{p.name} left the valley.")
        if not self.players and self.result is None:
            self.result = {"reason": "Everyone left.", "cleared": {}}
