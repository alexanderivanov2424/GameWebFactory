"""Navigation: where colonists can stand and walk, distance maps and paths. No colonists here.

A cell is *standable* when it is inside the grid, doesn't block fluid (doors do, but are walkable),
and either the cell below blocks fluid or a ladder is at the cell or the cell below. Liquids and
gases are walkable. Moves from a standable cell (each costs 1 in the BFS):
    left/right to a standable cell;
    up/down along ladders (a ladder cell, or the cell above a ladder's top);
    a diagonal step up by 1 when the head-room cell above is open;
    walking off a ledge: into an open, non-standable side cell, then falling to the first
    standable cell below (at most MAX_FALL cells).
A start cell that isn't standable (mid-air) can only fall straight down.

    standable(world, x, y) -> bool
    walkable(world, i) -> bool       cell index is open (not blocking, doors count as open)
    neighbours(world, i) -> list of cell indexes reachable in one move
    distances(world, start_index, limit=None) -> (dist, parent)   dicts keyed by cell index
    path(world, parent, start_index, goal_index) -> list of 4-adjacent cell indexes after start
                                                    (diagonals and falls expanded), [] if
                                                    start is the goal, None if unreachable
"""

from collections import deque

MAX_FALL = 6


def walkable(world, i):
    return not world.blocks_fluid(i) or world.door[i]


def standable(world, x, y):
    if not world.inside(x, y):
        return False
    return _standable(world, world.idx(x, y), y)


def _standable(world, i, y):
    if world.blocks_fluid(i) and not world.door[i]:
        return False
    if world.ladder[i]:
        return True
    if y + 1 >= world.h:
        return False
    j = i + world.w
    return world.blocks_fluid(j) or world.ladder[j]


def _fall_target(world, i, y):
    """First standable cell straight below i (exclusive), within MAX_FALL, through open cells."""
    w = world.w
    for step in range(1, MAX_FALL + 1):
        if y + step >= world.h:
            return None
        k = i + step * w
        if not walkable(world, k):
            return None
        if _standable(world, k, y + step):
            return k
    return None


def neighbours(world, i):
    w = world.w
    x, y = i % w, i // w
    out = []
    if not _standable(world, i, y):
        k = _fall_target(world, i, y)
        return [k] if k is not None else []
    for dx in (-1, 1):
        nx = x + dx
        if not 0 <= nx < w:
            continue
        j = i + dx
        if not walkable(world, j):
            if y > 0:
                up = j - w
                if walkable(world, up) and walkable(world, i - w) and _standable(world, up, y - 1):
                    out.append(up)
            continue
        if _standable(world, j, y):
            out.append(j)
        else:
            k = _fall_target(world, j, y)
            if k is not None:
                out.append(k)
    if world.ladder[i] and y > 0:
        up = i - w
        if walkable(world, up) and _standable(world, up, y - 1):
            out.append(up)
    if y + 1 < world.h and (world.ladder[i] or world.ladder[i + w]):
        down = i + w
        if walkable(world, down) and _standable(world, down, y + 1):
            out.append(down)
    return out


def distances(world, start, limit=None):
    dist = {start: 0}
    parent = {start: None}
    queue = deque([start])
    while queue:
        i = queue.popleft()
        d = dist[i]
        if limit is not None and d >= limit:
            continue
        for j in neighbours(world, i):
            if j not in dist:
                dist[j] = d + 1
                parent[j] = i
                queue.append(j)
    return dist, parent


def _expand(world, a, b):
    w = world.w
    ax, ay, bx, by = a % w, a // w, b % w, b // w
    cells = []
    if ax != bx and by < ay:      # step up: head-room first, then sideways
        cells.append(a - w)
        cells.append(b)
    elif ax != bx and by > ay:    # walk off, then fall
        cells.append(ay * w + bx)
        for y in range(ay + 1, by + 1):
            cells.append(y * w + bx)
    elif ax == bx:
        step = 1 if by > ay else -1
        for y in range(ay + step, by + step, step):
            cells.append(y * w + bx)
    else:
        cells.append(b)
    return cells


def path(world, parent, start, goal):
    if goal == start:
        return []
    if goal not in parent:
        return None
    chain = []
    i = goal
    while i is not None and i != start:
        chain.append(i)
        i = parent[i]
    chain.reverse()
    out, prev = [], start
    for i in chain:
        out.extend(_expand(world, prev, i))
        prev = i
    return out
