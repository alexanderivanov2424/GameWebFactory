"""Bastion: playtest bots (test-only: tests/ is never deployed, and this isn't a test_*.py file, so
the test runner doesn't collect it). The user asked for bots to playtest and balance the game;
tests/playtest.py drives them. They play through the Match API only (legal moves from units,
hauling and tiles, build spots from board.check + economy.output like views.build_targets but
only near the city; Match methods to act) and never change Match internals.

    bot = Bot(match, pid, rng, stats, style="good" | "passive")
    bot.place()      place phase: put every free unit somewhere, then ready
    bot.act()        act phase, on this bot's turn: cards, resolving, building, roads, market,
                     soldier strikes (the driver calls match.end_turn after it)
    Stats()          counters every bot of one game writes to (playtest.py reads them)

"good": a heuristic player. Placement is greedy over a value per output (food is worth more
when the stockpile won't cover the next rounds, scarce materials more than plentiful ones,
strikes on an active enemy a lot); work goes first, hauls after, input users last; a tool
boosts work when the stockpile has spares; blueprints go to the spot with the best output plus
link, neighbour and keep-distance terms (never one that cuts roads off); houses wait until food
and work keep up; roads link what's cut off; the market buys from a want list driven by the
food margin, materials, idle units and enemies (at most 2 rerolls a round). It never builds
walls: walling the city cost more space than raids cost it.
"passive": works the farm and the lumbermill, fights with everything else, never builds or buys.
Both are deterministic (the match rng is seeded; ties break by board order): a seed gives the same game.
"""

import math
from collections import Counter, defaultdict, deque

from gamekit import LobbyError

from games.bastion.logic import economy, food, hauling, tiles, units
from games.bastion.logic.cards import CARDS
from games.bastion.logic.structures import GOODS, STRUCTURES

BASE_VALUE = {"wood": 1.0, "stone": 1.3, "ore": 0.6, "wheat": 1.2, "bread": 2.4, "tools": 1.5, "gold": 1.2}
TARGET = {"wood": 8, "stone": 6, "gold": 6, "tools": 3}  # stockpile the good bot likes to keep


class Stats:
    def __init__(self):
        self.produced = Counter()  # round -> goods made (stockpile or store)
        self.hauled = Counter()  # round -> goods hauled
        self.haul_units = Counter()  # round -> haul resolutions
        self.gold_in = 0
        self.gold_out = defaultdict(int)  # what gold went to
        self.tools_used = 0  # tools spent on work
        self.tools_sold = 0
        self.built = Counter()
        self.bought = Counter()
        self.fight_units = 0
        self.work_units = 0
        self.lost_units = 0
        self.rerolls = 0
        self.idle = Counter()  # round -> units the good bots left unplaced


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


def food_capacity(match):
    """Wheat-equivalent the city's food buildings make in a round if all are worked (bakeries
    count their bread less the wheat they use)."""
    total = 0
    for s in match.board.structures.values():
        if not s.spec["work"] or s.ruined or s.plague is not None:
            continue
        key = makes(s.spec)
        out = economy.output(match.board, s.kind, s.cells)[0]
        if key == "wheat":
            total += out
        elif key == "bread":
            total += out * food.FEEDS["bread"] / food.FEEDS["wheat"] - 1
    for s in match.board.structures.values():
        total += s.spec["income"].get("wheat", 0) + s.spec["income"].get("bread", 0) * 2
    return total


def food_margin(match):
    """Wheat a round the city's food buildings (all worked) make beyond what it eats."""
    return food_capacity(match) - need_per_round(match)


def need_per_round(match):
    return match.population() / food.FEEDS["wheat"]


# --- roads -----------------------------------------------------------------------------------

def connected_cells(board, reach):
    depots = board.depot_cells()
    return lambda c: bool(board.neighbors([c]) & depots) or bool(board.neighbors([c]) & reach)


