"""Map generation (STUB: to be implemented).

    generate(w, h, rng) -> (World, (pod_x, pod_y))
"""

from .grid import World


def generate(w, h, rng):
    world = World(w, h, "sandstone")
    cx, cy = w // 2 - 6, h // 2 - 3
    for y in range(cy, cy + 5):
        for x in range(cx, cx + 12):
            world.set_cell(world.idx(x, y), "oxygen", 1.8, 22)
    return world, (cx + 4, cy + 2)
