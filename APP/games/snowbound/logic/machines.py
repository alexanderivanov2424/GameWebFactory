"""What each machine kind does, one function per kind: STEPS[kind](ctx, unit, player, rate).

rate = the machine's JSON rate x the owner's machine_mult upgrades x frenzy/blizzard.
Upgrades named here are flags (upgrades/*.json, effect kind "flag"); Player.has(id).

worker   (Neighbour Kid) digs the nearest workable lot near the rally point at rate.
         snow-angels: finishing a lot also clears the lots around it with ANGEL_SNOW or less.
dog      (Drift Dog) walks to the frontier, then tunnels in a straight line (cardinal direction
         away from where it came): digs the lot ahead at rate while it has at most params.limit snow,
         steps into it once clear and makes it road. Snow too deep ahead: turns left or right; if
         both are too deep it goes back to looking for a frontier lot. sled-harness: x2 rate, x3 limit.
sweeper  (Dust Sweeper) digs only lots a blizzard snowed over, or with at most params.shallow snow.
         ember-pack: every EMBER_LOTS lots it clears add a log to the woodpile.
brazier  (Brazier, placed) while the woodpile has logs: melts rate from every lot with snow within
         params.radius (any lot, frontier or not), paid; it is a heat source within
         survival.BRAZIER_HEAT; burns params.logs logs/s (survival.stove_burn). bellows: radius +1, half the logs.
buddy    (Shovel Buddy) follows its owner and digs workable lots within its reach at rate; while
         within params.near of you it boosts your shovel (Match.buddy_boost).
dozer    (Blade Dozer) digs the nearest frontier lot at rate, but only params.paid of it is paid
         (windrow-pay: all of it); the other part is shoved onto the next unreached lot further from
         the cabin (destroyed if there is none).
auger    (Deep Auger) drills the deepest workable lot with at least params.min snow within
         params.range of the rally point (or itself) at rate; with none there, the nearest deep
         workable lot anywhere. corkscrew: any lot in that range, not
         only workable ones (World.melt), so it opens new cleared ground out in the drifts.
still    (Snow Still, placed) digs the params.lots nearest workable lots within its reach,
         splitting rate between them; pays cash and fills the owner's tank with 1 L diesel per
         params.diesel_per snow. ration-kettle: also a ration per KETTLE_RATION snow and a log per
         KETTLE_LOG snow.
grader   (Road Grader) digs workable lots next to a road (any workable lot if there's no road),
         x params.road_mult while standing on a road; what it clears becomes road. wing-blade: the two
         lots beside its target get the same work (World.melt) and become road too.
jet      (Jet Blower) drives to the frontier near the rally point; every params.cooldown s it fires
         a beam straight away from the cabin: every lot within params.range loses up to rate snow
         (World.melt, paid) and becomes road. long-throw: double range, LONG_COOLDOWN s.
"""

import math

from .content import MACHINES
from .units import move_toward, work

ANGEL_SNOW = 20
EMBER_LOTS = 10
KETTLE_RATION = 3000
KETTLE_LOG = 2000
LONG_COOLDOWN = 12
BEAM_SHOW = 1.5  # seconds the client keeps drawing a beam
DIRS = ((1, 0), (0, 1), (-1, 0), (0, -1))


def _params(unit):
    return MACHINES[unit.mid]["params"]


def worker(ctx, unit, player, rate):
    world = ctx.world

    def angels(i, removed, cleared):
        if cleared and player.has("snow-angels"):
            for j in world.neighbours(i):
                if 0 < world.snow[j] <= ANGEL_SNOW and world.workable(j):
                    got, found = world.dig(j, ANGEL_SNOW)
                    player.earn(got)
                    if found:
                        ctx.match.found(player.id, found, j)

    work(ctx, unit, player, rate * ctx.dt, on_dig=angels)


