"""Hex Realms: bots, computer players that plan their orders through the same rules as people.

    plan(m, pid)    give bot pid's orders for this turn, then mark it done

Every order goes through Match.act, so bots pass the same checks as people, and they only use
what pid knows (vision.known_at, m.visible, movement.reach), so fog of war applies to them too.
A simple strategy, in this order each turn:
  1. Settlers found a city where they stand if they can; otherwise they head for the nearest
     explored site within CITY_RANGE that it knows is free (about CITY_SPACING + 2 from its own
     cities), or wander.
  2. Research the cheapest advance it can afford.
  3. Builders: if a construction site gets no builders, switch off its newest working structure
     that doesn't make food (once nothing is waiting, switch everything back on). Then build by
     need (at most MAX_BUILDS a turn, only with idle people left over for builders): homes when
     nearly full, farms when food is short, a lumbermill and a mine per city, storage when goods
     are near the cap, then Barracks, Market, Chapel, College, Smithy, Towers, more farms, anywhere
     in its territory (near the Town Hall preferred). If a farm / lumbermill / mine finds no land
     it needs, it buys land (orders.claim, up to MAX_CLAIMS a turn, only while its gold income pays the
     land's upkeep) towards the nearest such terrain.
  4. Recruit Settlers until it has 3 cities, then an army that grows with the turn number.
  5. Units: ranged ones shoot what's in range; everyone attacks enemies near its structures;
     the oldest unit scouts (explore.target, like the Explore order) until a war needs it; from ATTACK_TURN an army of
     ATTACK_ARMY marches on the nearest enemy city it knows (or any enemy structure); the rest
     stay near home and hold.
"""

import random
from collections import Counter

from gamekit import LobbyError
from gamekit.hexes import disk, dist, neighbors, parse

from . import construction, economy, explore, logistics, movement, orders, territory, vision
from .content import ADVANCES, STRUCTURES, TOWN_HALL, UNITS, footprint
from .economy import report, staffing

MAX_BUILDS = 3
MAX_CLAIMS = 2
CITIES = 3
CITY_RANGE = 10
ATTACK_TURN = 20
ATTACK_ARMY = 5
NEED_TERRAIN = {"farm": {"plains", "hills"}, "lumbermill": {"forest"}, "mine": {"hills", "mountain"}}


def try_act(m, pid, *args):
    try:
        m.act(pid, *args)
        return True
    except LobbyError:
        return False


def plan(m, pid):
    if m.result is not None or not m.players[pid]["alive"]:
        return
    bot = Bot(m, pid)
    bot.settlers()
    bot.research()
    bot.builders()
    bot.build()
    bot.recruit()
    bot.army()
    m.players[pid]["done"] = True


