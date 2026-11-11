"""Hex Realms: Match, one game from start to finish (no lobby, network or members).

    match = Match({"p1": "Ann", "p2": "Bob"}, settings, rng=random.Random(1), bots=["b1"])
                               bots: seats played by the computer (bots.py plans their turns)
    match.act(pid, "build", stype, at, rot)   any order from orders.py (raises LobbyError)
    match.set_done(pid, True)  end your turn; when every player still in is done, the turn resolves
    match.resolve()            resolve the turn now (also the turn timer's job, in server.py)
    match.remove(pid)          pid left: their units and structures vanish
    match.public() / match.private(pid)    what clients see
    match.result               None while playing; then {"winner": pid or None, "reason", "scores"}

Turn resolution, in order: research; ranged shots (positions before anyone moves); movement
step by step with battles (movement.py); towers shoot; settlers found cities; builds (two
players ordering the same cell both fail and get refunds); recruits appear on or next to their
structure; production, deliveries along roads, eating, wages and growth (economy.py, logistics.py); healing (+1 hp for units that didn't
fight, full on or next to an own Barracks); players without a Town Hall are out. The game ends
when one player is left (if it started with 2 or more) or after the last turn: highest score wins.
Solo games (1 player) are a sandbox: they end at the turn limit with your score, or when you lose
your last Town Hall. Bots plan as each turn starts (and are done at once); once no person is
left in the game, it ends with the highest score winning.

Score = population + units + 3 per advance + structure scores (Town Hall 4, University 2,
Monument 10) + gold // 10.

State: cells {key: terrain}; structures {sid: {"id", "n", "type", "owner", "at", "rot", "cells",
"hp", "active", "stock" (goods in a store), "held" (goods a producer waits to deliver)}} with cell_structure {key: sid}; units {uid: {"id", "n", "type", "owner", "at",
"hp"}} with unit_at {key: uid}; players {pid: {"res" (gold/faith/science only: goods live in
stores, see logistics.py), "pop", "advances", "done", "alive"}};
orders {pid: {"builds", "recruits", "research": [...], "moves": {uid: [keys]}, "shots": {uid: key},
"holds": [uid], "found": {uid: rot}}}; events (the last resolution, for the client to replay).
"""

import random

from gamekit import LobbyError
from gamekit.hexes import neighbors

from . import bots, combat, logistics, movement, orders, vision
from .content import ADVANCES, CATEGORIES, RESOURCE_INFO, RESOURCES, STRUCTURES, TERRAIN, TOWN_HALL, UNITS, footprint
from .economy import end_of_turn, report, staffing, territory
from .mapgen import generate

