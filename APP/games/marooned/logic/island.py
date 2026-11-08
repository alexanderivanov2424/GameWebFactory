"""Marooned: the island grid, the tile deck and what lies on each explored square.

Squares are (row, col) on a size x size grid; only explored squares have a tile. Camp is a
built-in tile on the middle of the bottom row, explored from the start; its pile is the
camp stockpile. Other tiles come from the tile deck (content/tiles, counts per map size).

    island = Island(size, rng, supplies)   # supplies: the stockpile at the start
    island.tile(cell)              # the square's tile dict, or None while unexplored
    island.explorable(cell)        # on the grid and not explored yet
    island.neighbours(cell)        # the 4 squares around it that are on the grid
    island.draw(2)                 # tile cards [{"uid", "card"}] for an explorer to pick from
    island.place(cell, tile_id, by)    # puts a tile down; returns the cells explored
                                       # (more than one when the tile reveals its neighbours)
    island.bottom(cards)           # unchosen cards go face down under the deck
    island.move_cost(cell)         # entering this square
    island.public()                # {"r,c": {...}} for the clients

A tile dict: {"type", "res": {item: n, -1 = unlimited}, "pile": {item: n}, "searches": n,
"by": public id of the explorer (None for camp)}.
"""

from gamekit import Deck

from .content import TILES, UNLIMITED, card_list

CAMP_TILE = {
    "id": "camp", "name": "Camp", "icon": "⛺", "color": "#e8c27a", "moveCost": 1,
    "resources": {}, "searches": 0, "shelter": 0, "reveals": False, "points": 0,
    "text": "The crash site: the stockpile, the shelter and the raft are here.",
}


def tile_types():
    return {"camp": CAMP_TILE, **TILES}


def key(cell):
    return f"{cell[0]},{cell[1]}"


class Island:
    def __init__(self, size, rng, supplies=None):
        self.size = size
        self.rng = rng
        self.camp = (size - 1, size // 2)
        self.tiles = {self.camp: {"type": "camp", "res": {}, "pile": dict(supplies or {}), "searches": 0, "by": None}}
        self.deck = Deck(self._deck_cards(), rng=rng)

    def _deck_cards(self):
        bracket = "small" if self.size <= 7 else "large"
        cards = card_list(TILES, lambda tile: tile["count"][bracket])
        needed = self.size * self.size  # every square but camp, plus one spare to choose from
        weights = [tile_id for tile_id, tile in TILES.items() if tile["count"][bracket]] or list(TILES)
        while len(cards) < needed:
            cards.append(self.rng.choice(weights))
        return cards

    # --- Geometry --------------------------------------------------------------------

    def on_grid(self, cell):
        return 0 <= cell[0] < self.size and 0 <= cell[1] < self.size

    def neighbours(self, cell):
        row, col = cell
        around = ((row - 1, col), (row + 1, col), (row, col - 1), (row, col + 1))
        return [c for c in around if self.on_grid(c)]

    def adjacent(self, a, b):
        return abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1

    def tile(self, cell):
        return self.tiles.get(tuple(cell))

    def kind(self, cell):
        tile = self.tile(cell)
        return tile_types()[tile["type"]] if tile else None

    def explorable(self, cell):
        return self.on_grid(cell) and tuple(cell) not in self.tiles

    def move_cost(self, cell):
        return self.kind(cell)["moveCost"]

    def all_explored(self):
        return len(self.tiles) == self.size * self.size

    # --- Exploring -------------------------------------------------------------------

    def draw(self, count):
        return self.deck.draw(count)

    def bottom(self, cards):
        for card in cards:
            self.deck.draw_pile.insert(0, card)

    def place(self, cell, tile_id, by):
        """Put tile_id on cell; a revealing tile also explores its unexplored neighbours
        with the top cards of the deck (no choice, and they don't reveal further)."""
        cell = tuple(cell)
        self._put(cell, tile_id, by)
        explored = [cell]
        if TILES[tile_id]["reveals"]:
            for near in self.neighbours(cell):
                if self.explorable(near):
                    cards = self.deck.draw(1)
                    if not cards:
                        break
                    self._put(near, cards[0]["card"], by)
                    explored.append(near)
        return explored

    def _put(self, cell, tile_id, by):
        kind = TILES[tile_id]
        self.tiles[cell] = {
            "type": tile_id, "res": dict(kind["resources"]), "pile": {},
            "searches": kind["searches"], "by": by,
        }

    # --- Resources and piles ------------------------------------------------------------

    def available(self, cell, item):
        amount = self.tile(cell)["res"].get(item, 0)
        return amount == UNLIMITED or amount > 0

    def take_resource(self, cell, item, count):
        """Take up to count of a tile resource; returns how many were taken."""
        res = self.tile(cell)["res"]
        amount = res.get(item, 0)
        if amount == UNLIMITED:
            return count
        taken = min(amount, count)
        res[item] = amount - taken
        if res[item] == 0:
            del res[item]
        return taken

    def pile(self, cell):
        return self.tile(cell)["pile"]

    # --- What clients see ----------------------------------------------------------------

    def public(self):
        tiles = {}
        for cell, tile in self.tiles.items():
            entry = {"type": tile["type"]}
            if tile["res"]:
                entry["res"] = dict(tile["res"])
            if tile["pile"]:
                entry["pile"] = dict(tile["pile"])
            if tile["searches"]:
                entry["searches"] = tile["searches"]
            if tile["by"]:
                entry["by"] = tile["by"]
            tiles[key(cell)] = entry
        return tiles
