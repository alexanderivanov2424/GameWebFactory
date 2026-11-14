"""DISABLED (2026-11-09): written for the worker-placement v4 rules (shared stockpile, hauling,
enemies); not updated for the per-player trading redesign, so it no longer runs against the current
Match. Kept for reference; tests/playtest.py exits before importing it.

Bastion: playtest bots (test-only: tests/ is never deployed, and this isn't a test_*.py file, so
the test runner doesn't collect it). The user asked for bots to playtest and balance the game;
tests/playtest.py drives them. They play through the Match API only (legal moves from units,
hauling and tiles, build spots from board.check + economy.output like views.build_targets but
only near the city; Match methods to act) and never change Match internals.

    bot = Bot(match, pid, rng, stats, style="good" | "passive")
    bot.place(ready=True)  place phase: put units on buildings / enemies (the rest stay haulers),
                     then ready (the last ready runs the resolution)
    bot.act()        act phase, on this bot's turn: hauls, cards, upgrades, building, roads,
                     market, soldier strikes (the driver calls match.end_turn after it: unused
                     haulers haul on their own)
    Stats()          counters every bot of one game writes to (playtest.py reads them)

"good": a heuristic player. Placement is greedy over a whole-round plan: each step tries one
more unit on every legal target and keeps the one that adds the most value to a model of the
round (buildings without inputs work first, then input users with the stockpile they'd find,
then the team's haulers carry the most valuable piles; goods in the stockpile count fully,
goods left in stores STORED (0.3)). Values per output: food is worth more when the stockpile won't
cover the next rounds, scarce materials more than plentiful ones, a strike on an active enemy
a lot. On its turn it hauls by value (and leaves the rest to End turn's auto-haul once its pick
is the auto pick and nothing in hand waits for materials), upgrades the building whose level
pays most over the rounds left with spare tools, builds blueprints at the best-scoring spot
(output, link, neighbours, keep distance; never one that cuts roads off), holds houses until
food keeps up, lays roads to link what's cut off (producers whose terrain near the city is used up
look over the whole map), pays curses unless the city would go hungry, plays Tax only with
fewer than 2 Unrests in its deck, and buys from a want list driven by the food margin,
materials, idle haulers and enemies (at most 2 rerolls a round). It never builds walls.
"passive": fills the farms and lumbermills, fights with everything else, hauls on End turn,
never builds, upgrades or buys.
Both are deterministic (the match rng is seeded; ties break by board order): a seed gives the same game.
"""

import math
from collections import Counter, defaultdict, deque

from gamekit import LobbyError

from games.bastion.logic import economy, food, hauling, tiles, units
from games.bastion.logic.cards import CARDS
from games.bastion.logic.structures import GOODS, STRUCTURES

BASE_VALUE = {"wood": 1.0, "stone": 1.3, "ore": 0.6, "wheat": 1.2, "bread": 2.4, "tools": 1.8, "gold": 1.2}
TARGET = {"wood": 8, "stone": 6, "gold": 6, "tools": 4}  # stockpile the good bot likes to keep
STORED = 0.3  # worth of a good left waiting in a building, against one in the stockpile


class Stats:
    def __init__(self):
        self.produced = Counter()  # round -> goods made (stockpile or store)
        self.stored = Counter()  # round -> goods the resolution put into building stores
        self.hauled = Counter()  # round -> goods hauled (manual + auto)
        self.haul_units = Counter()  # round -> hauls made (manual + auto)
        self.auto_hauls = Counter()  # round -> hauls made by End turn's auto-haul
        self.haulers = Counter()  # round -> haulers the team had after the resolution
        self.gold_in = 0
        self.gold_out = defaultdict(int)  # what gold went to
        self.upgrades = Counter()  # level reached -> times
        self.tools_upgrades = 0  # tools spent on upgrades
        self.tools_sold = 0
        self.built = Counter()
        self.bought = Counter()
        self.work_kinds = Counter()  # building kind -> units placed on it (all rounds)
        self.fight_units = 0
        self.work_units = 0
        self.worked = 0  # buildings worked (sum over rounds)
        self.short_units = 0  # placed units that couldn't work (inputs short) and hauled instead
        self.rerolls = 0
        self.idle = Counter()  # round -> haulers with nothing to carry


def goods_total(match):
    return sum(match.stock[g] for g in GOODS) + sum(s.stored() for s in match.board.structures.values())


def keep_of(board):
    return next((s for s in board.structures.values() if s.kind == "keep"), None)


def makes(spec):
    return next(iter(spec["work"]["makes"])) if spec["work"] else None


def team_cards(match):
    found = Counter()
    for seat in match.seats.values():
        for c in seat.all_cards():
            found[c["card"]] += 1
    return found


def kinds_on_board(match):
    return Counter(s.kind for s in match.board.structures.values())


def full_output(board, s):
    """What s makes with every cell worked (its level included)."""
    return economy.amount(board, s, max(1, economy.capacity(s)))[0]


