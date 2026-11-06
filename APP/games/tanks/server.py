"""Tanks: Fog of War.

Played on an n x n grid. At the start every player secretly picks a square for their tank
and lays MINES_AT_START mines anywhere (several tanks or mines may share a square, since
refusing would reveal where someone is). Tank and mine locations stay hidden; actions, HP
and hits are public.

Turns use turn counters (see turns.py): players start at 1, 2, 3, ... in random order.
The lowest counter acts next (ties: whoever reached that value first). Acting adds the
action's cost to your counter, so cheap actions can let you act again before others.

Actions (costs in COSTS unless a setting):
  scan       Contiguous rows or columns, from-to inclusive. Over half the board: 1, a single
             line: 3, otherwise 2 (see scan_cost). Tells only the scanner (privately) whether
             any other living tank is in that area.
  spray      1 damage to every tank in a 2x2 area anywhere on the board. Cost: setting.
  artillery  2 damage to every tank on one square anywhere on the board. Cost: setting.
  blast      Shoots up, down, left or right from your square until it hits a tank, a wall or
             the edge. A hit deals 4 damage to every tank on the first occupied square and
             makes that square public; a miss says only "miss" (not even the direction).
  move       One square up, down, left or right, not through a wall. Public, but not where.
  heal       +1 HP, up to the starting HP.
  wall       Build a wall between any two neighboring squares, if the board stays connected.
  unwall     Remove any wall.
  mine       Lay a mine on a square at most MINE_RANGE steps away (walking, so walls count).
You never damage yourself (except by walking onto a mine).

Mines: moving onto a square with mines sets them all off and removes them: 1 damage to every
tank on that square, the mover included. Starting on a mine, or a mine laid on your square,
does nothing. Only the owner knows where their mines are; they're told privately when one
goes off.

Shields: a tank that takes damage is shielded until its next turn starts. Hits on a shielded
tank still count (they're public and stop a blast) but deal no damage.

Walls sit between neighboring squares and are public. Each starting wall is placed with the
"wall chance" probability, but only if every square stays reachable from every other,
so 100% gives a perfect maze. Walls block movement, blasts and mine range; scan, spray and
artillery ignore them.

Settings:       {"boardSize": 8, "hp": 5, "sprayCost": 2, "artilleryCost": 3, "wallChance": 15}
Game messages:  {"action": "place", "row": r, "col": c, "mines": [[r, c], ...]}   (placing stage)
                {"action": "scan", "axis": "row"|"col", "from": a, "to": b}
                {"action": "spray", "row": r, "col": c}               (top-left of the 2x2)
                {"action": "artillery", "row": r, "col": c}
                {"action": "blast", "dir": "up"|"down"|"left"|"right"}
                {"action": "move", "row": r, "col": c}                (destination)
                {"action": "heal"}
                {"action": "wall" | "unwall", "cells": [[r1, c1], [r2, c2]]}
                {"action": "mine", "row": r, "col": c}
"""

import random

from gamekit import FINISHED, Int, LobbyError, LobbyGame, TurnQueue
from gamekit.validate import cell, one_of

SPRAY_DAMAGE = 1
ARTILLERY_DAMAGE = 2
BLAST_DAMAGE = 4
MINE_DAMAGE = 1
HEAL_AMOUNT = 1
MINES_AT_START = 2
MINE_RANGE = 3
COSTS = {"move": 1, "blast": 5, "heal": 3, "wall": 1, "unwall": 2, "mine": 1}
SCAN_COSTS = {"over_half": 1, "other": 2, "single": 3}

DIRECTIONS = {"up": (-1, 0), "down": (1, 0), "left": (0, -1), "right": (0, 1)}

PLACING, ACTION = "placing", "action"


def scan_cost(size, lines):
    """1 for more than half the board, 3 for a single line, 2 otherwise (exactly half included)."""
    if lines == 1:
        return SCAN_COSTS["single"]
    if lines * 2 > size:
        return SCAN_COSTS["over_half"]
    return SCAN_COSTS["other"]


def neighbors(size, cell):
    r, c = cell
    for nr, nc in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
        if 0 <= nr < size and 0 <= nc < size:
            yield (nr, nc)


def wall_key(a, b):
    """Walls are stored as (cell, cell) with the smaller cell first."""
    return (a, b) if a < b else (b, a)


def distances(size, walls, start, limit=None):
    """Steps from start to every square reachable without crossing a wall (up to limit)."""
    dist = {start: 0}
    frontier = [start]
    while frontier and (limit is None or dist[frontier[0]] < limit):
        nxt_frontier = []
        for cell in frontier:
            for nxt in neighbors(size, cell):
                if nxt not in dist and wall_key(cell, nxt) not in walls:
                    dist[nxt] = dist[cell] + 1
                    nxt_frontier.append(nxt)
        frontier = nxt_frontier
    return dist


