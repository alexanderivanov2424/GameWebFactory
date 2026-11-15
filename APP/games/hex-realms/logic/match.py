"""Hex Realms: Match, one game from start to finish (no lobby or network).

    match.act(pid, name, *args)     an order from orders.py (raises LobbyError)
    match.set_done(pid, True)       end your turn; the turn resolves once all live realms are done
    match.resolve() / remove(pid)   resolve now (the timer calls this) / pid left
    match.public() / private(pid)   what clients see
    match.result                    None while playing, then {"winner", "reason", "scores"}

Resolution: research; ranged shots; movement and battles (movement.py); towers; settlers found
cities; builds (a cell two players order fails for both); recruits; production, eating, wages and
new people (economy.py); construction; healing; realms with no Town Hall are knocked out. The game
ends when one realm is left (2+ started) or after the last turn. Solo games end at the turn limit
or when the last Town Hall falls.

Score = population + units + 3 per advance + structure scores + gold // 10.

Main dicts: cells, structures (cell_structure), units (unit_at), sites (cell_site), claims and
territory ({key: pid}), players, orders (secret until resolution), events (for the client to replay).
"""

import random

from gamekit import LobbyError
from gamekit.hexes import disk, dist, neighbors, parse

from . import bots, combat, construction, economy, logistics, movement, orders, recruiting, standing, territory, vision
from .content import ADVANCES, CATEGORIES, RESOURCE_INFO, TAGS, RESOURCES, STRUCTURES, TERRAIN, TOWN_HALL, UNITS, footprint
from .economy import end_of_turn, report, staffing
from .mapgen import generate

COLORS = ["#d9483b", "#3b7dd9", "#e0b030", "#3ba55d", "#a05cc8", "#e07b22"]
START_RES = {"gold": 10, "faith": 0, "science": 0}  # realm-wide
START_GOODS = {"wood": 10, "stone": 5}  # put into the first Town Hall when it's founded
START_UNIT = "settlers"
START_ESCORT = "scout"  # starts on a free land cell next to the settlers
START_POP = 3
SIZES = {"small": -3, "normal": 0, "large": 4, "huge": 8}
ACTS = {name: getattr(orders, name) for name in
        ("build", "claim", "recruit", "move", "shoot", "hold", "auto", "found", "research", "cancel", "trade", "toggle",
         "staff", "demolish", "disband")}


def map_radius(players, size):
    return 9 + 3 * min(players, 6) + SIZES.get(size, 0) - (2 if players == 1 else 0)


def empty_orders():
    return {"builds": [], "recruits": [], "research": [], "moves": {}, "shots": {}, "holds": [], "found": {}}


