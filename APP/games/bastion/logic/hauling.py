"""Bastion: hauling, a unit on the Hauling pool moving stored goods to the stockpile (pure rules).

When a hauling unit resolves, its player picks a source: a building with goods in its store that
is next to a depot or whose roads reach one (board.link). Up to the haul's capacity in goods
move from it to the stockpile at once, whatever the distance, biggest piles first (ties in
resource order). A haul carries SMALL goods; each round the first N haul resolutions carry BIG
instead, where N is the number of undamaged structures with "carriage" (the Carriage).
Match.hauled counts this round's resolutions.

    carriages(board) -> undamaged carriage structures
    capacity(board, hauled) -> what the next haul carries after `hauled` hauls this round
    queue(board, hauled, count) -> [capacity, ...] for the next `count` hauls
    sources(board) -> {uid: Structure} buildings a haul may take from now
    why_not(board, structure) -> why nothing can be hauled from it, or None
    best_source(board) -> the source with the most goods (lowest uid on a tie), or None
    take(structure, capacity) -> {good: n} removed from its store (biggest piles first)
"""

from .structures import GOODS

SMALL = 3  # goods per haul (tune)
BIG = 5  # goods per haul for the first N hauls a round, N = carriages (tune)


def carriages(board):
    return sum(1 for s in board.structures.values() if s.spec["carriage"] and not s.ruined)


def capacity(board, hauled):
    return BIG if hauled < carriages(board) else SMALL


def queue(board, hauled, count):
    return [capacity(board, hauled + i) for i in range(count)]


def why_not(board, s):
    if not s.stored():
        return f"That {s.spec['name']} has no goods waiting."
    if not board.link(s):
        return f"That {s.spec['name']} is cut off: link it to the keep or a storage yard by road."
    return None


def sources(board):
    reach = board.road_reach()
    return {uid: s for uid, s in sorted(board.structures.items()) if s.stored() and board.link(s, reach)}


def best_source(board):
    found = sources(board)
    return max(found.values(), key=lambda s: (s.stored(), -s.uid)) if found else None


def take(s, cap):
    taken = {}
    for good, n in sorted(s.store.items(), key=lambda kv: (-kv[1], GOODS.index(kv[0]))):
        moved = min(n, cap - sum(taken.values()))
        if moved <= 0:
            break
        taken[good] = moved
        s.store[good] -= moved
        if not s.store[good]:
            del s.store[good]
    return taken
