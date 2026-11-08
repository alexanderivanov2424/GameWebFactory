"""Bastion: the shared board, a map plus the structures built on it, and the placement rules.

    board = Board(MAPS["valley"])
    board.place(card, x, y, owner)  -> "built" | "upgraded"   (LobbyError if not allowed)
    board.upgrade(x, y)             -> the upgraded Structure (a targeted order)
    board.demolish(x, y, pid)       removes pid's structure (or one whose owner left)
    board.at(x, y)                  Structure or None
    board.of_kind(kind)             [Structure, ...] in build order
    board.near(x, y, kind, reach)   structures of a kind within `reach` (1.5 = the 8 neighbours)
    board.rally(x, y)               the road cell a barracks' soldiers hold (nearest the keep), or None
    board.boost(x, y, kind)         summed "bonus" of the structures of `kind` next to x, y
                                    (forges: damage, watchtowers: range)
    board.public()                  {"x,y": {card, level, uid, owner?, hp?, maxHp?, damage?, range?,
                                    rally?}} for clients: towers and barracks carry their damage
                                    (and range) with bonuses, barracks the cell they hold

Placement: road kinds (walls, traps) go on road cells, never on an entrance or the keep;
ground kinds go on grass that isn't road; barracks must touch the road (8 neighbours).
Playing a structure card on the same structure raises its level (up to the card's maxLevel)
and repairs it fully.
"""

import itertools
import math
from dataclasses import dataclass

from gamekit import LobbyError

from .cards import CARDS, stat

ADJACENT = 1.5  # Euclidean reach of "next to" (the 8 neighbours)


@dataclass
class Structure:
    uid: int
    card: str
    x: int
    y: int
    owner: str | None
    level: int = 1
    hp: float = 0  # walls only

    @property
    def kind(self):
        return CARDS[self.card]["kind"]

    def max_hp(self):
        return stat(CARDS[self.card], "hp", self.level) if self.kind == "wall" else 0

    def public(self):
        info = {"card": self.card, "level": self.level, "uid": self.uid}
        if self.owner:
            info["owner"] = self.owner
        if self.kind == "wall":
            info["hp"] = math.ceil(self.hp)
            info["maxHp"] = self.max_hp()
        return info


def key(x, y):
    return f"{x},{y}"


def distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


class Board:
    def __init__(self, game_map):
        self.map = game_map
        self.structures = {}  # (x, y) -> Structure
        self._uids = itertools.count(1)

    def at(self, x, y):
        return self.structures.get((x, y))

    def of_kind(self, kind):
        return sorted((s for s in self.structures.values() if s.kind == kind), key=lambda s: s.uid)

    def near(self, x, y, kind, reach=ADJACENT):
        return [s for s in self.of_kind(kind) if (s.x, s.y) != (x, y) and distance((s.x, s.y), (x, y)) <= reach]

    def boost(self, x, y, kind):
        return sum(stat(CARDS[s.card], "bonus", s.level) for s in self.near(x, y, kind))

    def rally(self, x, y):
        cells = [c for c in self.map.road_cells if distance(c, (x, y)) <= ADJACENT
                 and c not in self.map.entrances and c != self.map.keep]
        if not cells:
            return None
        return min(cells, key=lambda c: (self.map.remaining[c], c))

    def check(self, card, x, y):
        """Raise LobbyError unless `card` may be built (or upgraded) at x, y. Returns the existing structure."""
        game_map = self.map
        if not game_map.inside(x, y):
            raise LobbyError("That's off the map.")
        cell = (x, y)
        existing = self.at(x, y)
        if existing:
            if existing.card != card["id"]:
                raise LobbyError("Something is already built there (play the same card on it to upgrade it).")
            if existing.level >= card["maxLevel"]:
                raise LobbyError(f"That {card['name']} is already at its highest level.")
            return existing
        if cell == game_map.keep:
            raise LobbyError("That's the keep.")
        if card["place"] == "road":
            if cell not in game_map.road_cells:
                raise LobbyError(f"{card['name']} goes on the road.")
            if cell in game_map.entrances:
                raise LobbyError("Nothing can be built where the enemy enters.")
        else:
            if cell in game_map.road_cells:
                raise LobbyError(f"{card['name']} can't go on the road.")
            if game_map.ground(x, y) != ".":
                raise LobbyError("You can only build on grass.")
            if card["kind"] == "barracks" and self.rally(x, y) is None:
                raise LobbyError("Barracks must be next to the road.")
        return None

    def place(self, card, x, y, owner):
        existing = self.check(card, x, y)
        if existing:
            existing.level += 1
            existing.hp = existing.max_hp()
            return "upgraded"
        structure = Structure(next(self._uids), card["id"], x, y, owner)
        structure.hp = structure.max_hp()
        self.structures[(x, y)] = structure
        return "built"

    def upgrade(self, x, y):
        existing = self.at(x, y) if self.map.inside(x, y) else None
        if not existing:
            raise LobbyError("Pick a structure to upgrade.")
        card = CARDS[existing.card]
        if existing.level >= card["maxLevel"]:
            raise LobbyError(f"That {card['name']} is already at its highest level.")
        existing.level += 1
        existing.hp = existing.max_hp()
        return existing

    def demolish(self, x, y, pid):
        existing = self.at(x, y) if self.map.inside(x, y) else None
        if not existing:
            raise LobbyError("There's nothing built there.")
        if existing.owner not in (pid, None):
            raise LobbyError("You can only demolish your own structures.")
        del self.structures[(x, y)]
        return existing

    def disown(self, pid, heir):
        """pid left: their structures pass to `heir` (None if nobody's left)."""
        for structure in self.structures.values():
            if structure.owner == pid:
                structure.owner = heir

    def public(self):
        result = {}
        for cell, structure in self.structures.items():
            info = structure.public()
            card = CARDS[structure.card]
            if structure.kind in ("tower", "barracks"):
                info["damage"] = stat(card, "damage", structure.level) + self.boost(*cell, "forge")
            if structure.kind == "tower":
                info["range"] = stat(card, "range", structure.level) + self.boost(*cell, "watch")
            if structure.kind == "barracks":
                info["rally"] = list(self.rally(*cell) or ())
            result[key(*cell)] = info
        return result
