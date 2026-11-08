"""Map generation: generate(w, h, rng) -> (World, (pod_x, pod_y)), deterministic from rng.

Bedrock border, rock by depth band (sandstone on top, granite below) with ore/soil blobs from
random walks, gas caves, water pools, an ice pocket and a cleared start room in the centre with
a sandstone floor. The pod position is the top-left of the 3x3 pod standing on that floor.
Resources the start needs (algae, copper ore, sand, dirt, a small water pool) are placed near it.
"""

from .content import ELEMENTS
from .grid import World

ROOM_W, ROOM_H = 14, 6


NEAR = 12  # guaranteed start resources lie within this many cells (Chebyshev) of the room


def _stamp_start(world, put, rng, cx, cy):
    """Stamp guaranteed start resources and two sealed air caves around the room (after random blobs)."""
    w, h = world.w, world.h
    keep = (cx - 1, cy - 1, cx + ROOM_W, cy + ROOM_H + 1)  # room, walls and floor row: never touched
    taken = []

    def fits(x0, y0, bw, bh):
        if x0 < 2 or y0 < 2 or x0 + bw > w - 2 or y0 + bh > h - 2:
            return False
        if x0 < cx - NEAR or x0 + bw - 1 > cx + ROOM_W - 1 + NEAR:
            return False
        if y0 < cy - NEAR or y0 + bh - 1 > cy + ROOM_H - 1 + NEAR:
            return False
        for (a, b, c, d) in [keep] + taken:
            if x0 <= c and x0 + bw - 1 >= a and y0 <= d and y0 + bh - 1 >= b:
                return False
        return True

    def spot(bw, bh):
        for _ in range(300):
            x0 = rng.randint(cx - NEAR, cx + ROOM_W + NEAR)
            y0 = rng.randint(cy - NEAR, cy + ROOM_H + NEAR)
            if fits(x0, y0, bw, bh):
                break
        else:
            cands = [(x, y) for y in range(2, h - 2) for x in range(2, w - 2) if fits(x, y, bw, bh)]
            if not cands:
                return None
            x0, y0 = cands[rng.randrange(len(cands))]
        taken.append((x0, y0, x0 + bw - 1, y0 + bh - 1))
        return x0, y0

    def fill(x0, y0, bw, bh, el):
        for y in range(y0, y0 + bh):
            for x in range(x0, x0 + bw):
                put(y * w + x, el)

    # sealed oxygen caves just outside the room's side walls (a 1-cell wall between)
    for side in (-1, 1):
        x0 = cx - 1 - 4 if side < 0 else cx + ROOM_W + 1
        y0 = cy + rng.randint(0, 2)
        fill(x0 - 1, y0 - 1, 6, 5, "granite")
        fill(x0, y0, 4, 3, "oxygen")
        taken.append((x0 - 1, y0 - 1, x0 + 4, y0 + 3))
        wx = cx - 1 if side < 0 else cx + ROOM_W
        fill(wx, y0 - 1, 1, 5, "sandstone")
    # compact 3x3 patches of rock-embedded resources
    for el in ("algae", "copper_ore", "sand", "dirt"):
        sp = spot(3, 3)
        if sp:
            fill(sp[0], sp[1], 3, 3, el)
    # water pool: 3x2 water inside a solid rock shell so it stays put
    sp = spot(5, 4)
    if sp:
        fill(sp[0], sp[1], 5, 4, "granite")
        fill(sp[0] + 1, sp[1] + 1, 3, 2, "water")