def dog(ctx, unit, player, rate):
    world, p = ctx.world, _params(unit)
    limit = p.get("limit", 60) * (3 if player.has("sled-harness") else 1)
    if player.has("sled-harness"):
        rate *= 2
    if unit.lot is None:
        # Not tunnelling: go to a frontier lot that isn't too deep, then tunnel toward it.
        ok = lambda i: world.snow[i] <= limit  # noqa: E731
        if not ctx.valid(unit, ok):
            ctx.release(unit)
            ctx.claim(unit, ctx.pick(unit, 1.0, ok))
        if unit.target is None:
            unit.state = "idle"
            return
        tx, ty = world.xy(unit.target)
        here = world.index(math.floor(unit.x), math.floor(unit.y))
        # Stand on a reached lot next to the target, then face it.
        for dx, dy in DIRS:
            j = world.index(tx - dx, ty - dy)
            if j is not None and world.reached[j] and world.snow[j] <= 0:
                if here == j and math.hypot(unit.x - (tx - dx + 0.5), unit.y - (ty - dy + 0.5)) < 0.15:
                    unit.lot, unit.dir = j, (dx, dy)
                    ctx.release(unit)
                    return
                move_toward(world, unit, tx - dx + 0.5, ty - dy + 0.5, MACHINES[unit.mid]["speed"], ctx.dt)
                unit.state = "moving"
                return
        ctx.release(unit)
        unit.state = "idle"
        return
    x, y = world.xy(unit.lot)
    if math.hypot(unit.x - x - 0.5, unit.y - y - 0.5) > 0.05:
        move_toward(world, unit, x + 0.5, y + 0.5, MACHINES[unit.mid]["speed"], ctx.dt)
        unit.state = "moving"
        return
    dx, dy = unit.dir
    for ddx, ddy in [(dx, dy)] + ctx.match.rng.sample([(dy, dx), (-dy, -dx)], 2):
        ahead = world.index(x + ddx, y + ddy)
        if ahead is None:
            continue
        if world.reached[ahead] and world.snow[ahead] <= 0:
            if (ddx, ddy) != (dx, dy):
                continue  # don't turn into open ground; only follow a tunnel straight
            unit.lot = ahead
            return
        if world.snow[ahead] <= limit and world.workable(ahead) and ctx.claimed.get(ahead, unit.id) == unit.id:
            unit.dir = (ddx, ddy)
            unit.state = "working"
            removed, found = world.dig(ahead, rate * ctx.dt)
            player.earn(removed)
            if found:
                ctx.match.found(player.id, found, ahead)
            if world.snow[ahead] <= 0:
                world.make_road(ahead)
                unit.lot = ahead
            return
    unit.lot = unit.dir = None  # boxed in by deep snow: find a new frontier lot


def sweeper(ctx, unit, player, rate):
    world, p = ctx.world, _params(unit)
    shallow = p.get("shallow", 30)
    ok = lambda i: i in world.dusted or world.snow[i] <= shallow  # noqa: E731

    def embers(i, removed, cleared):
        if cleared and player.has("ember-pack"):
            unit.acc += 1
            if unit.acc >= EMBER_LOTS:
                unit.acc -= EMBER_LOTS
                ctx.match.woodpile += 1

    work(ctx, unit, player, rate * ctx.dt, ok=ok, on_dig=embers)


def brazier_radius(player):
    return 3 if player.has("bellows") else 2


def brazier(ctx, unit, player, rate):
    world, match = ctx.world, ctx.match
    if match.woodpile <= 0:
        unit.state = "unlit"
        return
    unit.state = "working"
    hx, hy = world.xy(unit.home)
    r = brazier_radius(player)
    for y in range(hy - r, hy + r + 1):
        for x in range(hx - r, hx + r + 1):
            i = world.index(x, y)
            if i is None or (x - hx) ** 2 + (y - hy) ** 2 > r * r + 0.5 or world.snow[i] <= 0 or world.kind[i] == "cabin":
                continue
            removed, found = world.melt(i, rate * ctx.dt)
            player.earn(removed)
            if found:
                match.found(player.id, found, i)


