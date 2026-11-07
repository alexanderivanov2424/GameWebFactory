"""Smugglers: the board (a graph of planets and dots) and its loader.

Boards are JSON files in content/boards/ (fields: content/README.md). Nodes are planets and
dots: a route of length L between two nodes has L-1 dots, named "<route>.<n>" (n = 1..L-1,
counted from the route's "from" end). A route end may be a dot of another route whose ends
are both planets ("r3.2"), so routes can branch off mid-way. One step = one edge.

    board = BOARDS["outer-rim"]          # every valid board, by file name
    board.planets                        # {id: {"name", "color", "x", "y"}}
    board.nodes                          # {node: (x, y)}; planets and dots
    board.is_planet(node)
    board.neighbours(node)               # set of nodes one step away
    board.reach(start, steps, blocked=(), stops=())
        # {node: distance} reachable in 1..steps steps (start left out); never enters a
        # `blocked` node and never moves on from a `stops` node (it can end there)
    board.distance(a, b, blocked=())     # steps on the shortest path, or None
    board.connected(nodes, blocked)      # all of `nodes` in one piece once `blocked` are removed
    board.public()                       # static JSON for clients (planets, node positions, edges)
"""

import logging
import re
from collections import deque
from pathlib import Path

from gamekit.data import load_json_dir, text, whole

log = logging.getLogger("smugglers")
CONTENT = Path(__file__).resolve().parent.parent / "content"
COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


class Board:
    def __init__(self, board_id, data):
        self.id = board_id
        self.name = text(data, "name", 40, required=True)
        self.width = whole(data, "width", 200, 4000)
        self.height = whole(data, "height", 200, 4000)
        self.planets = self._parse_planets(data.get("planets"))
        self.nodes = {pid: (p["x"], p["y"]) for pid, p in self.planets.items()}
        self.adjacent = {pid: set() for pid in self.planets}
        self.edges = []
        self._parse_routes(data.get("routes"))
        self.starts = self._planet_list(data.get("starts"), "starts")
        home = data.get("interpolHome")
        if home not in self.planets:
            raise ValueError("interpolHome must be a planet id")
        self.interpol_home = home
        if not self.connected(self.nodes):
            raise ValueError("every planet and dot must be reachable from every other")

    def _parse_planets(self, raw):
        if not isinstance(raw, dict) or not 2 <= len(raw) <= 60:
            raise ValueError("planets must be an object with 2 to 60 planets")
        planets, colors = {}, set()
        for pid, data in raw.items():
            if not re.match(r"^[a-z][a-z0-9_-]{0,30}$", pid) or not isinstance(data, dict):
                raise ValueError(f"bad planet {pid!r}")
            color = data.get("color")
            if not isinstance(color, str) or not COLOR.match(color):
                raise ValueError(f"planet {pid} needs a color like #a1b2c3")
            if color.lower() in colors:
                raise ValueError(f"planet {pid}: every planet needs its own color")
            colors.add(color.lower())
            planets[pid] = {
                "name": text(data, "name", 24, required=True),
                "color": color,
                "x": whole(data, "x", 0, self.width),
                "y": whole(data, "y", 0, self.height),
            }
        return planets

    def _parse_routes(self, raw):
        if not isinstance(raw, dict) or not raw:
            raise ValueError("routes must be a non-empty object")
        lengths = {}
        for rid, route in raw.items():
            if not re.match(r"^[a-z0-9_-]{1,20}$", rid) or not isinstance(route, dict):
                raise ValueError(f"bad route {rid!r}")
            lengths[rid] = whole(route, "length", 1, 9)
        # First the dots of every route between two planets (others may branch off them),
        # then every route's chain of edges.
        for rid, route in raw.items():
            ends = (route.get("from"), route.get("to"))
            if all(end in self.planets for end in ends):
                self._add_dots(rid, ends, lengths[rid])
        for rid, route in raw.items():
            ends = (route.get("from"), route.get("to"))
            for end in ends:
                if end not in self.nodes:
                    raise ValueError(f"route {rid}: {end!r} isn't a planet or a dot of a planet-to-planet route")
            if ends[0] == ends[1]:
                raise ValueError(f"route {rid} must join two different places")
            if not all(end in self.planets for end in ends):
                self._add_dots(rid, ends, lengths[rid])
            chain = [ends[0]] + [f"{rid}.{n}" for n in range(1, lengths[rid])] + [ends[1]]
            for a, b in zip(chain, chain[1:]):
                self.adjacent[a].add(b)
                self.adjacent[b].add(a)
                self.edges.append([a, b])

    def _add_dots(self, rid, ends, length):
        (x1, y1), (x2, y2) = self.nodes[ends[0]], self.nodes[ends[1]]
        for n in range(1, length):
            dot = f"{rid}.{n}"
            self.nodes[dot] = (round(x1 + (x2 - x1) * n / length), round(y1 + (y2 - y1) * n / length))
            self.adjacent[dot] = set()

    def _planet_list(self, raw, key):
        if not isinstance(raw, list) or not raw or any(p not in self.planets for p in raw):
            raise ValueError(f"{key} must be a list of planet ids")
        return list(raw)

    # --- Geometry ---------------------------------------------------------------------------

    def is_planet(self, node):
        return node in self.planets

    def neighbours(self, node):
        return self.adjacent.get(node, set())

    def reach(self, start, steps, blocked=(), stops=()):
        seen = {start: 0}
        queue = deque([start])
        while queue:
            node = queue.popleft()
            if seen[node] >= steps or (node != start and node in stops):
                continue
            for nxt in sorted(self.adjacent[node]):
                if nxt not in seen and nxt not in blocked:
                    seen[nxt] = seen[node] + 1
                    queue.append(nxt)
        seen.pop(start)
        return seen

    def distance(self, a, b, blocked=()):
        if a == b:
            return 0
        return self.reach(a, len(self.nodes), blocked).get(b)

    def connected(self, nodes, blocked=()):
        nodes = [n for n in nodes if n not in blocked]
        if not nodes:
            return True
        found = set(self.reach(nodes[0], len(self.nodes), blocked)) | {nodes[0]}
        return all(n in found for n in nodes)

    def public(self):
        return {
            "id": self.id,
            "name": self.name,
            "width": self.width,
            "height": self.height,
            "planets": self.planets,
            "nodes": {node: list(xy) for node, xy in self.nodes.items()},
            "edges": self.edges,
        }


def load_boards(folder=CONTENT / "boards"):
    return load_json_dir(folder, Board, log)


BOARDS = load_boards()