def food_capacity(match):
    """Wheat-equivalent a round the city's food buildings make with every cell worked (bakeries
    count their bread less the wheat they use), plus the keep's income."""
    total = 0
    for s in match.board.structures.values():
        if not s.spec["work"] or s.ruined or s.plague is not None:
            continue
        key = makes(s.spec)
        if key == "wheat":
            total += full_output(match.board, s)
        elif key == "bread":
            cells = economy.capacity(s)
            total += full_output(match.board, s) * food.FEEDS["bread"] / food.FEEDS["wheat"] - cells
    for s in match.board.structures.values():
        total += s.spec["income"].get("wheat", 0) + s.spec["income"].get("bread", 0) * 2
    return total


def food_margin(match):
    """Wheat a round the city's food buildings (all worked) make beyond what it eats."""
    return food_capacity(match) - need_per_round(match)


def need_per_round(match):
    return match.population() / food.FEEDS["wheat"]


def auto_haul_preview(match, pid):
    """(hauls, goods) End turn's auto-haul would make for pid now (nothing changed)."""
    board = match.board
    stores = {uid: dict(s.store) for uid, s in hauling.sources(board).items()}
    hauls = goods = 0
    for i in range(match.seats[pid].haulers):
        live = {uid: st for uid, st in stores.items() if sum(st.values())}
        if not live:
            break
        uid = max(live, key=lambda u: (sum(live[u].values()), -u))
        cap = hauling.capacity(board, match.hauled + i)
        for good, n in sorted(live[uid].items(), key=lambda kv: (-kv[1], GOODS.index(kv[0]))):
            moved = min(n, cap)
            cap -= moved
            live[uid][good] -= moved
            goods += moved
            if cap <= 0:
                break
        hauls += 1
    return hauls, goods


# --- roads -----------------------------------------------------------------------------------

def connected_cells(board, reach):
    depots = board.depot_cells()
    return lambda c: bool(board.neighbors([c]) & depots) or bool(board.neighbors([c]) & reach)


def road_path(board, cells, limit=24):
    """The empty cells to pave so `cells` gets a road link (None if no path within limit)."""
    reach = board.road_reach()
    ok = connected_cells(board, reach)
    roads = board.roads
    dist, prev = {}, {}
    dq = deque()
    for c in sorted(board.neighbors(cells)):
        if c in roads or board.empty(c):
            d = 0 if c in roads else 1
            if c not in dist or d < dist[c]:
                dist[c], prev[c] = d, None
                (dq.appendleft if d == 0 else dq.append)(c)
    seen = set()
    while dq:
        c = dq.popleft()
        if c in seen:
            continue
        seen.add(c)
        if dist[c] > limit:
            break
        if ok(c):
            path = []
            while c is not None:
                if c not in roads:
                    path.append(c)
                c = prev[c]
            return path[::-1]
        for n in sorted(board.neighbors([c])):
            if n in seen or not (n in roads or board.empty(n)):
                continue
            d = dist[c] + (0 if n in roads else 1)
            if n not in dist or d < dist[n]:
                dist[n], prev[n] = d, c
                (dq.appendleft if n in roads else dq.append)(n)
    return None


def linked_after(board, cells):
    """How many buildings would still have a road or depot link if a building covered `cells`
    (its roads gone), the same way board.link counts them."""
    covered = set(cells)
    roads = board.roads - covered
    depots = board.depot_cells()
    frontier = [c for c in roads if board.neighbors([c]) & depots]
    reach = set(frontier)
    while frontier:
        nxt = []
        for x, y in frontier:
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                c = (x + dx, y + dy)
                if c in roads and c not in reach:
                    reach.add(c)
                    nxt.append(c)
        frontier = nxt
    return sum(1 for st in board.structures.values()
               if board.neighbors(st.cells) & (depots | reach))


def net_distance(board):
    """{empty cell: road tiles needed to link a building next to it} (1 = right next to the network)."""
    reach = board.road_reach()
    ok = connected_cells(board, reach)
    dist = {}
    frontier = [(x, y) for y in range(board.height) for x in range(board.width) if board.empty((x, y)) and ok((x, y))]
    for c in frontier:
        dist[c] = 1
    while frontier:
        nxt = []
        for c in frontier:
            for n in board.neighbors([c]):
                if n not in dist and board.empty(n):
                    dist[n] = dist[c] + 1
                    nxt.append(n)
        frontier = nxt
    return dist


# --- the bot ---------------------------------------------------------------------------------