def buddy(ctx, unit, player, rate):
    world = ctx.world
    m = MACHINES[unit.mid]
    if math.hypot(player.x - unit.x, player.y - unit.y) > 1.2:
        move_toward(world, unit, player.x, player.y, max(m["speed"], 5.0), ctx.dt, 1.0)
        unit.state = "moving"
        return
    work(ctx, unit, player, rate * ctx.dt, local_only=True)


def dozer(ctx, unit, player, rate):
    world = ctx.world
    paid = 1.0 if player.has("windrow-pay") else _params(unit).get("paid", 0.4)

    def shove(i, removed, cleared):
        if not removed:
            return
        x, y = world.xy(i)
        dx, dy = x - world.cx, y - world.cy
        step = (1 if dx > 0 else -1, 0) if abs(dx) >= abs(dy) else (0, 1 if dy > 0 else -1)
        beyond = world.index(x + step[0], y + step[1])
        if beyond is not None and not world.reached[beyond]:
            world.add_snow(beyond, removed * (1 - paid))

    work(ctx, unit, player, rate * ctx.dt, on_dig=shove, pay=paid)


def auger(ctx, unit, player, rate):
    world, p = ctx.world, _params(unit)
    least, reach = p.get("min", 200), p.get("range", 15)
    rally = ctx.rallies.get(unit.pid)
    cx, cy = rally if rally is not None else (unit.x - 0.5, unit.y - 0.5)
    anywhere = player.has("corkscrew")
    i = unit.target
    if i is None or world.snow[i] < least or (not anywhere and not world.workable(i)) \
            or ctx.claimed.get(i, unit.id) != unit.id:
        ctx.release(unit)
        if ctx.searches <= 0:
            unit.state = "idle"
            return
        ctx.searches -= 1
        best, best_snow = None, 0
        if anywhere:
            r = int(reach)
            lots = (world.index(x, y) for y in range(int(cy) - r, int(cy) + r + 1)
                    for x in range(int(cx) - r, int(cx) + r + 1))
        else:
            lots = iter(world.targets)
        for j in lots:
            if j is None or j in ctx.claimed or world.snow[j] < least:
                continue
            x, y = world.xy(j)
            if (x - cx) ** 2 + (y - cy) ** 2 <= reach * reach and world.snow[j] > best_snow:
                best, best_snow = j, world.snow[j]
        if best is None:  # nothing deep near the rally point: the nearest deep frontier lot anywhere
            best = ctx.pick(unit, MACHINES[unit.mid]["reach"], ok=lambda j: world.snow[j] >= least)
        ctx.claim(unit, best)
        if best is None:
            unit.state = "idle"
            return
    tx, ty = world.xy(unit.target)
    if math.hypot(tx + 0.5 - unit.x, ty + 0.5 - unit.y) > MACHINES[unit.mid]["reach"]:
        move_toward(world, unit, tx + 0.5, ty + 0.5, MACHINES[unit.mid]["speed"], ctx.dt, 0.8)
        unit.state = "moving"
        return
    unit.state = "working"
    removed, found = world.melt(unit.target, rate * ctx.dt)
    player.earn(removed)
    if found:
        ctx.match.found(player.id, found, unit.target)


def still(ctx, unit, player, rate):
    world, match, p = ctx.world, ctx.match, _params(unit)
    reach = MACHINES[unit.mid]["reach"]
    hx, hy = world.xy(unit.home)
    lots = []
    r = int(reach) + 1
    for y in range(hy - r, hy + r + 1):
        for x in range(hx - r, hx + r + 1):
            i = world.index(x, y)
            if i is not None and world.workable(i) and (x - hx) ** 2 + (y - hy) ** 2 <= reach * reach:
                lots.append(((x - hx) ** 2 + (y - hy) ** 2, i))
    lots = [i for _, i in sorted(lots)[:int(p.get("lots", 3))]]
    if not lots:
        unit.state = "idle"
        return
    unit.state = "working"
    total = 0.0
    for i in lots:
        removed, found = world.dig(i, rate * ctx.dt / len(lots))
        total += removed
        if found:
            match.found(player.id, found, i)
    player.earn(total)
    player.diesel += total / p.get("diesel_per", 20)
    if player.has("ration-kettle"):
        unit.acc += total
        while unit.acc >= KETTLE_LOG:
            unit.acc -= KETTLE_LOG
            match.woodpile += 1
            if match.rng.random() < KETTLE_LOG / KETTLE_RATION:
                player.rations += 1


