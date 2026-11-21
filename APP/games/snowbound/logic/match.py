"""Match: one game of Snowbound (the valley, the players, weather, golden snowflakes).

Match(names, settings, colors, rng). Players are public ids ("p1"); no lobby code here.
step(dt) advances everything (called TICK_RATE times a second by server.py):
weather -> once a second (blizzard snowfall or deliveries, golden snowflakes) -> stove and
needs (survival.py) -> machine crews (crews.py) -> click budgets -> goal check.
Player actions raise LobbyError when refused: click, catch_flake, buy, upgrade, supply,
set_focus. Clicks on lots that can't be worked are ignored silently (the client also
checks, and the snow may simply have just been cleared by someone else).
result: {"reason": str, "cleared": {pid: snow}} once the goal share of lots is reached or
everyone left.
"""

import random

from gamekit import LobbyError

from . import crews, survival
from .content import MACHINES, UPGRADES
from .economy import CLICKS_PER_SECOND, PRICES, Player
from .world import World

SIZES = {"small": 96, "medium": 160, "large": 256, "huge": 384}
FLAKE_EVERY = (40, 90)
FLAKE_LIFE = 13
FLAKE_REACH = 1.6
FRENZY_TIME = 30
LUCKY_SECONDS = 600     # a lucky flake pays up to this many seconds of your machines...
LUCKY_SHARE = 0.15      # ...but at most this share of your cash (at least LUCKY_MIN)
LUCKY_MIN = 77
FOREST_LOGS = 4
LOG_KEEP = 30
MAX_SUPPLY = 10 ** 12


class Match:
    def __init__(self, names, settings, colors=None, rng=None):
        self.rng = rng or random.Random()
        colors = colors or {}
        self.players = {pid: Player(pid, name, colors.get(pid, "#4fc3f7")) for pid, name in names.items()}
        self.names = dict(names)
        self.world = World(SIZES.get(settings.get("mapSize"), SIZES["large"]), self.rng)
        self.goal = settings.get("goal", 75) / 100
        self.harshness = survival.HARSHNESS.get(settings.get("survival"), 1.0)
        self.weather = survival.Weather(self.rng)
        self.woodpile = float(survival.START_LOGS)
        self.shared_upgrades = {}   # upgrade id -> pid who bought it
        self.crews = {}
        self.flake = None           # {"i": lot, "left": seconds}
        self.flake_timer = self.rng.uniform(*FLAKE_EVERY)
        self.time = 0.0
        self._second = 0.0
        self.log = []               # [(number, text)]
        self.log_count = 0
        self.result = None
        self.say("Dig out the valley! Click snow next to cleared ground. Keep the stove fed and eat.")

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
        return len(self.world.reached_list) / (self.world.w * self.world.h)

    # --- time ------------------------------------------------------------------------

    def step(self, dt):
        if self.result is not None:
            return
        self.time += dt
        changed = self.weather.step(dt)
        if changed == "warning":
            self.say(f"A blizzard is coming in {survival.WARNING} seconds! Stock up on logs.")
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
        crews.step(self, dt)
        for p in self.players.values():
            p.clicks = min(CLICKS_PER_SECOND, p.clicks + CLICKS_PER_SECOND * dt)
        if self.progress() >= self.goal - 1e-9:
            self.result = {"reason": f"The valley is dug out: {round(self.progress() * 100)}% cleared "
                                     f"in {int(self.time // 60)} min {int(self.time % 60)} s.",
                           "cleared": {pid: round(p.cleared) for pid, p in self.players.items()}}

    def _flakes(self, dt):
        if self.flake is not None:
            self.flake["left"] -= dt
            if self.flake["left"] <= 0:
                self.flake = None
            return
        self.flake_timer -= dt
        if self.flake_timer <= 0:
            self.flake_timer = self.rng.uniform(*FLAKE_EVERY)
            self.flake = {"i": self.rng.choice(self.world.reached_list), "left": float(FLAKE_LIFE)}

    def found(self, pid, kind, i):
        """Lot i was cleared for the first time by pid's click or crew; kind is its feature."""
        p = self.players[pid]
        if kind == "forest":
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
        elif kind == "skier" and "helper" in MACHINES:
            p.owned["helper"] += 2
            self.say(f"{p.name} rescued two lost skiers. They join the crew as Neighbour Kids!")

    # --- actions ---------------------------------------------------------------------

    def click(self, pid, x, y):
        """Shovel lot (x, y) by hand. Returns the snow removed."""
        p = self.player(pid)
        i = self.world.index(x, y)
        if i is None or not self.world.workable(i) or p.clicks < 1:
            return 0.0
        if p.frostbite:
            raise LobbyError("Your hands are frozen! Warm up by the stove first.")
        p.clicks -= 1
        survival.clicked(self, p)
        removed, found = self.world.dig(i, p.click_power())
        p.earn(removed)
        if found:
            self.found(pid, found, i)
        return removed

    def catch_flake(self, pid, x, y):
        p = self.player(pid)
        if self.flake is None:
            raise LobbyError("The snowflake melted.")
        fx, fy = self.world.xy(self.flake["i"])
        if (fx - x) ** 2 + (fy - y) ** 2 > FLAKE_REACH ** 2:
            raise LobbyError("Missed the snowflake.")
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

    def buy(self, pid, mid, count):
        p = self.player(pid)
        p.buy_machine(mid, count)

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

    def set_focus(self, pid, xy):
        p = self.player(pid)
        if xy is None:
            p.focus = None
            return
        i = self.world.index(*xy)
        if i is None:
            raise LobbyError("That's off the map.")
        p.focus = i
        for crew in self.crews.values():
            if crew.pid == pid:
                crew.target = None

    def remove(self, pid):
        p = self.players.pop(pid, None)
        if p is None:
            return
        crews.remove_player(self, pid)
        self.say(f"{p.name} left the valley.")
        if not self.players and self.result is None:
            self.result = {"reason": "Everyone left.", "cleared": {}}