def reachable(size, walls, start, goal):
    """Can you get from start to goal without crossing a wall?"""
    return goal in distances(size, walls, start)


def generate_walls(size, chance):
    """Randomly wall off neighboring squares (chance in %) without ever disconnecting the board.

    Edges are tried in random order; a wall is kept only if its two squares are still
    connected some other way. Since the board starts connected and each step keeps it
    connected, the whole board always stays connected. At 100% this leaves a spanning tree,
    i.e. a perfect maze.
    """
    edges = [((r, c), (r, c + 1)) for r in range(size) for c in range(size - 1)]
    edges += [((r, c), (r + 1, c)) for r in range(size - 1) for c in range(size)]
    random.shuffle(edges)
    walls = set()
    for a, b in edges:
        if random.random() * 100 >= chance:
            continue
        walls.add((a, b))
        if not reachable(size, walls, a, b):
            walls.discard((a, b))
    return walls


class Game(LobbyGame):
    MIN_PLAYERS = 2
    MAX_PLAYERS = 8
    SETTINGS = {
        "boardSize": Int("Board size", default=8, low=4, high=12),
        "hp": Int("Starting HP", default=5, low=1, high=20),
        "sprayCost": Int("Spray cost", default=2, low=1, high=20),
        "artilleryCost": Int("Artillery cost", default=3, low=1, high=20),
        "wallChance": Int("Wall chance", default=15, low=0, high=100, suffix="%"),
    }
    ACTIONS = {
        "place": "place",
        "scan": "scan",
        "spray": "spray",
        "artillery": "artillery",
        "blast": "blast",
        "move": "move",
        "heal": "heal",
        "wall": "build_wall",
        "unwall": "remove_wall",
        "mine": "lay_mine",
    }

    def __init__(self, room):
        super().__init__(room)
        self.reset_game()

    # --- Game state --------------------------------------------------------------

    def reset_game(self):
        self.stage = None
        self.size = 0
        self.walls = set()  # {((r1, c1), (r2, c2))}, see wall_key
        self.names = {}  # public id -> name, fixed at the start
        self.hp = {}  # public id -> HP
        self.locations = {}  # public id -> [row, col]  (secret until the game ends)
        self.mines = []  # [{"owner": pid, "row": r, "col": c}]  (secret until the game ends)
        self.shielded = set()  # public ids shielded until their next turn
        self.queue = TurnQueue()  # living players only
        self.log = []  # public action log
        self.notes = {}  # public id -> {log index: {...}}  private details of log entries

    def start_game(self):
        self.size = self.settings["boardSize"]
        self.walls = generate_walls(self.size, self.settings["wallChance"])
        self.names = {p.id: p.name for p in self.players}
        self.hp = {pid: self.settings["hp"] for pid in self.names}
        self.locations = {}
        self.mines = []
        self.shielded = set()
        order = list(self.names)
        random.shuffle(order)
        self.queue = TurnQueue(order, staggered=True)  # starting values 1, 2, 3, ...
        self.log = []
        self.notes = {pid: {} for pid in self.names}
        self.stage = PLACING

    def costs(self):
        return {
            **COSTS,
            "spray": self.settings["sprayCost"],
            "artillery": self.settings["artilleryCost"],
            # scan[k - 1] = cost of scanning k rows or columns
            "scan": [scan_cost(self.size, k) for k in range(1, self.size + 1)],
        }

    def game_state(self):
        offsets = self.queue.offsets()
        order = self.queue.order() + [pid for pid in self.names if pid not in self.queue]
        finished = self.phase == FINISHED
        return {
            "stage": self.stage,
            "size": self.size,
            "walls": [[*a, *b] for a, b in sorted(self.walls)],  # [r1, c1, r2, c2]
            "maxHp": self.settings["hp"],
            "costs": self.costs(),
            "rules": {
                "minesAtStart": MINES_AT_START,
                "mineRange": MINE_RANGE,
                "damage": {"spray": SPRAY_DAMAGE, "artillery": ARTILLERY_DAMAGE, "blast": BLAST_DAMAGE, "mine": MINE_DAMAGE},
            },
            "current": self.queue.current() if self.stage == ACTION and not finished else None,
            "players": [
                {
                    "id": pid,
                    "name": self.names[pid],
                    "hp": self.hp[pid],
                    "alive": pid in self.queue,
                    "placed": pid in self.locations,
                    "shielded": pid in self.shielded,
                    "turn": offsets.get(pid),
                }
                for pid in order
            ],
            "log": self.log,
            # Revealed only once the game is over.
            "locations": self.locations if finished else None,
            "mines": self.mines if finished else None,
        }

    def private_state(self, member):
        if member.id not in self.names:
            return None
        return {
            "location": self.locations.get(member.id),
            "mines": [[m["row"], m["col"]] for m in self.mines if m["owner"] == member.id],
            "notes": self.notes.get(member.id, {}),
        }

    # --- Actions -----------------------------------------------------------------

    async def on_game_message(self, member, data):
        if member.id not in self.queue:
            raise LobbyError("Your tank has been destroyed.")

        if self.stage == PLACING:
            if data.get("action") != "place":
                raise LobbyError("Choose your hidden location first.")
            await self.dispatch(member, data)
            return

        if self.queue.current() != member.id:
            raise LobbyError("It's not your turn.")
        if data.get("action") == "place":
            raise LobbyError("Unknown action.")
        await self.dispatch(member, data)
        self.after_action()

    def place(self, member, data):
        pid = member.id
        if pid in self.locations:
            raise LobbyError("You've already chosen your location.")
        tank = self.cell(data)
        mines = data.get("mines")
        if not isinstance(mines, list) or len(mines) != MINES_AT_START:
            raise LobbyError(f"Lay exactly {MINES_AT_START} mines.")
        cells = [self.cell_from(m) for m in mines]
        if len(set(cells)) != len(cells):
            raise LobbyError("Put your mines on different squares.")
        self.locations[pid] = list(tank)
        self.mines += [{"owner": pid, "row": r, "col": c} for r, c in cells]
        self.check_all_placed()

    def scan(self, member, data):
        pid = member.id
        axis = one_of(data.get("axis"), ("row", "col"), "Scan rows or columns.")
        start, end = data.get("from"), data.get("to")
        if type(start) is not int or type(end) is not int or not (0 <= start <= end < self.size):
            raise LobbyError("Pick a valid range to scan.")
        cost = scan_cost(self.size, end - start + 1)
        index = 0 if axis == "row" else 1
        found = any(
            start <= self.locations[other][index] <= end
            for other in self.queue.ids()
            if other != pid
        )
        self.notes[pid][len(self.log)] = {"found": found}
        self.log.append({"type": "scan", "actor": pid, "axis": axis, "from": start, "to": end, "cost": cost})
        self.queue.advance(pid, cost)

    def spray(self, member, data):
        pid = member.id
        row, col = self.cell(data)
        if row > self.size - 2 or col > self.size - 2:
            raise LobbyError("The 2x2 area must fit on the board.")
        area = {(row, col), (row + 1, col), (row, col + 1), (row + 1, col + 1)}
        cost = self.settings["sprayCost"]
        hits = self.damage(area, SPRAY_DAMAGE, exclude=pid)
        self.log.append({"type": "spray", "actor": pid, "row": row, "col": col, "cost": cost, "hits": hits})
        self.queue.advance(pid, cost)

    def artillery(self, member, data):
        pid = member.id
        row, col = self.cell(data)
        cost = self.settings["artilleryCost"]
        hits = self.damage({(row, col)}, ARTILLERY_DAMAGE, exclude=pid)
        self.log.append({"type": "artillery", "actor": pid, "row": row, "col": col, "cost": cost, "hits": hits})
        self.queue.advance(pid, cost)

    def blast(self, member, data):
        pid = member.id
        direction = one_of(data.get("dir"), tuple(DIRECTIONS), "Blast up, down, left or right.")
        dr, dc = DIRECTIONS[direction]
        cost = COSTS["blast"]
        r, c = self.locations[pid]
        target = None
        while True:
            nxt = (r + dr, c + dc)
            if not (0 <= nxt[0] < self.size and 0 <= nxt[1] < self.size):
                break
            if wall_key((r, c), nxt) in self.walls:
                break
            r, c = nxt
            if any(tuple(self.locations[o]) == nxt for o in self.queue.ids() if o != pid):
                target = nxt
                break
        # The direction stays private: on a miss nothing else is public.
        self.notes[pid][len(self.log)] = {"dir": direction}
        entry = {"type": "blast", "actor": pid, "cost": cost, "hit": None, "hits": []}
        if target:
            entry["hit"] = list(target)
            entry["hits"] = self.damage({target}, BLAST_DAMAGE, exclude=pid)
        self.log.append(entry)
        self.queue.advance(pid, cost)

    def move(self, member, data):
        pid = member.id
        row, col = self.cell(data)
        my_row, my_col = self.locations[pid]
        if abs(row - my_row) + abs(col - my_col) != 1:
            raise LobbyError("You can only move one square up, down, left or right.")
        if wall_key((my_row, my_col), (row, col)) in self.walls:
            raise LobbyError("A wall is in the way.")
        cost = COSTS["move"]
        self.locations[pid] = [row, col]
        # The destination is secret: the log only says that you moved (and any mine it set off).
        entry = {"type": "move", "actor": pid, "cost": cost}
        triggered = [m for m in self.mines if (m["row"], m["col"]) == (row, col)]
        if triggered:
            index = len(self.log)
            self.mines = [m for m in self.mines if m not in triggered]
            for owner in {m["owner"] for m in triggered}:
                if owner in self.notes:
                    self.notes[owner][index] = {"mineAt": [row, col]}
            entry["mine"] = True
            entry["hits"] = self.damage({(row, col)}, MINE_DAMAGE)
        self.log.append(entry)
        if pid in self.queue:  # the mine may have destroyed the mover
            self.queue.advance(pid, cost)

    def heal(self, member, data):
        pid = member.id
        if self.hp[pid] >= self.settings["hp"]:
            raise LobbyError("Your tank is already at full HP.")
        cost = COSTS["heal"]
        self.hp[pid] = min(self.settings["hp"], self.hp[pid] + HEAL_AMOUNT)
        self.log.append({"type": "heal", "actor": pid, "cost": cost, "amount": HEAL_AMOUNT})
        self.queue.advance(pid, cost)

    def build_wall(self, member, data):
        pid = member.id
        a, b = self.edge(data)
        if wall_key(a, b) in self.walls:
            raise LobbyError("There's already a wall there.")
        walls = self.walls | {wall_key(a, b)}
        if not reachable(self.size, walls, a, b):
            raise LobbyError("That wall would cut the board in two.")
        self.walls = walls
        cost = COSTS["wall"]
        self.log.append({"type": "wall", "actor": pid, "cost": cost, "cells": [list(a), list(b)]})
        self.queue.advance(pid, cost)

    def remove_wall(self, member, data):
        pid = member.id
        a, b = self.edge(data)
        if wall_key(a, b) not in self.walls:
            raise LobbyError("There's no wall there.")
        self.walls.discard(wall_key(a, b))
        cost = COSTS["unwall"]
        self.log.append({"type": "unwall", "actor": pid, "cost": cost, "cells": [list(a), list(b)]})
        self.queue.advance(pid, cost)

    def lay_mine(self, member, data):
        pid = member.id
        row, col = self.cell(data)
        reach = distances(self.size, self.walls, tuple(self.locations[pid]), MINE_RANGE)
        if (row, col) not in reach:
            raise LobbyError(f"Mines must be at most {MINE_RANGE} steps from your tank.")
        cost = COSTS["mine"]
        self.mines.append({"owner": pid, "row": row, "col": col})
        self.notes[pid][len(self.log)] = {"cell": [row, col]}
        self.log.append({"type": "mine", "actor": pid, "cost": cost})
        self.queue.advance(pid, cost)

    def damage(self, area, amount, exclude=None):
        """Hit every living tank in area. Shielded tanks take no damage; others become shielded."""
        hits = []
        for target in self.queue.ids():
            if target == exclude or tuple(self.locations[target]) not in area:
                continue
            if target in self.shielded:
                hits.append({"player": target, "damage": 0, "destroyed": False, "shielded": True})
                continue
            self.hp[target] = max(0, self.hp[target] - amount)
            destroyed = self.hp[target] == 0
            if destroyed:
                self.queue.remove(target)
            else:
                self.shielded.add(target)
            hits.append({"player": target, "damage": amount, "destroyed": destroyed})
        return hits

    def after_action(self):
        """Start the next turn (dropping that tank's shield) or end the game."""
        if len(self.queue) == 0:
            self.finish({"winner": None, "reason": "No tanks are left."})
        elif len(self.queue) == 1:
            self.finish({"winner": self.queue.current(), "reason": None})
        elif self.stage == ACTION:
            self.shielded.discard(self.queue.current())

    def cell_from(self, value):
        return cell(value, self.size)

    def cell(self, data):
        return cell([data.get("row"), data.get("col")], self.size)

    def edge(self, data):
        cells = data.get("cells")
        if not isinstance(cells, list) or len(cells) != 2:
            raise LobbyError("Pick two neighboring squares.")
        a, b = (self.cell_from(c) for c in cells)
        if abs(a[0] - b[0]) + abs(a[1] - b[1]) != 1:
            raise LobbyError("Pick two neighboring squares.")
        return wall_key(a, b)

    def check_all_placed(self):
        if self.stage == PLACING and all(pid in self.locations for pid in self.queue.ids()):
            self.stage = ACTION
            self.log.append({"type": "start"})

    # --- Players leaving -----------------------------------------------------------

    def on_player_removed(self, member):
        if member.id not in self.queue:
            return
        self.queue.remove(member.id)
        self.shielded.discard(member.id)
        self.log.append({"type": "left", "actor": member.id})
        if len(self.queue) == 1:
            self.finish({"winner": self.queue.current(), "reason": "Everyone else left."})
        else:
            self.check_all_placed()
            if self.stage == ACTION:
                self.shielded.discard(self.queue.current())