class Bot:
    def __init__(self, m, pid):
        self.m, self.pid = m, pid
        self.rng = random.Random(f"{m.settings.get('seed')}-{pid}-{m.turn}")
        self.mine = [s for s in m.structures.values() if s["owner"] == pid]
        self.sites = [x for x in m.sites.values() if x["owner"] == pid]
        self.halls = [s for s in self.mine if s["type"] == TOWN_HALL]
        self.hall_cells = [c for s in self.halls for c in s["cells"]]
        self.units = [u for u in m.units.values() if u["owner"] == pid]
        self.known = vision.known_at(m, pid)

    def near_hall(self, k):
        return min((dist(k, c) for c in self.hall_cells), default=99)

    # --- Settlers ------------------------------------------------------------------------------

    def settlers(self):
        m, pid = self.m, self.pid
        for u in [u for u in self.units if UNITS[u["type"]]["settler"]]:
            rots = [r for r in range(6) if not orders.found_problem(m, pid, u, r)]
            if rots:
                try_act(m, pid, "found", u["id"], rots[0])
                continue
            goal = self.city_site(u)
            if goal is not None:
                self.head_for(u, goal)
                continue
            options = [k for k in movement.reach(m, u["id"]) if not self.enemy_at(k)]
            if options:
                try_act(m, pid, "move", u["id"], self.rng.choice(sorted(options)))

    def city_site(self, u):
        """The nearest explored cell within CITY_RANGE where pid could found a city (as far as it
        knows), preferring about CITY_SPACING + 2 from its own Town Halls."""
        m, pid = self.m, self.pid
        explored = m.explored[pid] if m.fog else m.cells
        halls = [c for c, (_, stype) in self.known.items() if stype == TOWN_HALL]
        best = None
        for k in disk(CITY_RANGE, parse(u["at"])):
            if k not in explored or k not in m.cells or self.enemy_at(k):
                continue
            if any(dist(k, h) < orders.CITY_SPACING + 1 for h in halls):
                continue
            if not any(all(c in explored for c in footprint(TOWN_HALL, k, r)) and
                       not orders.site_problem(m, pid, TOWN_HALL, footprint(TOWN_HALL, k, r), seen=m.visible[pid])
                       for r in range(6)):
                continue
            value = dist(k, u["at"]) + (0.5 * abs(self.near_hall(k) - orders.CITY_SPACING - 2) if self.halls else 0)
            if best is None or value < best[0]:
                best = (value, k)
        return best and best[1]

    def enemy_at(self, k):
        m = self.m
        occ = m.unit_at.get(k)
        if occ is not None and m.units[occ]["owner"] != self.pid and vision.sees(m, self.pid, k):
            return True
        owner, _ = self.known.get(k, (None, None))
        return owner is not None and owner != self.pid

    # --- Research ------------------------------------------------------------------------------

    def research(self):
        have = set(self.m.players[self.pid]["advances"])
        options = [aid for aid, a in ADVANCES.items() if aid not in have and all(x in have for x in a["after"])]
        for aid in sorted(options, key=lambda a: (sum(ADVANCES[a]["cost"].values()), a)):
            if try_act(self.m, self.pid, "research", aid):
                return

    # --- Building ------------------------------------------------------------------------------

    def wants(self):
        m, pid = self.m, self.pid
        rep, stock = report(m, pid), logistics.stock(m, pid)
        have = Counter(s["type"] for s in self.mine + self.sites)
        adv = set(m.players[pid]["advances"])
        cities = len(self.halls)
        full = lambda r: rep["caps"].get(r, 0) - stock.get(r, 0) <= 4
        out = []
        if m.players[pid]["pop"] + 1 >= rep["housing"]:
            out.append("house" if stock.get("stone", 0) >= 6 else "hut")
        if rep["net"]["food"] <= 1:
            out.append("farm")
        if have["lumbermill"] < cities:
            out.append("lumbermill")
        if have["mine"] < cities:
            out.append("mine")
        if any(full(r) for r in ("wood", "stone", "metal")) and have["storage_yard"] < cities:
            out.append("storage_yard")
        if full("food") and have["granary"] < cities:
            out.append("granary")
        if m.turn >= 6 and not have["barracks"]:
            out.append("barracks")
        for stype, turn in (("market", 10), ("chapel", 12), ("college", 14)):
            if m.turn >= turn and have[stype] < (cities + 1) // 2:
                out.append(stype)
        if "bronze_working" in adv and not have["smithy"]:
            out.append("smithy")
        if "masonry" in adv and have["tower"] < cities:
            out.append("tower")
        if rep["idle"] > 1:
            out.append("farm")
        return out, rep["idle"]

    def builders(self):
        m, pid = self.m, self.pid
        waiting = [x for x in self.sites if x["id"] not in construction.forecast(m, pid)["works"]
                   and not construction.finished(x)]
        if not waiting:
            if any(not s["active"] for s in self.mine):
                try_act(m, pid, "staff", True)
            return
        working = staffing(m, pid)[0]
        jobs = [s for s in working if STRUCTURES[s["type"]]["jobs"] and not economy.output_keys(s["type"]) & {"food"}]
        if jobs:
            try_act(m, pid, "toggle", max(jobs, key=lambda s: s["n"])["id"])

    def build(self):
        if not self.halls:
            return
        wants, idle = self.wants()
        idle -= sum(STRUCTURES[x["type"]]["builders"] for x in self.sites if not construction.finished(x))
        built = claims = 0
        for stype in wants:
            d = STRUCTURES[stype]
            if built >= MAX_BUILDS or idle < 1:
                break
            if d["jobs"] + d["builders"] > idle:
                continue
            site = self.site(stype)
            if site is None:
                if stype in NEED_TERRAIN and claims < MAX_CLAIMS and self.claim_land(stype):
                    claims += 1
                continue
            if try_act(self.m, self.pid, "build", stype, site[0], site[1]):
                built += 1
                idle -= d["jobs"] + d["builders"]

    def free_cells(self):
        m = self.m
        return sorted(k for k, owner in m.territory.items() if owner == self.pid and k not in m.cell_structure
                      and k not in m.cell_site)

    def site(self, stype):
        """(at, rot) of the best place for stype, or None."""
        m, pid, d = self.m, self.pid, STRUCTURES[stype]
        pending = {c for b in m.orders[pid]["builds"] for c in b["cells"]}
        best = None
        for at in self.free_cells():
            for rot in range(6 if len(d["cells"]) > 1 else 1):
                cells = footprint(stype, at, rot)
                if any(m.territory.get(c) != pid for c in cells):
                    continue
                if orders.site_problem(m, pid, stype, cells, pending, m.visible[pid]):
                    continue
                touching = {n for c in cells for n in neighbors(c)} - set(cells)
                value = self.value(stype, cells, touching) - 0.3 * self.near_hall(at) + self.rng.random() * 0.1
                if best is None or value > best[0]:
                    best = (value, at, rot)
        return best and best[1:]

    def value(self, stype, cells, touching):
        terrain = self.m.cells
        if stype == "farm":
            return sum(2 if terrain[c] == "plains" else 1 for c in cells)
        if stype == "lumbermill":
            return sum(1 for n in touching if terrain.get(n) == "forest") * 2
        if stype == "windmill":
            return sum(1 for n in touching if self.m.structures.get(self.m.cell_structure.get(n), {}).get("type") == "farm")
        return 0

    def claim_land(self, stype):
        """Buy one cell of land (orders.claim) on the way to the nearest known land stype needs."""
        m, pid = self.m, self.pid
        want = NEED_TERRAIN.get(stype)
        known = m.explored[pid] if m.fog else m.cells
        targets = [k for k in known if m.cells[k] in want and m.territory.get(k) != pid]
        options = [k for k in sorted(known) if not orders.claim_problem(m, pid, k)]
        if not targets or not options:
            return False
        best = min(options, key=lambda k: (min(dist(k, t) for t in targets), self.near_hall(k), k))
        if report(m, pid)["net"]["gold"] < len(territory.claim_cells(m, best)) * territory.LAND_UPKEEP:
            return False  # can't keep paying for it
        return try_act(m, pid, "claim", best)

    # --- Recruiting ----------------------------------------------------------------------------

    def recruit(self):
        m, pid = self.m, self.pid
        p, rep = m.players[pid], report(m, pid)
        settlers = [u for u in self.units if UNITS[u["type"]]["settler"]]
        if self.halls and len(self.halls) + len(settlers) < CITIES and m.turn >= 5 and p["pop"] >= 5 \
                and rep["net"]["food"] >= 2:
            try_act(m, pid, "recruit", self.halls[0]["id"], "settlers")
        army = len([u for u in self.units if not UNITS[u["type"]]["settler"]])
        target = min(12, 1 + m.turn // 5 + len(self.threats()))
        if rep["net"]["gold"] < 0 and army >= 2:
            return
        archers = sum(1 for u in self.units if u["type"] == "archer")
        for s in sorted(self.mine, key=lambda s: s["type"] != "barracks"):
            if army >= target or p["pop"] < 3:
                return
            for ut in self.unit_choices(s, archers, army):
                if try_act(m, pid, "recruit", s["id"], ut):
                    army += 1
                    archers += ut == "archer"
                    break

    def unit_choices(self, s, archers, army):
        options = [u for u in STRUCTURES[s["type"]]["recruits"] if u != "settlers" and not UNITS[u]["naval"]]
        rank = {"knight": 0, "swordsman": 1, "catapult": 2, "archer": 3, "spearman": 4, "militia": 5}
        if archers * 3 >= army + 1:
            rank["archer"] = 6
        return sorted(options, key=lambda u: rank.get(u, 5))

    # --- Moving the army -----------------------------------------------------------------------

    def threats(self):
        m = self.m
        homes = [c for s in self.mine for c in s["cells"]]
        return [u["at"] for u in m.units.values() if u["owner"] != self.pid and vision.sees(m, self.pid, u["at"])
                and any(dist(u["at"], h) <= 5 for h in homes)]

    def army(self):
        m, pid = self.m, self.pid
        known = self.known
        threats = self.threats()
        army = [u for u in self.units if not UNITS[u["type"]]["settler"] and not UNITS[u["type"]]["naval"]]
        enemy = [c for c, (owner, stype) in known.items() if owner != pid]
        halls = [c for c in enemy if known[c][1] == TOWN_HALL]
        target = None
        if enemy and m.turn >= ATTACK_TURN and len(army) >= ATTACK_ARMY and self.hall_cells:
            target = min(halls or enemy, key=lambda c: (self.near_hall(c), c))
        scout = None if threats or (target and len(army) < 2 * ATTACK_ARMY) else \
            next(iter(sorted(army, key=lambda u: u["n"])), None)
        for u in army:
            if UNITS[u["type"]]["range"] and self.shoot(u, known):
                continue
            if threats:
                goal = min(threats, key=lambda k: (dist(k, u["at"]), k))
            elif u is scout:
                self.explore(u)
                continue
            elif target:
                goal = target
            else:
                if self.hall_cells and self.near_hall(u["at"]) > 3:
                    goal = min(self.hall_cells, key=lambda c: (dist(c, u["at"]), c))
                else:
                    try_act(m, pid, "hold", u["id"])
                    continue
            self.head_for(u, goal)

    def shoot(self, u, known):
        m, pid, rng = self.m, self.pid, UNITS[u["type"]]["range"]
        targets = [x["at"] for x in m.units.values() if x["owner"] != pid and vision.sees(m, pid, x["at"])]
        targets += [c for c, (owner, stype) in known.items() if owner != pid and STRUCTURES[stype]["hp"]]
        targets = sorted((k for k in targets if dist(k, u["at"]) <= rng), key=lambda k: (dist(k, u["at"]), k))
        return bool(targets) and try_act(m, pid, "shoot", u["id"], targets[0])

    def head_for(self, u, goal):
        reach = movement.reach(self.m, u["id"])
        if goal in reach:
            try_act(self.m, self.pid, "move", u["id"], goal)
            return
        options = [k for k in reach if dist(k, goal) < dist(u["at"], goal)]
        if options:
            try_act(self.m, self.pid, "move", u["id"], min(options, key=lambda k: (dist(k, goal), k)))

    def explore(self, u):
        goal = explore.target(self.m, u["id"])
        if goal:
            try_act(self.m, self.pid, "move", u["id"], goal)