def road_path(board, cells, limit=14):
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

    def link_of(self, s):
        """board.link(s) with the road reach cached per board version."""
        board = self.match.board
        cached = self._spot_cache.get("reach")
        if not cached or cached[0] != board.version:
            cached = self._spot_cache["reach"] = (board.version, board.road_reach())
        return board.link(s, cached[1])

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

    def place(self):
        m = self.match
        if self.style == "passive":
            self.place_passive()
        else:
            self.place_good()
        m.ready(self.pid)

    def place_passive(self):
        m = self.match
        while units.free(m, self.pid) > 0:
            options = units.targets(m)
            pick = None
            for t in options:
                if t.startswith("s"):
                    s = m.board.structures[int(t[1:])]
                    if s.kind in ("farm", "lumbermill") and not units.resolve_reason(m, t):
                        pick = t
                        break
            if pick is None:
                fights = [t for t in options if t.startswith("fight") or t.startswith("raze")]
                pick = fights[0] if fights else "haul"
            m.place(self.pid, pick)

    def plan_context(self):
        """Expected stockpile changes and stored goods from everything already placed this round."""
        m = self.match
        ctx = {"stock": Counter(), "stored": 0, "haul_cap": 0, "strikes": Counter(), "hauls": 0}
        for target, by in sorted(m.placed.items(), key=lambda kv: kv[0] == "haul"):  # work before hauls
            for _ in range(sum(by.values())):
                self.apply(ctx, target)
        return ctx

    def apply(self, ctx, target):
        m = self.match
        if target == "haul":
            cap = hauling.capacity(m.board, m.hauled + ctx["hauls"])
            ctx["hauls"] += 1
            moved = min(cap, max(0, self.haulable(ctx)))
            ctx["haul_cap"] += moved
            return
        if target.startswith("fight"):
            ctx["strikes"][target] += 1
            return
        if target.startswith("raze"):
            ctx["strikes"][target] += 1
            return
        s = m.board.structures[int(target[1:])]
        key = makes(s.spec)
        out = economy.amount(m.board, s)
        for r, n in s.spec["work"]["uses"].items():
            ctx["stock"][r] -= n
        if key in GOODS and self.link_of(s) != "depot":
            room = economy.STORE_CAP - s.stored()
            if self.link_of(s):
                ctx["stored"] += min(out, room)
        else:
            ctx["stock"][key] += out

    def haulable(self, ctx):
        stored = sum(s.stored() for s in hauling.sources(self.match.board).values())
        return stored + ctx["stored"] - ctx["haul_cap"]

    def score(self, ctx, target, vals):
        m = self.match
        if target == "haul":
            cap = hauling.capacity(m.board, m.hauled + ctx["hauls"])
            gain = min(cap, max(0, self.haulable(ctx)))
            return gain * 1.15
        if target.startswith("fight"):
            foe = m.foes[int(target[5:])]
            left = foe.hp * foe.defeat["soldiers"] - foe.strikes - ctx["strikes"][target]
            return self.strike_value(foe) if left > 0 else -1
        if target.startswith("raze"):
            x, y = (int(v) for v in target[4:].split(","))
            blight = m.board.blights.get((x, y))
            if not blight or ctx["strikes"][target]:
                return -1
            if blight["lair"]:
                return self.strike_value(m.foes[blight["foe"]]) + 0.3
            hurt = sum(1 for uid in {m.board.at[c] for c in m.board.neighbors([(x, y)]) if c in m.board.at}
                       if m.board.structures[uid].spec["work"])
            return 1.0 + 1.2 * hurt
        s = m.board.structures[int(target[1:])]
        spec = s.spec
        key = makes(spec)
        uses = spec["work"]["uses"]
        if uses and not self.link_of(s):
            return -1
        for r, n in uses.items():
            if m.stock[r] + min(0, ctx["stock"][r]) < n:
                return -1
        out = economy.amount(m.board, s)
        value = out * vals.get(key, 1.0)
        if key in GOODS and self.link_of(s) != "depot":
            if not self.link_of(s):
                return value * 0.15
            room = economy.STORE_CAP - s.stored()
            value = min(out, room) * vals.get(key, 1.0) * 0.85
        if key == "cure":
            value = min(out, len(m.plagued())) * vals["cure"]
        if key == "keep":
            value = min(out, m.keep_max - m.keep) * vals["keep"]
        value -= sum(n * vals.get(r, 1.0) for r, n in uses.items()) * 0.8
        return value

    def place_good(self):
        m = self.match
        while units.free(m, self.pid) > 0:
            ctx = self.plan_context()
            vals = self.values(ctx["stock"])
            best, best_score = None, 0.05
            for t in units.targets(m):
                sc = self.score(ctx, t, vals)
                if sc > best_score:
                    best, best_score = t, sc
            if best is None:  # nothing useful: leave the rest unplaced
                self.stats.idle[m.round] += units.free(m, self.pid)
                return
            m.place(self.pid, best)

    # --- act phase --------------------------------------------------------------------------

    def act(self):
        m = self.match
        if self.style == "passive":
            self.resolve_all()
            self.pay_curses(passive=True)
            self.spend_soldiers()
            return
        self.play_actions()
        self.build_pass()
        self.resolve_all()
        if m.result is not None:
            return
        self.pay_curses()
        self.build_pass()
        self.link_pass()
        self.special_damage()
        self.spend_soldiers()
        self.buy_pass()
        self.play_actions(late=True)
        self.build_pass()

    def tool_reserve(self):
        need = self.blueprint_demand().get("tools", 0)
        if kinds_on_board(self.match).get("barracks"):
            need += 1
        return need

    def resolve_order(self, target):
        m = self.match
        if target.startswith("s"):
            s = m.board.structures.get(int(target[1:]))
            if s and s.spec["work"]["uses"]:
                return 2
            return 0
        if target == "haul":
            return 1
        return 3

    def resolve_all(self):
        m = self.match
        for _ in range(3):  # retry: hauls and earlier work may supply later inputs
            mine = units.mine(m, self.pid)
            if not mine:
                return
            progress = False
            for target in sorted(mine, key=self.resolve_order):
                for _ in range(mine[target]):
                    if m.result is not None or self.match.turn() != self.pid:
                        return
                    if self.resolve_one(target):
                        progress = True
            if not progress:
                break

    def resolve_one(self, target):
        m = self.match
        tool = False
        if target.startswith("s") and self.style != "passive":
            s = m.board.structures.get(int(target[1:]))
            if s and m.stock["tools"] > self.tool_reserve() and makes(s.spec) not in ("cure",) \
                    and not units.resolve_reason(m, target, True):
                key = makes(s.spec)
                if key != "keep" or m.keep_max - m.keep > economy.amount(m.board, s):
                    tool = True
        if units.resolve_reason(m, target, tool):
            if tool and not units.resolve_reason(m, target):
                tool = False
            else:
                return False
        gold, goods, stock = m.stock["gold"], goods_total(m), sum(m.stock[g] for g in GOODS)
        m.resolve(self.pid, target, tool)
        self.stats.gold_in += max(0, m.stock["gold"] - gold)
        if target == "haul":
            self.stats.hauled[m.round] += sum(m.stock[g] for g in GOODS) - stock
            self.stats.haul_units[m.round] += 1
        elif target.startswith("s"):
            self.stats.work_units += 1
            self.stats.produced[m.round] += max(0, goods_total(m) - goods + (1 if tool else 0))
            if tool:
                self.stats.tools_used += 1
        else:
            self.stats.fight_units += 1
        return True

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
                    if m.stock["gold"] < 10:
                        self.play(c["uid"])
                elif cid == "sell":
                    if m.stock["tools"] > self.tool_reserve() + (2 if not late else 0) or m.stock["gold"] < 2:
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
            if not passive and "wheat" in pay and vals["wheat"] >= 2.2:
                continue  # food first
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

    def candidates(self, kind, ex):
        """Legal spots near the city (same rules as views.build_targets, a smaller area):
        (rotation, x, y, cells, output)."""
        board, spec = self.board, STRUCTURES[kind]
        if "near" not in ex:
            used = [c for s in board.structures.values() for c in s.cells] + list(board.roads)
            ex["near"] = (min(x for x, _ in used) - 5, max(x for x, _ in used) + 2,
                          min(y for _, y in used) - 5, max(y for _, y in used) + 2)
        x0, x1, y0, y1 = ex["near"]
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
        ex["best"][kind] = found = self.find_spot(kind, ex)
        return found

    def find_spot(self, kind, ex):
        board, spec = self.board, STRUCTURES[kind]
        key = makes(spec)
        kx, ky = ex["keep"]
        if spec["protects"]:
            open_cells = [c for s in board.structures.values() if s.kind != "keep" for c in s.cells
                          if not board.protected(c)]
        scored = []
        for rot, x, y, cells, out in self.candidates(kind, ex):
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
        if best is None or (spec["work"] and best_score < 0):
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
        """Useful places for units in a round: workable buildings, one haul per building that
        stores its goods, and a few fighters while a fightable enemy is here."""
        m = self.match
        count = 0
        for s in m.board.structures.values():
            if s.spec["work"] and not s.ruined and s.plague is None:
                if makes(s.spec) == "cure" and not m.plagued():
                    continue
                count += 1
                if makes(s.spec) in GOODS and self.link_of(s) == "road":
                    count += 1
        if any(f.active and f.fightable for f in m.foes):
            count += 4
        count += sum(1 for b in m.board.blights.values())
        return count

    def house_ok(self, extra=0):
        """Another house (2 people) would have food and work."""
        m = self.match
        units_next = m.population() + 2 * extra
        idle = self.stats.idle.get(m.round - 1, 0) if m.round > 1 else 0
        stocked = (m.stock["wheat"] + 2 * m.stock["bread"]) / max(1.0, need_per_round(m))
        food_ok = food_margin(m) >= extra - (1.5 if stocked >= 2 else 0.5)
        planned = sum(n for cid, n in team_cards(m).items()
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
            "quarry": (1 + pop // 12, 9 if not have("quarry") else 6),
            "lumbermill": (1 + pop // 10, 7),
            "workshop": (1 if pop >= 6 else 0, 6),
            "bakery": ((pop >= 10) + (pop >= 20), 7),
            "storage-yard": ((pop >= 8) + (pop >= 18), 5),
            "carriage": ((pop >= 10) + (pop >= 18), 4),
            "market": ((houses >= 3) + (houses >= 7), 8),
            "chapel": (1 if m.keep < m.keep_max - 4 or pop >= 16 else 0, 5),
            "barracks": (1 if pop >= 12 and any(f.state != "defeated" for f in m.foes) else 0, 4),
            "mine": (1 if pop >= 16 else 0, 3),
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
            if not cards.get(f"plan-{kind}") and kinds.get(kind, 0) < 2 + pop // 10:
                wants.append((f"plan-{kind}", 7))
        if self.stats.idle.get(m.round - 1, 0) >= 2:  # idle hands: more workplaces
            for kind in ("farm", "workshop", "market", "bakery", "quarry", "lumbermill", "mine"):
                want = targets.get(kind, (99,))[0] + 1
                if have(kind) < want and not cards.get(f"plan-{kind}"):
                    wants.append((f"plan-{kind}", 5))
                    break
        if kinds.get("workshop") and cards.get("sell", 0) < 1 + kinds.get("workshop", 0) + (pop >= 16):
            wants.append(("sell", 6))
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