def grader(ctx, unit, player, rate):
    world = ctx.world
    near_road = (lambda i: any(world.road[j] for j in world.neighbours(i))) if world.road_count else None
    here = world.index(math.floor(unit.x), math.floor(unit.y))
    if here is not None and world.road[here]:
        rate *= _params(unit).get("road_mult", 2)
    wing = player.has("wing-blade")

    def pave(i, removed, cleared):
        if wing and removed:
            x, y = world.xy(i)
            dx, dy = x + 0.5 - unit.x, y + 0.5 - unit.y
            side = (0, 1) if abs(dx) >= abs(dy) else (1, 0)
            for sx, sy in (side, (-side[0], -side[1])):
                j = world.index(x + sx, y + sy)
                if j is not None and world.snow[j] > 0:
                    got, found = world.melt(j, removed)
                    player.earn(got)
                    if found:
                        ctx.match.found(player.id, found, j)
                    if world.snow[j] <= 0:
                        world.make_road(j)
        if cleared:
            world.make_road(i)

    work(ctx, unit, player, rate * ctx.dt, ok=near_road, on_dig=pave)


def jet(ctx, unit, player, rate):
    world, match, p = ctx.world, ctx.match, _params(unit)
    long_throw = player.has("long-throw")
    reach = p.get("range", 12) * (2 if long_throw else 1)
    cooldown = LONG_COOLDOWN if long_throw else p.get("cooldown", 20)
    unit.cd = max(0.0, unit.cd - ctx.dt)
    if not ctx.valid(unit):
        ctx.release(unit)
        ctx.claim(unit, ctx.pick(unit, MACHINES[unit.mid]["reach"]))
    if unit.target is None:
        unit.state = "idle"
        return
    tx, ty = world.xy(unit.target)
    if math.hypot(tx + 0.5 - unit.x, ty + 0.5 - unit.y) > MACHINES[unit.mid]["reach"]:
        move_toward(world, unit, tx + 0.5, ty + 0.5, MACHINES[unit.mid]["speed"], ctx.dt, 1.0)
        unit.state = "moving"
        return
    if unit.cd > 0:
        unit.state = "charging"
        return
    # Fire: straight away from the cabin, through the target.
    dx, dy = tx + 0.5 - (world.cx + 0.5), ty + 0.5 - (world.cy + 0.5)
    length = math.hypot(dx, dy) or 1
    dx, dy = dx / length, dy / length
    hit, total = [], 0.0
    for k in range(int(reach * 2) + 1):
        i = world.index(math.floor(unit.x + dx * k / 2), math.floor(unit.y + dy * k / 2))
        if i is None:
            break
        if i in hit:
            continue
        hit.append(i)
        removed, found = world.melt(i, rate)
        total += removed
        if found:
            match.found(player.id, found, i)
        if world.snow[i] <= 0 and world.kind[i] != "cabin":
            world.make_road(i)
    player.earn(total)
    unit.cd = cooldown
    unit.state = "charging"
    ctx.release(unit)
    match.beam(unit.x, unit.y, unit.x + dx * reach, unit.y + dy * reach, player.color)


STEPS = {"worker": worker, "dog": dog, "sweeper": sweeper, "brazier": brazier, "buddy": buddy,
         "dozer": dozer, "auger": auger, "still": still, "grader": grader, "jet": jet}
