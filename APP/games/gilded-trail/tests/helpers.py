"""Gilded Trail: shared test helpers (not a test file: run_tests.py only collects test_*.py).

Tests build exact positions on a real Match instead of playing games:

    helpers = importlib.import_module("games.gilded-trail.tests.helpers")
    m = helpers.new_match()                  # 2 players, serpent map, rng seed 1
    pid = helpers.cur(m)                     # whose turn it is
    a, b = helpers.hand(m, pid, "porter", "trader")   # hand = exactly these cards -> their uids (101, 102, ...)
    helpers.lane(m, "porter")                # nothing; see below

The test row: hexes "-2,0" .. "3,0" are in tile 0 and "4,0" .. "6,0" in tile 1 (blockade 0
sits between "3,0" and "4,0"). lane(m, ...) overwrites them so a position is exact:
    lane(m, ["machete", 1], ["machete", 1], ...)  # spaces "0,0", "1,0", ... as (terrain, value)
    put(m, pid, ei, "0,0")                         # explorer ei of pid stands there
    set_hex(m, "3,0", "rubble", 2)                 # change one hex
    set_blockade(m, 0, "machete", 1)               # blockade 0 (tile 0 | tile 1)
Every other explorer is parked on its start space; set_hex/lane never touch those.
"""

import random

import importlib

content = importlib.import_module("games.gilded-trail.logic.content")
match_module = importlib.import_module("games.gilded-trail.logic.match")
Match = match_module.Match
CARDS = content.CARDS
MAPS = content.MAPS


def new_match(players=2, **settings):
    names = {f"p{i + 1}": f"Player{i + 1}" for i in range(players)}
    return Match(names, {"map": "serpent", **settings}, rng=random.Random(1))


def cur(m):
    return m.turn()


def other(m, pid=None):
    pid = pid or cur(m)
    return next(p for p in m.seats if p != pid)


def hand(m, pid, *card_ids):
    """Replace pid's hand with these cards; uids 101, 102, ... Returns the uids."""
    m.players[pid]["hand"] = [{"uid": 101 + i, "card": c} for i, c in enumerate(card_ids)]
    return [101 + i for i in range(len(card_ids))]


def set_hex(m, key, terrain, value=1):
    m.board.hexes[key].update({"t": terrain, "v": value})
    m.board.hexes[key].pop("goal", None)


def goal(m, key):
    m.board.hexes[key].update({"t": "machete", "v": 1, "goal": True})


def lane(m, *spaces):
    """Spaces "0,0", "1,0", ... become (terrain, value) pairs; "-2,0" and "-1,0" become 1-value machete."""
    for key in ("-2,0", "-1,0"):
        set_hex(m, key, "machete", 1)
    for i, (terrain, value) in enumerate(spaces):
        set_hex(m, f"{i},0", terrain, value)


def set_blockade(m, index, terrain, value):
    m.board.blockades[index].update({"t": terrain, "v": value})


def put(m, pid, ei, key):
    m.players[pid]["explorers"][ei] = key


def discard_uids(m, pid):
    return [c["uid"] for c in m.players[pid]["deck"].discard_pile]


def discard_cards(m, pid):
    return sorted(c["card"] for c in m.players[pid]["deck"].discard_pile)


def removed_cards(m, pid):
    return sorted(c["card"] for c in m.players[pid]["removed"])


def fill_market(m, *card_ids):
    """Market slots become exactly these cards (padded with empty slots to 6)."""
    m.market.slots = list(card_ids) + [""] * (6 - len(card_ids))
