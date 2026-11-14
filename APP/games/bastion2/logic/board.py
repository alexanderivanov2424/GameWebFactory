"""Bastion 2: the board, an unbounded square grid of one-tile structures.

There is no terrain: every tile is buildable. The board's shown area (`bounds`) is the box around
every structure plus MARGIN tiles (or the START area while it's empty); the client draws the grid
there and keeps the camera inside it, and castles must go inside it.

    board = Board()
    board.structures   {(x, y): {"kind", "owner", "pending"}}  pending: played this turn, built
                       when its owner's turn ends
    board.add(cell, kind, owner, pending=False) / board.remove(cell)
    board.bounds()     (x0, y0, x1, y1), inclusive
    board.next_to(cell)              the 4 orthogonal neighbours
    board.build_spots(pid)           empty tiles next to the player's built structures
    board.castle_spots(pid)          empty tiles in bounds at least CASTLE_GAP from other players
    board.owned(pid, built=True)     the player's cells (built only, or pending too)
"""

MARGIN = 6
START = (-7, -5, 7, 5)
CASTLE_GAP = 5  # Chebyshev distance from any other player's structure
LIMIT = 500     # coordinates stay within -LIMIT..LIMIT


class Board:
    def __init__(self):
        self.structures = {}

    def add(self, cell, kind, owner, pending=False):
        self.structures[cell] = {"kind": kind, "owner": owner, "pending": pending}

    def remove(self, cell):
        self.structures.pop(cell, None)

    def bounds(self):
        if not self.structures:
            return START
        xs = [x for x, _ in self.structures]
        ys = [y for _, y in self.structures]
        return (min(xs) - MARGIN, min(ys) - MARGIN, max(xs) + MARGIN, max(ys) + MARGIN)

    def in_bounds(self, cell):
        x0, y0, x1, y1 = self.bounds()
        return x0 <= cell[0] <= x1 and y0 <= cell[1] <= y1

    @staticmethod
    def next_to(cell):
        x, y = cell
        return [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]

    def owned(self, pid, built=True):
        return [c for c, s in self.structures.items() if s["owner"] == pid and not (built and s["pending"])]

    def build_spots(self, pid):
        spots = set()
        for cell in self.owned(pid):
            for n in self.next_to(cell):
                if n not in self.structures and all(abs(v) <= LIMIT for v in n):
                    spots.add(n)
        return sorted(spots)

    def castle_reason(self, pid, cell):
        if cell in self.structures:
            return "That tile is taken."
        if not self.in_bounds(cell):
            return "Place your castle on the map."
        for (x, y), s in self.structures.items():
            if s["owner"] != pid and max(abs(x - cell[0]), abs(y - cell[1])) < CASTLE_GAP:
                return f"Castles go at least {CASTLE_GAP} tiles from other players' cities."
        return ""

    def castle_spots(self, pid):
        x0, y0, x1, y1 = self.bounds()
        return [(x, y) for y in range(y0, y1 + 1) for x in range(x0, x1 + 1) if not self.castle_reason(pid, (x, y))]
