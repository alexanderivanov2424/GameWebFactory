"""Landmarks: one-of-a-kind ruins hidden under the snow (content: landmarks/*.json).

place(world, rng, size_name): picks which landmarks this valley gets (PER_MAP of them: a random
selection on smaller maps; every one on large and huge, with a second copy of those with max 2)
and lays each as a size x size square of "site" lots at a random spot whose distance from the
cabin is within its band (shares of half the map), apart from the cabin and the other sites.
Site lots hold SITE_SNOW x the normal snow and look like plain snow until reached. The client
only sees a landmark once one of its lots is reached (or every landmark after the Observatory).

When the last of its lots is reached (Match.found(pid, "site", i)), whoever cleared it gets the
reward (grant):
    unit:   a unique machine (machines/*.json "unique") joins the finder's crew at the site;
    placed: a unique placed machine (Ice Factory, Snow Cone Stand, Hot Spring) is built for the
            finder on the site's centre lot;
    team:   an effect for everyone (EFFECTS), stored in Match.effects:
            market       an Old Rail Station: a drop point for snow and a market for goods on the
                         site's centre lot (roads.Network sources);
            forecast     blizzard warnings come FORECAST_WARNING s ahead and blizzards last
                         FORECAST_SHORTER as long (survival.Weather);
            observatory  every landmark shows on the map, golden snowflakes come twice as often.
"""

import math

from . import units
from .content import LANDMARKS, MACHINES

PER_MAP = {"small": 6, "medium": 9, "large": 99, "huge": 99}
SECOND_COPY = {"large", "huge"}
SITE_SNOW = 1.5
SPACING = 8          # lots between landmarks (and from the cabin's start area)
TRIES = 300
EFFECTS = {"market", "forecast", "observatory"}
FORECAST_WARNING = 60
FORECAST_SHORTER = 0.7


def place(world, rng, size_name):
    ids = list(LANDMARKS)
    rng.shuffle(ids)
    ids = ids[:PER_MAP.get(size_name, 99)]
    if size_name in SECOND_COPY:
        ids += [lid for lid in ids if LANDMARKS[lid]["max"] >= 2]
    half = world.w / 2
    for lid in ids:
        lm = LANDMARKS[lid]
        n = lm["size"]
        for _ in range(TRIES):
            d = rng.uniform(*lm["band"]) * (half - n - 1)
            a = rng.uniform(0, 2 * math.pi)
            x0 = int(world.cx + d * math.cos(a)) - n // 2
            y0 = int(world.cy + d * math.sin(a)) - n // 2
            if _fits(world, x0, y0, n):
                _lay(world, lid, x0, y0, n)
                break


def _fits(world, x0, y0, n):
    if x0 < 1 or y0 < 1 or x0 + n >= world.w - 1 or y0 + n >= world.h - 1:
        return False
    cx, cy = x0 + n / 2, y0 + n / 2
    if math.hypot(cx - world.cx, cy - world.cy) < SPACING:
        return False
    return all(math.hypot(cx - s["x"] - s["size"] / 2, cy - s["y"] - s["size"] / 2) >= SPACING for s in world.sites)


def _lay(world, lid, x0, y0, n):
    number = len(world.sites)
    lots = [world.index(x, y) for y in range(y0, y0 + n) for x in range(x0, x0 + n)]
    world.sites.append({"id": lid, "x": x0, "y": y0, "size": n, "lots": lots, "left": len(lots), "found": None})
    for i in lots:
        world.kind[i] = "site"
        world.site[i] = number
        world.depth[i] = round(world.depth[i] * SITE_SNOW, 1)
        world.snow[i] = world.depth[i]


def centre(world, site):
    n = site["size"]
    return world.index(site["x"] + n // 2, site["y"] + n // 2)


def found(match, pid, i):
    """Lot i (a site lot) was just reached by pid or pid's unit: reward a fully cleared site."""
    world = match.world
    site = world.sites[world.site[i]]
    if site["left"] > 0 or site["found"] is not None:
        return
    p = match.players[pid]
    site["found"] = pid
    lm = LANDMARKS[site["id"]]
    reward = lm["reward"]
    middle = centre(world, site)
    x, y = world.xy(middle)
    if reward["kind"] == "team":
        match.effects.add(reward["effect"])
        if reward["effect"] == "market":
            match.markets.append(middle)
            match.roads.add_drop(middle, market=True)
        elif reward["effect"] == "forecast":
            match.weather.forecast()
    else:
        mid = reward["machine"]
        p.owned[mid] += 1
        if reward["kind"] == "placed":
            units.add(match, pid, mid, 1, x + 0.5, y + 0.5, home=middle)
        else:
            units.add(match, pid, mid, 1, x + 0.5, y + 0.5)
    what = MACHINES[reward["machine"]]["name"] if reward["kind"] != "team" else None
    match.say(f"{p.name} dug out the {lm['name']}! " + (f"The {what} is theirs. " if what else "") + lm["text"])


def public(match):
    """Landmarks the client may see: {"<n>": {"id", "x", "y", "size", "left", "total", "found"?}}."""
    world = match.world
    everything = "observatory" in match.effects
    out = {}
    for n, s in enumerate(world.sites):
        if everything or s["left"] < len(s["lots"]):
            entry = {"id": s["id"], "x": s["x"], "y": s["y"], "size": s["size"], "left": s["left"], "total": len(s["lots"])}
            if s["found"] is not None:
                entry["found"] = s["found"]
            out[str(n)] = entry
    return out
