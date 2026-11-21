"""Hex Realms: the random hex map, generated from a seed (Voronoi terrain patches, fair starts).

    generate(radius, players, seed) -> (cells, starts)
    cells    {key: terrain id} over the hexagon of `radius`
    starts   one anchor key per player (their first Town Hall)
"""

import random

from gamekit.hexes import dist, disk, neighbors, parse, ring

from .content import TERRAIN

WEIGHTS = {"plains": 7, "forest": 3, "hills": 2, "mountain": 1, "desert": 1, "water": 1.6}
START_RING2 = ["forest", "forest", "plains", "hills", "plains", "plains", "forest", "plains", "hills", "plains", "plains", "plains"]


def pick(rng, weights):
    x = rng.random() * sum(weights.values())
    for k, w in weights.items():
        x -= w
        if x <= 0:
            return k
    return k


def generate(radius, players, seed):
    for attempt in range(40):
        rng = random.Random(f"{seed}/{attempt}")
        cells, starts = _attempt(rng, radius, players)
        if _connected(cells, starts):
            return cells, starts
    return cells, starts  # practically never: 40 unlucky maps in a row


def _attempt(rng, radius, players):
    keys = disk(radius)
    points = [(k, pick(rng, WEIGHTS)) for k in rng.sample(keys, max(6, len(keys) // 7))]
    cells = {k: min(points, key=lambda p: (dist(k, p[0]), p[0]))[1] for k in keys}
    around = ring(max(2, radius - 3))
    offset = rng.randrange(len(around))
    starts = [around[(offset + i * len(around) // players) % len(around)] for i in range(players)]
    for s in starts:
        q, r = parse(s)
        for k in ring(1, (q, r)) + [s]:
            if k in cells:
                cells[k] = "plains"
        for k, t in zip(ring(2, (q, r)), START_RING2):
            if k in cells:
                cells[k] = t
    return cells, starts


def _connected(cells, starts):
    seen, todo = {starts[0]}, [starts[0]]
    while todo:
        for n in neighbors(todo.pop()):
            if n in cells and n not in seen and TERRAIN[cells[n]]["move"] is not None:
                seen.add(n)
                todo.append(n)
    return all(s in seen for s in starts)
