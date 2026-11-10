"""Hex Realms test fixtures: a blank all-grass map with hand-placed structures and units."""

import importlib
import random

GAME = "hex-realms"
match_mod = importlib.import_module(f"games.{GAME}.logic.match")
Match = match_mod.Match


class FixedDice(random.Random):
    """Every die shows `face` (6 = every die hits, 1 = none do)."""

    def __init__(self, face=6):
        super().__init__(1)
        self.face = face

    def randint(self, a, b):
        return self.face


def blank(players=2, face=6, **settings):
    """A match whose map is all grass with nothing on it; place things with hall()/unit()."""
    names = {f"p{i + 1}": f"Player {i + 1}" for i in range(players)}
    m = Match(names, {"turns": 40, "mapSize": "normal", "seed": 1, **settings}, rng=FixedDice(face))
    for k in m.cells:
        m.cells[k] = "grass"
    for sid in list(m.structures):
        m.remove_structure(sid)
    for uid in list(m.units):
        m.remove_unit(uid)
    m.refresh()
    return m


def hall(m, pid, at="0,0"):
    s = m.add_structure(pid, "town_hall", at, 0)
    m.refresh()
    return s["id"]


def unit(m, pid, utype, at):
    return m.add_unit(pid, utype, at)


def rich(m, pid, n=99):
    for r in m.players[pid]["res"]:
        m.players[pid]["res"][r] = n
