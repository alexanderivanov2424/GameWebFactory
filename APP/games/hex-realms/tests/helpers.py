"""Hex Realms test fixtures: a blank all-plains map with hand-placed structures and units."""

import importlib
import random
from unittest import mock

from gamekit.hexes import disk

GAME = "hex-realms"
match_mod = importlib.import_module(f"games.{GAME}.logic.match")
Match = match_mod.Match
logistics = importlib.import_module(f"games.{GAME}.logic.logistics")
content = importlib.import_module(f"games.{GAME}.logic.content")


class FixedDice(random.Random):
    """Every die shows `face` (6 = every die hits, 1 = none do)."""

    def __init__(self, face=6):
        super().__init__(1)
        self.face = face

    def randint(self, a, b):
        return self.face


def blank(players=2, face=6, radius=10, fog="off", **settings):
    """A match whose map is all plains (a hexagon of `radius`) with nothing on it; place things with
    hall()/unit(). Fog is off unless asked for (then call m.refresh() after placing things)."""
    names = {f"p{i + 1}": f"Player {i + 1}" for i in range(players)}
    m = Match(names, {"turns": 40, "mapSize": "normal", "seed": 1, "fog": fog, **settings}, rng=FixedDice(face))
    m.cells = {k: "plains" for k in disk(radius)}
    m.radius = radius
    for sid in list(m.structures):
        m.remove_structure(sid)
    for uid in list(m.units):
        m.remove_unit(uid)
    m.refresh()
    return m


def hall(m, pid, at="0,0"):
    """A Town Hall (cells at, at+(1,0), at+(0,1)) holding the starting goods."""
    s = m.add_structure(pid, "town_hall", at, 0)
    s["stock"] = dict(match_mod.START_GOODS)
    m.refresh()
    return s["id"]


def well_fed(test, food=99):
    """For one test: every Town Hall makes `food` food a turn, so units and people never starve (eating
    uses this turn's production only) in tests about something else."""
    hall_def = content.STRUCTURES["town_hall"]
    patch = mock.patch.dict(hall_def, {"produce": {**hall_def["produce"], "food": food}})
    patch.start()
    test.addCleanup(patch.stop)


def unit(m, pid, utype, at):
    return m.add_unit(pid, utype, at)


def stock(m, pid):
    """What pid can spend: logistics.stock."""
    return logistics.stock(m, pid)


def rich(m, pid, n=99):
    """n of everything: gold/faith/science in the realm, goods in pid's first Town Hall (over its cap)."""
    for r in m.players[pid]["res"]:
        m.players[pid]["res"][r] = n
    hall_of(m, pid)["stock"] = {r: n for r in ("food", "wood", "stone", "metal")}


def hall_of(m, pid):
    return next(s for s in sorted(m.structures.values(), key=lambda s: s["n"]) if s["owner"] == pid and s["type"] == "town_hall")
