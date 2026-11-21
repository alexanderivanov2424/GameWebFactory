"""Player characters: walking with collision, and shoveling the lot you aim at.

World coordinates are in lots; lot (x, y) covers [x, x + 1) x [y, y + 1). A character is a circle
of RADIUS at (p.x, p.y). It can stand on lots that World.passable() allows (reached, or snow
shallow enough to wade), so deep snow is a wall you dig through. Movement tries x then y
separately, so you slide along walls. client/grid.js mirrors blocked() and move() exactly, for
prediction: keep them in sync.

Speed: WALK_SPEED lots/s, x DUSTED_SLOW on a reached lot with snow on it, x FROSTBITE_SLOW with
frostbite, x STARVING_SLOW while starving.
Shoveling: a swing digs Player.click_power() from a workable lot whose centre is within REACH
of you. Swings come from clicks (actions) and from holding the dig button (input "dig"), at most
SWING_RATE a second while held; both use the click budget (economy.CLICKS_PER_SECOND).
"""

import math

RADIUS = 0.3
WALK_SPEED = 4.0
DUSTED_SLOW = 0.6
FROSTBITE_SLOW = 0.4
STARVING_SLOW = 0.7
REACH = 2.2
SWING_RATE = 6
KEYS = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}


def blocked(world, x, y):
    """Would a character centred at (x, y) overlap a lot it can't stand on (or leave the map)?"""
    for cx in (x - RADIUS, x + RADIUS):
        for cy in (y - RADIUS, y + RADIUS):
            i = world.index(math.floor(cx), math.floor(cy))
            if i is None or not world.passable(i):
                return True
    return False


def move(world, x, y, dx, dy):
    """Move by (dx, dy), sliding along walls; a blocked step is retried at 1/2 and 1/4 so you
    get right up to a wall. Returns the new (x, y)."""
    for part in (1, 0.5, 0.25):
        if dx and not blocked(world, x + dx * part, y):
            x += dx * part
            break
    for part in (1, 0.5, 0.25):
        if dy and not blocked(world, x, y + dy * part):
            y += dy * part
            break
    return x, y


def speed(world, p):
    i = world.index(math.floor(p.x), math.floor(p.y))
    s = WALK_SPEED
    if i is not None and world.snow[i] > 0 and world.reached[i]:
        s *= DUSTED_SLOW
    if p.frostbite:
        s *= FROSTBITE_SLOW
    if p.starving:
        s *= STARVING_SLOW
    return s


def walk(world, p, dt):
    dx = sum(KEYS[k][0] for k in p.keys)
    dy = sum(KEYS[k][1] for k in p.keys)
    if not dx and not dy:
        return
    length = math.hypot(dx, dy)
    step = speed(world, p) * dt / length
    p.x, p.y = move(world, p.x, p.y, dx * step, dy * step)


def in_reach(p, x, y):
    return math.hypot(x + 0.5 - p.x, y + 0.5 - p.y) <= REACH


def step(match, dt):
    """Walk everyone and run held-down shoveling."""
    for p in match.players.values():
        walk(match.world, p, dt)
        p.swing_cd = max(0.0, p.swing_cd - dt)
        p.swinging = max(0.0, p.swinging - dt)
        if p.dig and p.aim is not None and p.swing_cd <= 0:
            if match.swing(p.id, *p.aim):
                p.swing_cd = 1 / SWING_RATE