def generate(w, h, rng):
    world = World(w, h, "granite")

    def temp_at(y):
        return 16 + 10 * y / h + rng.uniform(-1.5, 1.5)

    def put(i, el, mass=None, temp=None):
        d = ELEMENTS[el]
        m = d["defaultMass"] if mass is None else mass
        world.set_cell(i, el, m, temp_at(i // w) if temp is None else temp, d["germs"] * m)

    def clamp(x, y):
        return max(1, min(w - 2, x)), max(1, min(h - 2, y))

    def blob(el, cx, cy, size, replace_only_solid=True):
        x, y = clamp(cx, cy)
        for _ in range(size):
            i = y * w + x
            if world.is_solid(i) and world.element_id(i) != "bedrock":
                put(i, el)
            dx, dy = rng.choice(((1, 0), (-1, 0), (0, 1), (0, -1)))
            x, y = clamp(x + dx, y + dy)

    def cave(cx, cy, size, el):
        x, y = clamp(cx, cy)
        for _ in range(size):
            put(y * w + x, el, temp=temp_at(y))
            dx, dy = rng.choice(((1, 0), (-1, 0), (1, 0), (-1, 0), (0, 1), (0, -1)))
            x, y = clamp(x + dx, y + dy)

    def pool(cx, cy, pw, el):
        cx = max(2, min(w - pw - 2, cx))
        cy = max(2, min(h - 5, cy))
        for dx in range(pw):
            put((cy) * w + cx + dx, "oxygen", temp=temp_at(cy))
            put((cy + 1) * w + cx + dx, el, temp=temp_at(cy))
            put((cy + 2) * w + cx + dx, el, temp=temp_at(cy))

    for y in range(1, h - 1):
        for x in range(1, w - 1):
            put(y * w + x, "sandstone" if y < h / 3 else "granite")
    for x in range(w):
        for y in (0, h - 1):
            put(y * w + x, "bedrock", temp=20)
    for y in range(h):
        for x in (0, w - 1):
            put(y * w + x, "bedrock", temp=20)

    area = w * h
    for _ in range(max(3, area // 400)):
        blob("dirt", rng.randrange(w), rng.randrange(1, max(2, h // 3)), rng.randint(15, 35))
    for _ in range(max(3, area // 450)):
        blob("algae", rng.randrange(w), rng.randrange(h // 3, 2 * h // 3), rng.randint(10, 25))
        blob("sand", rng.randrange(w), rng.randrange(h // 3, 2 * h // 3), rng.randint(15, 30))
    for _ in range(max(3, area // 450)):
        blob("coal", rng.randrange(w), rng.randrange(2 * h // 3, h), rng.randint(10, 25))
        blob("copper_ore", rng.randrange(w), rng.randrange(2 * h // 3, h), rng.randint(10, 25))

    for _ in range(max(4, area // 300)):
        roll = rng.random()
        el = "oxygen" if roll < 0.65 else "carbon_dioxide" if roll < 0.85 else "polluted_oxygen"
        cave(rng.randrange(w), rng.randrange(2, h - 2), rng.randint(12, 40), el)

    cx, cy = w // 2 - ROOM_W // 2, h // 2 - ROOM_H // 2
    pool(rng.randrange(2, w - 10), rng.randrange(h // 3, h - 5), rng.randint(5, 8), "water")
    pool(rng.randrange(2, w - 10), rng.randrange(h // 3, h - 5), rng.randint(4, 6), "polluted_water")
    pool(cx + ROOM_W // 2 - 2, cy + ROOM_H + 5, 5, "water")  # small start pool
    blob("ice", rng.randrange(5, w - 5), rng.randrange(h // 2, h - 3), 8)
    # the ice pocket is cold
    for i in range(world.n):
        if world.element_id(i) == "ice":
            world.temp[i] = -10.0
    # resources near the start
    blob("algae", cx - 5, cy + 4, 14)
    blob("copper_ore", cx + ROOM_W + 3, cy + 3, 14)
    blob("sand", cx + 2, cy + ROOM_H + 9, 14)
    blob("dirt", cx + 4, cy - 4, 14)

    for y in range(cy, cy + ROOM_H):
        for x in range(cx, cx + ROOM_W):
            world.set_cell(y * w + x, "oxygen", 1.8, 22.0)
    _stamp_start(world, put, rng, cx, cy)
    for x in range(cx, cx + ROOM_W):
        world.set_cell((cy + ROOM_H) * w + x, "sandstone", ELEMENTS["sandstone"]["defaultMass"], 22.0)
    return world, (cx + 5, cy + ROOM_H - 3)