class Bot:
    def __init__(self, match, pid, rng, stats, style="good"):
        self.match = match
        self.pid = pid
        self.rng = rng
        self.stats = stats
        self.style = style
        self._spot_cache = {}

    @property
    def board(self):
        return self.match.board

    def reach(self):
        board = self.match.board
        cached = self._spot_cache.get("reach")
        if not cached or cached[0] != board.version:
            cached = self._spot_cache["reach"] = (board.version, board.road_reach())
        return cached[1]

    def link_of(self, s):
        """board.link(s) with the road reach cached per board version."""
        return self.match.board.link(s, self.reach())

    def rounds_left(self):
        """Rough rounds the game still has (the last enemy arrives, then a few rounds to beat it)."""
        m = self.match
        return max(2, m.last_arrival() + 4 - m.round)

    # --- values -----------------------------------------------------------------------------

    def blueprint_demand(self):
        """Materials the team's blueprints (in every hand) still need."""
        need = Counter()
        for seat in self.match.seats.values():
            for c in seat.hand:
                card = CARDS[c["card"]]
                if card["kind"] == "build":
                    need.update(STRUCTURES[card["structure"]]["cost"])
        return need

    def values(self, planned=None):
        """Worth of one more of each output now. planned: expected stockpile changes this round."""
        m = self.match
        planned = planned or Counter()
        demand = self.blueprint_demand()
        for foe in m.foes:  # enemies beaten with resources (Frost Witch: wood)
            if foe.active and foe.defeat.get("resources"):
                for r, n in foe.defeat["resources"].items():
                    demand[r] += n * min(foe.hp, 3)
        v = dict(BASE_VALUE)
        for r, target in TARGET.items():
            want = target + demand.get(r, 0)
            have = m.stock[r] + planned.get(r, 0)
            v[r] *= min(2.0, max(0.4, 1 + (want - have) / max(1, want)))
        kinds = kinds_on_board(m)
        if not kinds.get("smithy"):
            v["ore"] = 0.1
        per_round = max(1.0, need_per_round(m))
        have = m.stock["wheat"] + planned.get("wheat", 0) + 2 * (m.stock["bread"] + planned.get("bread", 0))
        cover = have / per_round  # rounds the stockpile feeds everyone
        if cover < 1.0:
            v["wheat"] = 3.2
        elif cover < 2.0:
            v["wheat"] = 2.2
        elif cover < 3.5:
            v["wheat"] = 1.4
        else:
            v["wheat"] = 0.6
        v["bread"] = v["wheat"] * food.FEEDS["bread"] / food.FEEDS["wheat"]
        fightable = any(f.active and f.fightable for f in m.foes)
        v["soldiers"] = 2.0 if fightable else 0.5
        missing = m.keep_max - m.keep
        v["keep"] = 0.0 if missing <= 0 else (1.0 + 2.0 * missing / m.keep_max)
        v["cure"] = 3.5 if m.plagued() else 0.0
        return v

    def strike_value(self, foe):
        m = self.match
        deadline = m.last_arrival() + 6 - m.round
        value = 2.6
        if deadline <= 4:
            value += 2.0
        value += 2.0 * (m.keep_max - m.keep) / m.keep_max
        return value

    # --- place phase ------------------------------------------------------------------------

    def place(self, ready=True):
        m = self.match
        if self.style == "passive":
            self.place_passive()
        else:
            self.place_good()
        if ready:
            m.ready(self.pid)

    def place_passive(self):
        m = self.match
        while units.haulers(m, self.pid) > 0:
            options = units.targets(m)
            pick = None
            for t in options:
                if t.startswith("s"):
                    s = m.board.structures[int(t[1:])]
                    if s.kind in ("farm", "lumbermill"):
                        pick = t
                        break
            if pick is None:
                fights = [t for t in options if t.startswith("fight") or t.startswith("raze")]
                if not fights:
                    return  # the rest haul
                pick = fights[0]
            m.place(self.pid, pick)

    def model(self, plan, vals):
        """Value of a whole round's placements `plan` ({target: units}, the team's): the
        resolution (no-input buildings, then input users, then fights), then every hauler
        carrying the most valuable pile it can reach."""
        m = self.match
        board = m.board
        stock = dict(m.stock)
        stores = {}
        value = 0.0
        team = sum(seat.units for seat in m.seats.values())
        placed = sum(plan.values())
        idle = 0
        buildings = []
        for target, n in plan.items():
            if target.startswith("s") and n:
                s = board.structures[int(target[1:])]
                buildings.append((bool(s.spec["work"]["uses"]), s.uid, s, n))
        buildings.sort(key=lambda b: b[:2])
        for _, uid, s, n in buildings:
            spec = s.spec["work"]
            link = self.link_of(s)
            able = n
            if spec["uses"]:
                able = 0 if not link else min(n, *(stock.get(k, 0) // c for k, c in spec["uses"].items()))
            idle += n - able
            if not able:
                continue
            for k, c in spec["uses"].items():
                stock[k] -= c * able
            made = self._amount(s, able)
            key = makes(s.spec)
            if key in GOODS:
                if link == "depot":
                    stock[key] += made
                else:
                    st = stores.setdefault(uid, dict(s.store))
                    kept = min(made, economy.STORE_CAP - sum(st.values()))
                    if kept > 0:
                        st[key] = st.get(key, 0) + kept
                    if not link:
                        value -= kept * vals.get(key, 1.0) * (STORED - 0.1)  # nobody can haul it
            elif key == "gold":
                stock["gold"] += made
            elif key == "soldiers":
                value += made * vals["soldiers"]
            elif key == "keep":
                value += min(made, m.keep_max - m.keep) * vals["keep"]
            elif key == "cure":
                value += min(made, len(m.plagued())) * vals["cure"]
        for target, n in plan.items():
            if target.startswith("fight") and n:
                foe = m.foes[int(target[5:])]
                left = foe.hp * foe.defeat["soldiers"] - foe.strikes
                value += min(n, max(0, left)) * self.strike_value(foe)
            elif target.startswith("raze") and n:
                x, y = (int(v) for v in target[4:].split(","))
                blight = board.blights[(x, y)]
                if blight["lair"]:
                    value += self.strike_value(m.foes[blight["foe"]]) + 0.3
                else:
                    hurt = sum(1 for uid in {board.at[c] for c in board.neighbors([(x, y)]) if c in board.at}
                               if board.structures[uid].spec["work"])
                    value += 1.0 + 1.2 * hurt
        # hauling: the team's haulers take the most valuable piles they can reach
        haulers = team - placed + idle
        reach = self.reach()
        final = stores  # {uid: store after this round} for every building touched
        pool = []
        for uid, s in sorted(board.structures.items()):
            st = final.get(uid, s.store)
            if st and sum(st.values()) and board.link(s, reach):
                final[uid] = dict(st)
                pool.append(uid)
        for i in range(haulers):
            cap = hauling.capacity(board, m.hauled + i)
            best, best_v, best_take = None, 0, None
            for uid in pool:
                take, room = {}, cap
                for good, k in sorted(final[uid].items(), key=lambda kv: (-kv[1], GOODS.index(kv[0]))):
                    moved = min(k, room)
                    if moved <= 0:
                        break
                    take[good] = moved
                    room -= moved
                worth = sum(k * vals.get(g, 1.0) for g, k in take.items())
                if worth > best_v:
                    best, best_v, best_take = uid, worth, take
            if best is None:
                break
            for g, k in best_take.items():
                final[best][g] -= k
                stock[g] += k
                if not final[best][g]:
                    del final[best][g]
        for g in list(GOODS) + ["gold"]:
            value += (stock.get(g, 0) - m.stock[g]) * vals.get(g, 1.0)
        for uid, st in final.items():
            before = board.structures[uid].store
            for g in GOODS:
                value += (st.get(g, 0) - before.get(g, 0)) * vals.get(g, 1.0) * STORED
        return value

    def _amount(self, s, n):
        key = (self.match.board.version, s.uid, s.level, n)
        cache = self._spot_cache.setdefault("amount", {})
        if key not in cache:
            if len(cache) > 2000:
                cache.clear()
            cache[key] = economy.amount(self.match.board, s, n)[0]
        return cache[key]

    def planned_stock(self, plan):
        """Stockpile change from the work in plan (for the values of the next pick)."""
        m = self.match
        delta = Counter()
        for target, n in plan.items():
            if not target.startswith("s"):
                continue
            s = m.board.structures[int(target[1:])]
            for k, c in s.spec["work"]["uses"].items():
                delta[k] -= c * n
            key = makes(s.spec)
            delta[key] += self._amount(s, n)
        return delta

    def place_good(self):
        m = self.match
        while units.haulers(m, self.pid) > 0:
            plan = {t: sum(by.values()) for t, by in m.placed.items()}
            vals = self.values(self.planned_stock(plan))
            base = self.model(plan, vals)
            best, best_gain = None, 0.05
            for t in units.targets(m):
                trial = dict(plan)
                trial[t] = trial.get(t, 0) + 1
                gain = self.model(trial, vals) - base
                if gain > best_gain:
                    best, best_gain = t, gain
            if best is None:  # nothing beats hauling: the rest haul
                return
            m.place(self.pid, best)

    # --- act phase --------------------------------------------------------------------------

    def act(self):
        m = self.match
        if self.style == "passive":
            self.pay_curses(passive=True)
            self.spend_soldiers()
            return
        self.haul_pass()
        self.play_actions()
        self.pay_curses()
        self.upgrade_pass()
        self.build_pass()
        self.link_pass()
        self.special_damage()
        self.spend_soldiers()
        self.buy_pass()
        self.play_actions(late=True)
        self.build_pass()
        self.upgrade_pass()

    def haul_pass(self):
        """Haul by value while it matters (the pick differs from the auto pick, or a blueprint
        in hand waits for materials); End turn hauls the rest."""
        m = self.match
        seat = m.seats[self.pid]
        while seat.haulers > 0 and m.result is None:
            found = hauling.sources(m.board)
            if not found:
                return
            vals = self.values()
            cap = hauling.capacity(m.board, m.hauled)
            pick = max(found.values(), key=lambda s: (sum(n * vals.get(g, 1.0) for g, n in hauling.carry(s, cap).items()),
                                                      s.stored(), -s.uid))
            auto = hauling.best_source(m.board)
            need = self.blueprint_demand()
            waiting = any(m.stock[g] < n for g, n in need.items() if g in GOODS)
            if pick is auto and not waiting:
                return
            goods = sum(m.stock[g] for g in GOODS)
            m.haul(self.pid, pick.uid)
            self.stats.hauled[m.round] += sum(m.stock[g] for g in GOODS) - goods
            self.stats.haul_units[m.round] += 1

    def tool_reserve(self):
        need = self.blueprint_demand().get("tools", 0)
        if kinds_on_board(self.match).get("barracks"):
            need += 1
        return need

    def upgrade_pass(self):
        m = self.match
        if m.result is not None or m.turn() != self.pid:
            return
        while True:
            spare = m.stock["tools"] - self.tool_reserve()
            vals = self.values()
            left = self.rounds_left()
            best, best_score = None, 0
            for s in m.board.structures.values():
                cost = economy.upgrade_cost(s)
                if not cost or cost > spare or economy.upgrade_reason(s, m.stock):
                    continue
                key = makes(s.spec)
                if key in ("cure", "keep"):
                    continue
                use = 1.0 if s.worked else 0.4  # worked this round: likely worked every round
                if s.spec["work"]["uses"]:
                    use *= 0.8
                gain = use * left * min(vals.get(key, 1.0), 2.5)
                score = gain / (cost * vals["tools"])
                if score > best_score:
                    best, best_score = s, score
            if best is None or best_score < 1.5:
                return
            cost = economy.upgrade_cost(best)
            m.upgrade(self.pid, uid=best.uid)
            self.stats.upgrades[best.level] += 1
            self.stats.tools_upgrades += cost

    # --- cards ------------------------------------------------------------------------------

    def hand(self):
        return list(self.match.seats[self.pid].hand)

    def play(self, uid, **kw):
        m = self.match
        gold = m.stock["gold"]
        m.play(self.pid, uid, **kw)
        delta = m.stock["gold"] - gold
        if delta > 0:
            self.stats.gold_in += delta
        elif delta < 0:
            self.stats.gold_out["cards"] -= delta

    def play_actions(self, late=False):
        m = self.match
        vals = self.values()
        for c in self.hand():
            card = CARDS[c["card"]]
            if card["kind"] != "action" or m.result is not None:
                continue
            if any(m.stock[r] < n for r, n in card["cost"].items()):
                continue
            cid = c["card"]
            try:
                if card["draw"]:
                    self.play(c["uid"])
                elif cid == "levy":
                    self.play(c["uid"])
                elif cid == "tax":
                    unrest = sum(1 for h in self.match.seats[self.pid].all_cards() if h["card"] == "unrest")
                    if m.stock["gold"] < 10 and unrest < 2:
                        self.play(c["uid"])
                elif cid == "sell":
                    if (late and m.stock["tools"] > self.tool_reserve() + 6) or m.stock["gold"] < 2 <= m.stock["tools"]:
                        self.play(c["uid"])
                        self.stats.tools_sold += 1
                elif cid == "trade-fair":
                    if vals["wheat"] <= 0.6:
                        self.play(c["uid"])
                elif cid == "militia":
                    if any(f.active and f.fightable for f in m.foes) and vals["wheat"] < 2:
                        self.play(c["uid"])
                elif card["repair"]:
                    ruined = [s for s in m.board.structures.values() if s.ruined]
                    if ruined and m.stock["wood"] >= len(ruined[0].ruined) + 1:
                        s = max(ruined, key=lambda s: (s.spec["population"] or 0) + (2 if s.spec["work"] else 0))
                        if m.stock["wood"] >= len(s.ruined):
                            x, y = sorted(s.ruined)[0]
                            self.play(c["uid"], x=x, y=y)
                elif card["cure"]:
                    sick = sorted(m.plagued(), key=lambda s: makes(s.spec) not in ("wheat", "bread"))
                    if sick:
                        x, y = sick[0].cells[0]
                        self.play(c["uid"], x=x, y=y)
                elif card["trash"]:
                    junk = [h["uid"] for h in self.hand() if h["card"] in ("tax",) and h["uid"] != c["uid"]]
                    if junk and m.stock["gold"] >= 8:
                        self.play(c["uid"], remove=junk[:card["trash"]])
            except LobbyError:  # e.g. nothing left to repair at that spot: skip the card
                pass

    def pay_curses(self, passive=False):
        m = self.match
        vals = self.values()
        for c in self.hand():
            card = CARDS[c["card"]]
            if card["kind"] != "curse":
                continue
            pay = card["pay"]
            if any(m.stock[r] < n for r, n in pay.items()):
                continue
            if not passive and "wheat" in pay and vals["wheat"] >= 3.2:
                continue  # food first: the city would go hungry
            self.play(c["uid"])

    # --- building ---------------------------------------------------------------------------

    def priority(self, kind):
        """Which blueprint to build first when materials are short."""
        m = self.match
        food_short = food_margin(m) < 1
        order = {"farm": 0 if food_short else 3, "quarry": 1, "lumbermill": 1, "house": 2 if not food_short else 5,
                 "bakery": 3, "workshop": 4, "storage-yard": 4, "apothecary": 1 if m.plagued() else 6,
                 "market": 6, "carriage": 6, "chapel": 6, "barracks": 5, "watchtower": 7, "mine": 7, "smithy": 7}
        return order.get(kind, 8)

    def build_pass(self):
        m = self.match
        if m.result is not None or m.turn() != self.pid:
            return
        built = True
        while built:
            built = False
            blueprints = [c for c in self.hand() if CARDS[c["card"]]["kind"] == "build"]
            blueprints.sort(key=lambda c: self.priority(CARDS[c["card"]]["structure"]))
            reserved = Counter()
            for c in blueprints:
                kind = CARDS[c["card"]]["structure"]
                cost = STRUCTURES[kind]["cost"]
                if kind == "house" and not self.house_ok(1):
                    continue  # no food or work for 2 more people yet: hold the card
                if any(m.stock[r] - reserved[r] < n for r, n in cost.items()):
                    reserved.update(cost)  # wait for it: don't spend its materials on lower ones
                    continue
                spot = self.best_spot(kind)
                if spot is None:
                    continue
                rot, x, y = spot
                cell = m.board.footprint(kind, rot, x, y)[0]
                self.play(c["uid"], x=x, y=y, rotation=rot)
                self.stats.built[kind] += 1
                self.link(m.board.structures.get(m.board.at.get(cell)))
                built = True
                break

    def spot_extras(self):
        """Per board version: network distance map and the keep cell."""
        version = self.board.version
        cached = self._spot_cache.get("extras")
        if cached and cached[0] == version:
            return cached[1]
        board = self.board
        keep = keep_of(board)
        extras = {"net": net_distance(board), "reach": board.road_reach(), "depots": board.depot_cells(),
                  "keep": keep.cells[0] if keep else (board.width // 2, board.height // 2)}
        self._spot_cache["extras"] = (version, extras)
        return extras

    def neighbour_effect(self, kind, around):
        """Output change for existing buildings next to a new `kind` there."""
        board = self.board
        total = 0.0
        for uid in {board.at[c] for c in around if c in board.at}:
            t = board.structures[uid]
            if not t.spec["work"]:
                continue
            for cond in t.spec["bonuses"]:
                if cond["near"] != kind:
                    continue
                count = board.near(t.cells, kind)
                if "each" in cond:
                    if count < cond["max"]:
                        total += cond["each"]
                elif count == cond["min"] - 1:
                    total += cond["bonus"]
        return total

    def candidates(self, kind, ex, wide=False):
        """Legal spots near the city, or anywhere when wide (same rules as views.build_targets):
        (rotation, x, y, cells, output)."""
        board, spec = self.board, STRUCTURES[kind]
        if "near" not in ex:
            used = [c for s in board.structures.values() for c in s.cells] + list(board.roads)
            ex["near"] = (min(x for x, _ in used) - 5, max(x for x, _ in used) + 2,
                          min(y for _, y in used) - 5, max(y for _, y in used) + 2)
        x0, x1, y0, y1 = (0, board.width - 1, 0, board.height - 1) if wide else ex["near"]
        rots = 1 if len(spec["pieces"][0]) == 1 else 4
        for rot in range(rots):
            for y in range(max(0, y0), min(board.height, y1 + 1)):
                for x in range(max(0, x0), min(board.width, x1 + 1)):
                    try:
                        cells = board.check(kind, rot, x, y)
                    except LobbyError:
                        continue
                    out = economy.output(board, kind, cells)[0] if spec["work"] else -1
                    yield rot, x, y, cells, out

    def best_spot(self, kind):
        """(rotation, x, y) of the best legal spot for `kind`, or None. A cheap score for every
        spot near the city, then the costly terms (cutting road links) for the best few."""
        board, spec = self.board, STRUCTURES[kind]
        ex = self.spot_extras()
        if kind in ex.setdefault("best", {}):
            return ex["best"][kind]
        found = self.find_spot(kind, ex)
        if found is None and spec["requires"]:  # a producer whose terrain near the city is used up
            found = self.find_spot(kind, ex, wide=True)
        ex["best"][kind] = found
        return found

    def find_spot(self, kind, ex, wide=False):
        board, spec = self.board, STRUCTURES[kind]
        key = makes(spec)
        kx, ky = ex["keep"]
        if spec["protects"]:
            open_cells = [c for s in board.structures.values() if s.kind != "keep" for c in s.cells
                          if not board.protected(c)]
        scored = []
        for rot, x, y, cells, out in self.candidates(kind, ex, wide):
            around = board.neighbors(cells)
            score = 0.0
            near_depot = bool(around & ex["depots"])
            linked = near_depot or bool(around & ex["reach"])
            if spec["work"]:
                if out <= 0:
                    continue
                score += 2.0 * out
                if key in GOODS or spec["work"]["uses"]:
                    if near_depot:
                        score += 2.0 if key in GOODS else 0.5
                    elif linked:
                        score += 1.0
                    else:
                        score -= 0.6 * min((ex["net"].get(c, 6) for c in around), default=30)
            score += 1.5 * self.neighbour_effect(kind, around)
            if kind == "house" or not spec["work"]:
                if near_depot:
                    score -= 2.0
                wild = sum(1 for cx, cy in around if board.terrain[cy][cx] in ("forest", "mountain"))
                score -= 0.4 * wild
            if kind == "house":
                score += 0.3 * board.near(cells, "house")
                score -= 0.15 * board.near(cells, "farm")
            if kind == "storage-yard":
                for uid in {board.at[c] for c in around if c in board.at}:
                    t = board.structures[uid]
                    if t.spec["work"] and makes(t.spec) in GOODS and self.link_of(t) != "depot":
                        score += 3.0
                score += 0.3 * sum(1 for cx, cy in around if board.terrain[cy][cx] in ("forest", "mountain"))
                if not linked:
                    score -= 0.5 * min((ex["net"].get(c, 6) for c in around), default=30)
            if kind == "carriage" and near_depot:
                score -= 2.0
            if spec["protects"]:
                r = spec["protects"]
                score += 0.5 * sum(1 for cx, cy in open_cells
                                   if any(abs(cx - px) <= r and abs(cy - py) <= r for px, py in cells))
            score -= 0.08 * (abs(x - kx) + abs(y - ky))
            if any(c in board.roads for c in cells):
                score -= 1.0
            scored.append((score, rot, x, y, cells))
        scored.sort(key=lambda t: -t[0])
        best, best_score = None, -99
        for score, rot, x, y, cells in scored[:12]:
            if any(c in board.roads for c in cells):
                if linked_after(board, cells) < ex.setdefault("linked", linked_after(board, ())):
                    score -= 8.0  # cuts buildings off the road network
            if score > best_score:
                best, best_score = (rot, x, y), score
        if best is None or (spec["work"] and best_score < (-6 if wide else 0)):
            return None
        return best

    def link(self, s):
        """Lay roads so s is linked (if it needs one and the team can pay)."""
        m = self.match
        if s is None or not s.spec["work"] or s.kind == "keep":
            return
        key = makes(s.spec)
        if not (key in GOODS or s.spec["work"]["uses"]) or self.link_of(s):
            return
        path = road_path(m.board, s.cells)
        if not path:
            return
        batches = math.ceil(max(0, len(path) - m.tile_stock["road"]) / tiles.BATCH)
        if m.stock["gold"] < batches:
            return
        for x, y in path:
            gold = m.stock["gold"]
            m.place_tile(self.pid, "road", x, y)
            self.stats.gold_out["roads"] += gold - m.stock["gold"]

    def link_pass(self):
        m = self.match
        for s in list(m.board.structures.values()):
            if m.result is not None:
                return
            self.link(s)

    # --- enemies ----------------------------------------------------------------------------

    def special_damage(self):
        m = self.match
        for foe in m.foes:
            if not foe.active:
                continue
            res = foe.defeat.get("resources")
            if res:
                while foe.active and all(m.stock[r] >= n + (2 if r == "wood" else 0) for r, n in res.items()):
                    m.strike(self.pid, foe.index, "resources")
                    if m.result is not None:
                        return

    def spend_soldiers(self):
        m = self.match
        for foe in m.foes:
            if m.result is not None:
                return
            if foe.active and foe.fightable:
                per = foe.defeat["soldiers"]
                while foe.active and m.soldiers >= max(1, per - foe.strikes):
                    m.strike(self.pid, foe.index, "soldiers")
                    if m.result is not None:
                        return
        for (x, y), blight in sorted(m.board.blights.items()):
            if m.result is not None:
                return
            cost = (m.foes[blight["foe"]].raze if blight["lair"] else 1) - blight["strikes"]
            if (x, y) in m.board.blights and m.soldiers >= cost:
                m.raze(self.pid, x, y)

    # --- market -----------------------------------------------------------------------------

    def slots(self):
        """Useful places for units in a round: every cell of a workable building, a hauler per
        building that stores its goods, and a few fighters while a fightable enemy is here."""
        m = self.match
        count = 0
        for s in m.board.structures.values():
            if s.spec["work"] and not s.ruined and s.plague is None:
                if makes(s.spec) in ("cure", "keep"):
                    continue
                count += economy.capacity(s)
                if makes(s.spec) in GOODS and self.link_of(s) == "road":
                    count += 1
        if any(f.active and f.fightable for f in m.foes):
            count += 4
        count += sum(1 for b in m.board.blights.values())
        return count

    def house_ok(self, extra=0):
        """Another `extra` houses would have food and work."""
        m = self.match
        per = STRUCTURES["house"]["population"]
        units_next = m.population() + per * extra
        idle = self.stats.idle.get(m.round - 1, 0) if m.round > 1 else 0
        stocked = (m.stock["wheat"] + 2 * m.stock["bread"]) / max(1.0, need_per_round(m))
        food_ok = food_margin(m) >= per * extra / food.FEEDS["wheat"] - (1.5 if stocked >= 2 else 0.5)
        planned = sum(len(STRUCTURES[CARDS[cid]["structure"]]["pieces"][0]) * n for cid, n in team_cards(m).items()
                      if CARDS[cid]["kind"] == "build" and STRUCTURES[CARDS[cid]["structure"]]["work"])
        soon = m.foes and m.round >= m.foes[0].arrives - 2 and any(f.state != "defeated" for f in m.foes)
        work_ok = soon or self.slots() + planned >= units_next - 1
        return food_ok and work_ok and idle <= 2

    def wants(self):
        """[(card id, priority)] best first: a target count per kind that grows with the city."""
        m = self.match
        kinds = kinds_on_board(m)
        cards = team_cards(m)
        have = lambda k: kinds.get(k, 0) + cards.get(f"plan-{k}", 0)
        pop = m.population()
        houses = kinds.get("house", 0)
        margin = food_margin(m) + 2 * cards.get("plan-farm", 0) + 3 * cards.get("plan-bakery", 0)
        wants = []
        if any(f.active and f.defeat.get("cure") for f in m.foes) or m.plagued():
            if cards.get("remedy", 0) < 2:
                wants.append(("remedy", 9))
            if not have("apothecary"):
                wants.append(("plan-apothecary", 8))
        if margin < 1:
            wants.append(("plan-farm", 9))
        elif margin < 3:
            wants.append(("plan-farm", 7))
        if cards.get("plan-house", 0) == 0 and self.house_ok(1):
            wants.append(("plan-house", 8))
        targets = {
            "quarry": (1 + pop // 8, 9 if not have("quarry") else 6),
            "lumbermill": (1 + pop // 7, 7),
            "workshop": (1 if pop >= 4 else 0, 7),
            "bakery": ((pop >= 6) + (pop >= 11), 7),
            "storage-yard": ((pop >= 6) + (pop >= 11), 5),
            "carriage": ((pop >= 6) + (pop >= 10), 4),
            "market": ((houses >= 3) + (houses >= 7), 8),
            "chapel": (1 if m.keep < m.keep_max - 4 or pop >= 9 else 0, 5),
            "barracks": (1 if pop >= 7 and any(f.state != "defeated" for f in m.foes) else 0, 4),
            "mine": (1 if pop >= 9 else 0, 3),
            "smithy": (1 if kinds.get("mine") else 0, 3),
            "watchtower": (1 if houses >= 6 else 0, 2),
        }
        for kind, (want, prio) in targets.items():
            if have(kind) < want:
                wants.append((f"plan-{kind}", prio))
        cut_off = [s for s in m.board.structures.values() if s.spec["work"] and makes(s.spec) in GOODS
                   and not self.link_of(s)]
        if cut_off and not cards.get("plan-storage-yard"):
            wants.append(("plan-storage-yard", 6))
        elif not self.spot_extras()["net"] and not cards.get("plan-storage-yard") and kinds.get("storage-yard", 0) < 3:
            wants.append(("plan-storage-yard", 5))
        short = [r for r in ("stone", "wood") if m.stock[r] < 3 + self.blueprint_demand().get(r, 0)]
        for r in short:
            kind = "quarry" if r == "stone" else "lumbermill"
            if not cards.get(f"plan-{kind}") and kinds.get(kind, 0) < 2 + pop // 6:
                wants.append((f"plan-{kind}", 7))
        if self.stats.idle.get(m.round - 1, 0) >= 3:  # idle haulers: more workplaces
            for kind in ("farm", "workshop", "market", "bakery", "quarry", "lumbermill", "mine"):
                want = targets.get(kind, (99,))[0] + 1
                if have(kind) < want and not cards.get(f"plan-{kind}"):
                    wants.append((f"plan-{kind}", 5))
                    break
        if kinds.get("workshop") and cards.get("sell", 0) < 1 + (pop >= 10):
            wants.append(("sell", 4))
        if any(s.ruined for s in m.board.structures.values()) and not cards.get("masons"):
            wants.append(("masons", 4))
        seen, ranked = set(), []
        for cid, prio in sorted(wants, key=lambda w: -w[1]):
            if cid not in seen and cid in CARDS:
                seen.add(cid)
                ranked.append((cid, prio))
        return ranked

    def buy_pass(self):
        m = self.match
        if self.style == "passive":
            return
        for _ in range(4):
            if m.result is not None:
                return
            wants = self.wants()
            if not wants:
                return
            slots = {cid: i for i, cid in enumerate(m.market.slots)}
            bought = False
            for cid, prio in wants:
                price = CARDS[cid]["price"]
                if cid in slots and m.stock["gold"] - price >= (0 if prio >= 8 else 1):
                    gold = m.stock["gold"]
                    m.buy(self.pid, slots[cid])
                    self.stats.gold_out["market"] += gold - m.stock["gold"]
                    self.stats.bought[cid] += 1
                    bought = True
                    break
            if bought:
                continue
            top, prio = wants[0]
            if prio >= 7 and m.rerolls < 2 and m.stock["gold"] >= m.reroll_cost() + CARDS[top]["price"]:
                gold = m.stock["gold"]
                m.reroll(self.pid)
                self.stats.gold_out["rerolls"] += gold - m.stock["gold"]
                self.stats.rerolls += 1
                continue
            return