COLORS = ["#d9483b", "#3b7dd9", "#e0b030", "#3ba55d", "#a05cc8", "#e07b22"]
START_RES = {"gold": 10, "faith": 0, "science": 0}  # realm-wide
START_GOODS = {"food": 10, "wood": 12, "stone": 6}  # put into the first Town Hall when it's founded
START_UNIT = "settlers"
START_POP = 3
SIZES = {"small": -3, "normal": 0, "large": 4, "huge": 8}
ACTS = {name: getattr(orders, name) for name in
        ("build", "recruit", "move", "shoot", "hold", "found", "research", "cancel", "trade", "toggle", "disband")}


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
            self.add_unit(pid, START_UNIT, at)  # they found the first Town Hall where they choose
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
             "hp": STRUCTURES[stype]["hp"], "active": True, "stock": {}, "held": {}}
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

    def orders_moves(self):
        return [(uid, p) for pid in self.seats for uid, p in self.orders[pid]["moves"].items()]

    def refresh(self):
        self.territory = territory(self)
        vision.update(self)

    def snapshot(self):
        """What everyone sees of each player's stock during planning (their orders stay secret)."""
        self.shown = {pid: {"res": logistics.stock(self, pid), "pop": p["pop"]} for pid, p in self.players.items()}

    def alive(self):
        return [pid for pid in self.seats if self.players[pid]["alive"]]

    # --- Planning -------------------------------------------------------------------------------

    def act(self, pid, name, *args):
        if self.result is not None or pid not in self.players or not self.players[pid]["alive"]:
            raise LobbyError("You're not playing.")
        ACTS[name](self, pid, *args)
        self.players[pid]["done"] = False
        if name == "disband":
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
        self._recruits(ev)
        self.refresh()
        for pid in self.alive():
            end_of_turn(self, pid, ev)
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
                hall["stock"] = self.players[pid].pop("startGoods", {})
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
                    orders.refund(self, pid, b["cost"])
                    ev.append({"t": "failed", "owner": pid, "what": b["type"], "at": b["at"], "why": problem})
                else:
                    self.add_structure(pid, b["type"], b["at"], b["rot"])
                    ev.append({"t": "built", "owner": pid, "type": b["type"], "at": b["at"]})

    def spawn_cell(self, pid, s, utype):
        naval = UNITS[utype]["naval"]
        for k in sorted(set(s["cells"]) | {n for c in s["cells"] for n in neighbors(c)}):
            if k not in self.cells or k in self.unit_at or movement.enemy_structure(self, pid, k):
                continue
            if (self.cells[k] == "water") if naval else TERRAIN[self.cells[k]]["move"] is not None:
                return k
        return None

    def _recruits(self, ev):
        for pid in self.alive():
            for r in self.orders[pid]["recruits"]:
                s = self.structures.get(r["at"])
                spot = self.spawn_cell(pid, s, r["type"]) if s and s["owner"] == pid else None
                if spot is None:
                    orders.refund(self, pid, r["cost"])
                    self.players[pid]["pop"] += r["people"]
                    ev.append({"t": "failed", "owner": pid, "what": r["type"], "at": s["at"] if s else None,
                               "why": "No room to place it."})
                else:
                    self.add_unit(pid, r["type"], spot)
                    ev.append({"t": "recruited", "owner": pid, "type": r["type"], "at": spot})

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
            if not any(s["owner"] == pid and s["type"] == TOWN_HALL for s in self.structures.values()) and \
                    not any(u["owner"] == pid and UNITS[u["type"]]["settler"] for u in self.units.values()):
                self.knock_out(pid)
                ev.append({"t": "eliminated", "owner": pid})
                self.log.append(f"Turn {self.turn}: {self.names[pid]} lost their last Town Hall.")

    def knock_out(self, pid):
        self.players[pid]["alive"] = False
        self.players[pid]["done"] = False
        for uid in [u for u, x in self.units.items() if x["owner"] == pid]:
            self.remove_unit(uid)
        for sid in [s for s, x in self.structures.items() if x["owner"] == pid]:
            self.remove_structure(sid)
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
        own_units = sum(1 for u in self.units.values() if u["owner"] == pid)
        built = sum(STRUCTURES[s["type"]]["score"] for s in self.structures.values() if s["owner"] == pid)
        return p["pop"] + own_units + 3 * len(p["advances"]) + built + p["res"]["gold"] // 10

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
        """Everything but the map: the map part (cells, structures, units, territory, events) is in
        each viewer's private state, cut down by fog of war (vision.view)."""
        return {
            "turn": self.turn, "turnLimit": self.turn_limit, "step": self.step, "radius": self.radius,
            "seats": self.seats, "fog": self.fog, "bots": self.bots,
            "content": {"structures": STRUCTURES, "units": UNITS, "advances": ADVANCES, "terrain": TERRAIN,
                        "resources": RESOURCES, "categories": CATEGORIES,
                        "resourceInfo": {r: {"name": n, "icon": i} for r, (n, i) in RESOURCE_INFO.items()}},
            "players": {pid: {"name": self.names[pid], "color": p["color"], "res": self.shown[pid]["res"],
                              "pop": self.shown[pid]["pop"], "advances": p["advances"], "done": p["done"],
                              "alive": p["alive"], "score": self.score(pid)} for pid, p in self.players.items()},
            "log": {str(i): line for i, line in enumerate(self.log)},
        }

    def stores(self, pid):
        """{sid: {"stock", "cap", "usable"}} for pid's storage structures."""
        nets = logistics.networks(self, pid)
        ok = {s["id"] for s in logistics.usable(self, pid, nets)}
        return {s["id"]: {"stock": s["stock"], "cap": logistics.capacity(s), "usable": s["id"] in ok}
                for s in self.structures.values() if s["owner"] == pid and logistics.capacity(s)}

    def private(self, pid):
        """{"view": the map as pid sees it} for everyone (pid None = a spectator: the whole map),
        plus pid's stock, orders, forecast and planning help while they're still playing."""
        staffed = {s["id"] for x in self.alive() for s in staffing(self, x)[0]}
        out = {"view": vision.view(self, pid, staffed)}
        if pid not in self.players or not self.players[pid]["alive"] or self.result is not None:
            return out
        p = self.players[pid]
        recruit = {}
        for s in self.structures.values():
            if s["owner"] == pid and STRUCTURES[s["type"]]["recruits"]:
                recruit[s["id"]] = {u: orders.recruit_problem(self, pid, s, u) or "" for u in STRUCTURES[s["type"]]["recruits"]}
        return {
            **out,
            "res": logistics.stock(self, pid), "pop": p["pop"], "done": p["done"],
            "stores": self.stores(pid), "held": {s["id"]: s["held"] for s in self.structures.values()
                                                 if s["owner"] == pid and s["held"]}, "orders": self.orders[pid], "report": report(self, pid),
            "reach": {uid: sorted(movement.reach(self, uid)) for uid, u in self.units.items() if u["owner"] == pid},
            "recruit": recruit,
            "found": {uid: [r for r in range(6) if not orders.found_problem(self, pid, u, r)]
                      for uid, u in self.units.items() if u["owner"] == pid and UNITS[u["type"]]["settler"]},
        }