class Match:
    def __init__(self, names, settings, rng=None, bots=()):
        self.rng = rng or random.Random()
        self.bots = [pid for pid in bots if pid in names]
        self.names = dict(names)
        self.seats = list(self.names)
        self.settings = dict(settings)
        self.turn_limit = self.settings.get("turns", 40)
        seed = self.settings.get("seed") or self.rng.randrange(1, 10 ** 9)
        self.radius = map_radius(len(self.seats), self.settings.get("mapSize", "normal"))
        self.cells, starts = generate(self.radius, len(self.seats), seed)
        self.rng.shuffle(starts)
        self.counter = 0
        self.structures, self.cell_structure, self.units, self.unit_at = {}, {}, {}, {}
        self.sites, self.cell_site = {}, {}
        self.claims = {}  # {key: pid}: weak land bought with gold (orders.claim)
        self.territory = {}  # {key: pid}: strong land, first come first served (territory.py)
        self.players = {pid: {"res": dict(START_RES), "pop": START_POP, "advances": [], "done": False, "alive": True,
                              "color": COLORS[i % len(COLORS)], "startGoods": dict(START_GOODS)}
                        for i, pid in enumerate(self.seats)}
        self.orders = {pid: empty_orders() for pid in self.seats}
        self.fog = self.settings.get("fog", "on") == "on"
        self.visible = {pid: set() for pid in self.seats}
        self.explored = {pid: set() for pid in self.seats}
        self.memory = {pid: {} for pid in self.seats}  # remembered enemy structures (vision.py)
        self.vis_before = {}
        self.result = None
        for pid, at in zip(self.seats, starts):
            self.add_unit(pid, START_UNIT, at)
            near = [k for k in sorted(disk(2, parse(at)), key=lambda k: (dist(k, at), k)) if k != at and k in self.cells
                    and TERRAIN[self.cells[k]]["move"] is not None and k not in self.unit_at]
            if near:
                self.add_unit(pid, START_ESCORT, near[0])
        self.turn = 1
        self.step = 0
        self.events = []
        self.log = []
        self.fought = set()
        self.result = None
        self.multi = len(self.seats) > 1
        self.refresh()
        self.snapshot()
        self.plan_bots()

    def plan_bots(self):
        for pid in self.bots:
            bots.plan(self, pid)

    # --- State helpers (used by the other modules) -------------------------------------------

    def new_id(self, prefix):
        self.counter += 1
        return f"{prefix}{self.counter}"

    def add_structure(self, owner, stype, at, rot):
        sid = self.new_id("s")
        cells = footprint(stype, at, rot)
        s = {"id": sid, "n": self.counter, "type": stype, "owner": owner, "at": at, "rot": rot, "cells": cells,
             "hp": STRUCTURES[stype]["hp"], "active": True, "stock": {}}
        self.structures[sid] = s
        for c in cells:
            self.cell_structure[c] = sid
        return s

    def remove_structure(self, sid):
        s = self.structures.pop(sid)
        for c in s["cells"]:
            self.cell_structure.pop(c, None)

    def add_unit(self, owner, utype, at):
        uid = self.new_id("u")
        self.units[uid] = {"id": uid, "n": self.counter, "type": utype, "owner": owner, "at": at, "hp": UNITS[utype]["hp"]}
        self.unit_at[at] = uid
        territory.unit_entered(self, uid)
        return uid

    def remove_unit(self, uid):
        u = self.units.pop(uid)
        if self.unit_at.get(u["at"]) == uid:
            del self.unit_at[u["at"]]
        orders.clear_unit(self, u["owner"], uid)

    def move_unit(self, uid, k):
        u = self.units[uid]
        if self.unit_at.get(u["at"]) == uid:
            del self.unit_at[u["at"]]
        u["at"] = k
        self.unit_at[k] = uid
        territory.unit_entered(self, uid)

    def orders_moves(self):
        return [(uid, p) for pid in self.seats for uid, p in self.orders[pid]["moves"].items()]

    def refresh(self):
        self.territory, self.claims = territory.territory(self)
        vision.update(self)

    def snapshot(self):
        """What everyone sees of each player's stock during planning (their orders stay secret)."""
        self.shown = {pid: {"res": logistics.stock(self, pid), "pop": p["pop"]} for pid, p in self.players.items()}

    def alive(self):
        return [pid for pid in self.seats if self.players[pid]["alive"]]

    def structures_of(self, pid, stype=None):
        """pid's structures, oldest first (only one type if given)."""
        return [s for s in self.structures.values() if s["owner"] == pid and stype in (None, s["type"])]

    def units_of(self, pid):
        """pid's units, oldest first."""
        return [u for u in self.units.values() if u["owner"] == pid]

    def has_hall(self, pid):
        return any(s["owner"] == pid and s["type"] == TOWN_HALL for s in self.structures.values())

    # --- Planning -------------------------------------------------------------------------------

    def act(self, pid, name, *args):
        if self.result is not None or pid not in self.players or not self.players[pid]["alive"]:
            raise LobbyError("You're not playing.")
        ACTS[name](self, pid, *args)
        self.players[pid]["done"] = False
        if name in ("disband", "demolish"):
            self.refresh()

    def set_done(self, pid, done):
        if self.result is not None or not self.players.get(pid, {}).get("alive"):
            raise LobbyError("You're not playing.")
        self.players[pid]["done"] = bool(done)
        if all(self.players[p]["done"] for p in self.alive()):
            self.resolve()

    # --- Resolution -----------------------------------------------------------------------------

    def resolve(self):
        if self.result is not None:
            return
        ev = []
        self.fought = set()
        self.vis_before = {pid: set(v) for pid, v in self.visible.items()}  # events seen as they happened
        for pid in self.alive():
            for r in self.orders[pid]["research"]:
                self.players[pid]["advances"].append(r["advance"])
                ev.append({"t": "research", "owner": pid, "advance": r["advance"]})
        for pid in self.alive():
            for uid, cell in list(self.orders[pid]["shots"].items()):
                if uid in self.units:
                    combat.shoot(self, uid, cell, ev)
        movement.resolve(self, ev)
        combat.towers(self, ev)
        self._found(ev)
        self._builds(ev)
        recruiting.resolve(self, ev)
        self.refresh()
        idle = {pid: staffing(self, pid)[1] for pid in self.alive()}  # this turn's builders
        for pid in self.alive():
            end_of_turn(self, pid, ev)
        for pid in self.alive():
            construction.progress(self, pid, idle[pid], ev)
        self._heal()
        self._eliminate(ev)
        self.refresh()
        self.turn += 1
        self.step += 1
        self.events = ev
        for pid in self.seats:
            self.orders[pid] = empty_orders()
            self.players[pid]["done"] = False
        self.snapshot()
        self._check_end()
        standing.plan_all(self)
        self.plan_bots()

    def _found(self, ev):
        for pid in self.alive():
            for uid, rot in list(self.orders[pid]["found"].items()):
                u = self.units.get(uid)
                if u is None:
                    continue
                problem = orders.found_problem(self, pid, u, rot, planning=False)
                if problem:
                    ev.append({"t": "failed", "owner": pid, "what": TOWN_HALL, "at": u["at"], "why": problem})
                    continue
                at = u["at"]
                self.remove_unit(uid)
                hall = self.add_structure(pid, TOWN_HALL, at, rot)
                if "startGoods" in self.players[pid]:  # the first city gets the starting goods
                    hall["stock"] = self.players[pid].pop("startGoods")
                ev.append({"t": "founded", "owner": pid, "at": at})
                self.log.append(f"Turn {self.turn}: {self.names[pid]} founded a city.")

    def _builds(self, ev):
        claims = {}
        for pid in self.alive():
            for b in self.orders[pid]["builds"]:
                for c in b["cells"]:
                    claims.setdefault(c, set()).add(pid)
        queues = [list(self.orders[pid]["builds"]) for pid in self.alive()]
        while any(queues):
            for pid, q in zip(self.alive(), queues):
                if not q:
                    continue
                b = q.pop(0)
                problem = "Another player built there too." if any(len(claims[c]) > 1 for c in b["cells"]) else \
                    orders.site_problem(self, pid, b["type"], b["cells"])
                if problem:
                    logistics.give(self, pid, b["cost"])
                    ev.append({"t": "failed", "owner": pid, "what": b["type"], "at": b["at"], "why": problem})
                else:
                    construction.start(self, pid, b)
                    ev.append({"t": "site", "owner": pid, "type": b["type"], "at": b["at"]})

    def _heal(self):
        for u in self.units.values():
            if u["id"] in self.fought:
                continue
            full = UNITS[u["type"]]["hp"]
            near = [self.cell_structure.get(k) for k in [u["at"]] + neighbors(u["at"])]
            barracks = any(sid and self.structures[sid]["owner"] == u["owner"] and STRUCTURES[self.structures[sid]["type"]]["heals"]
                           for sid in near)
            u["hp"] = full if barracks else min(full, u["hp"] + 1)

    def _eliminate(self, ev):
        for pid in self.alive():
            if not self.has_hall(pid) and not any(UNITS[u["type"]]["settler"] for u in self.units_of(pid)):
                self.knock_out(pid)
                ev.append({"t": "eliminated", "owner": pid})
                self.log.append(f"Turn {self.turn}: {self.names[pid]} lost their last Town Hall.")

    def knock_out(self, pid):
        self.players[pid]["alive"] = False
        self.players[pid]["done"] = False
        for u in self.units_of(pid):
            self.remove_unit(u["id"])
        for s in self.structures_of(pid):
            self.remove_structure(s["id"])
        for cid in [c for c, x in self.sites.items() if x["owner"] == pid]:
            construction.remove(self, cid)
        self.claims = {k: p for k, p in self.claims.items() if p != pid}
        self.orders[pid] = empty_orders()

    def _check_end(self):
        alive = self.alive()
        if not alive:
            self.end(None, "Every realm has fallen.")
        elif self.bots and not [pid for pid in alive if pid not in self.bots]:
            scores = {pid: self.score(pid) for pid in alive}
            winner = max(alive, key=lambda pid: scores[pid]) if list(scores.values()).count(max(scores.values())) == 1 else None
            self.end(winner, f"Only bots are left: {self.names[winner]} has the highest score." if winner
                     else "Only bots are left.")
        elif self.multi and len(alive) == 1:
            self.end(alive[0], f"{self.names[alive[0]]} is the last realm standing.")
        elif self.turn > self.turn_limit and not self.multi:
            pid = alive[0]
            self.end(pid, f"Turn limit reached: {self.names[pid]} finished with {self.score(pid)} points.")
        elif self.turn > self.turn_limit:
            scores = {pid: self.score(pid) for pid in alive}
            top = max(scores.values())
            best = [pid for pid in alive if scores[pid] == top]
            winner = best[0] if len(best) == 1 else None
            self.end(winner, f"Turn limit reached: {self.names[winner]} has the highest score." if winner
                     else "Turn limit reached: a tie for the highest score.")

    def end(self, winner, reason):
        self.result = {"winner": winner, "reason": reason, "scores": {pid: self.score(pid) for pid in self.seats}}

    def score(self, pid):
        p = self.players[pid]
        if not p["alive"]:
            return 0
        built = sum(STRUCTURES[s["type"]]["score"] for s in self.structures_of(pid))
        return p["pop"] + len(self.units_of(pid)) + 3 * len(p["advances"]) + built + p["res"]["gold"] // 10

    def remove(self, pid):
        if pid not in self.players or not self.players[pid]["alive"]:
            return
        self.knock_out(pid)
        self.log.append(f"Turn {self.turn}: {self.names[pid]} left the game.")
        self.refresh()
        if not self.multi or len(self.alive()) <= 1 or not set(self.alive()) - set(self.bots):
            self._check_end()
            if self.result is None:
                self.end(None, "Everyone left.")
        elif all(self.players[p]["done"] for p in self.alive()):
            self.resolve()

    # --- What clients see -----------------------------------------------------------------------

    def public(self):
        """Everything but the map, which is in each viewer's private state (vision.view)."""
        return {
            "turn": self.turn, "turnLimit": self.turn_limit, "step": self.step, "radius": self.radius,
            "seats": self.seats, "fog": self.fog, "bots": self.bots,
            "content": {"structures": STRUCTURES, "units": UNITS, "advances": ADVANCES, "terrain": TERRAIN,
                        "resources": RESOURCES, "categories": CATEGORIES,
                        "tags": {t: {"name": n, "color": c} for t, (n, c) in TAGS.items()},
                        "claim": {"cost": orders.CLAIM_COST, "upkeep": territory.LAND_UPKEEP},
                        "tradeGoods": economy.TRADE_GOODS, "goods": logistics.GOODS,
                        "resourceInfo": {r: {"name": n, "icon": i} for r, (n, i) in RESOURCE_INFO.items()}},
            "players": {pid: {"name": self.names[pid], "color": p["color"], "res": self.shown[pid]["res"],
                              "pop": self.shown[pid]["pop"], "advances": p["advances"], "done": p["done"],
                              "alive": p["alive"], "score": self.score(pid)} for pid, p in self.players.items()},
            "log": {str(i): line for i, line in enumerate(self.log)},
        }

    def ordered(self, pid):
        """pid's units that have an order this turn or a standing order (greyed out on the map)."""
        o = self.orders[pid]
        busy = set(o["moves"]) | set(o["shots"]) | set(o["holds"]) | set(o["found"])
        return sorted(u["id"] for u in self.units_of(pid) if u["id"] in busy or u.get("auto"))

    def private(self, pid):
        """The map as pid sees it ("view"; pid None = spectator, whole map), plus pid's stock, orders and planning help."""
        staffed = {s["id"] for x in self.alive() for s in staffing(self, x)[0]}
        out = {"view": vision.view(self, pid, staffed)}
        if pid not in self.players or not self.players[pid]["alive"] or self.result is not None:
            return out
        p, own, units = self.players[pid], self.structures_of(pid), self.units_of(pid)
        return {
            **out,
            "res": logistics.stock(self, pid), "pop": p["pop"], "done": p["done"],
            "stores": {s["id"]: {"stock": s["stock"], "cap": logistics.capacity(s)} for s in logistics.stores(self, pid)},
            "trades": {s["id"]: s["trade"] for s in own if s.get("trade")},
            "orders": self.orders[pid], "report": report(self, pid),
            "auto": {u["id"]: {"mode": u["auto"], "goal": u.get("goal")} for u in units if u.get("auto")},
            "ordered": self.ordered(pid),
            "building": construction.forecast(self, pid),
            "typeBonus": economy.type_bonus(self, pid), "housingBonus": economy.housing_bonus(self, pid),
            "reach": {u["id"]: sorted(movement.reach(self, u["id"])) for u in units},
            "recruit": {s["id"]: {ut: orders.recruit_problem(self, pid, s, ut) or "" for ut in STRUCTURES[s["type"]]["recruits"]}
                        for s in own if STRUCTURES[s["type"]]["recruits"]},
            "found": {u["id"]: [r for r in range(6) if not orders.found_problem(self, pid, u, r)]
                      for u in units if UNITS[u["type"]]["settler"]},
        }

