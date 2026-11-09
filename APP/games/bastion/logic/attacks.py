"""Bastion: what an enemy's attack does to the city (enemies.py documents the attack fields).

    strike(match, foe, attack) -> [text, ...]   applies every part of the attack and says what
                                                happened (for the log); randomness from match.rng
Raids (ruin) only hit unprotected building tiles (board.raid_targets); when none are open they
break a wall tile instead, and do nothing if there are no walls. A building whose every tile is
ruined is destroyed. Looting takes goods from carriages on road tiles that aren't protected
(next to a wall or within a watchtower's reach), one at a time from a random carriage; an emptied
carriage turns back and its card returns to its owner. Blights go on empty grass next to a building when there is any.
"""

from . import carriages
from .structures import GOODS, a


def steal(match, amounts):
    taken = {}
    for key, n in amounts.items():
        if key == "most":
            key = max(GOODS, key=lambda g: (match.stock[g], -GOODS.index(g)))
        got = min(n, match.stock[key])
        if got:
            match.stock[key] -= got
            taken[key] = taken.get(key, 0) + got
    return taken


def loot(match, count):
    board, taken = match.board, {}
    for _ in range(count):
        open_ = [c for _, c in sorted(board.carriages.items()) if c.cell and not board.protected(c.cell)]
        if not open_:
            break
        carriage = match.rng.choice(open_)
        good = match.rng.choice(sorted(carriage.goods))
        carriage.goods[good] -= 1
        if not carriage.goods[good]:
            del carriage.goods[good]
        if not carriage.goods:
            carriages.return_card(match, carriage)
        board.version += 1
        taken[good] = taken.get(good, 0) + 1
    return taken


def ruin(match, count, prefer):
    board, hits = match.board, []
    for _ in range(count):
        targets = board.raid_targets(prefer)
        if not targets:
            targets = sorted(board.walls)
            if not targets:
                break
            cell = match.rng.choice(targets)
            board.ruin(cell)
            hits.append("a wall")
            continue
        cell = match.rng.choice(targets)
        name = board.structures[board.at[cell]].spec["name"]
        destroyed = board.ruin(cell)
        hits.append(f"the {name} (destroyed)" if destroyed else f"{a(name)} tile")
    return hits


def blight_spots(board):
    near_buildings = {c for s in board.structures.values() for c in board.neighbors(s.cells) if board.empty(c)}
    return sorted(near_buildings) or [(x, y) for y in range(board.height) for x in range(board.width)
                                      if board.empty((x, y))]


def strike(match, foe, attack):
    board, rng, out = match.board, match.rng, []
    if "steal" in attack:
        taken = steal(match, attack["steal"])
        out.append("stole " + (", ".join(f"{n} {k}" for k, n in taken.items()) if taken else "nothing"))
    if "loot" in attack:
        taken = loot(match, attack["loot"])
        out.append("looted " + (", ".join(f"{n} {k}" for k, n in taken.items()) + " from carriages" if taken
                                else "nothing (no unprotected carriages on the roads)"))
    if "ruin" in attack:
        hits = ruin(match, attack["ruin"], attack["prefer"])
        out.append("ruined " + (", ".join(hits) if hits else "nothing (all protected, no walls to break)"))
    if "keep" in attack:
        damage = attack["keep"]
        if attack.get("shield"):
            keep = next(s for s in board.structures.values() if s.kind == "keep")
            damage = max(0, damage - board.near(keep.cells, "wall"))
        match.keep = max(0, match.keep - damage)
        out.append(f"hit the keep for {damage}")
    if "place" in attack:
        placed = 0
        for _ in range(attack["count"]):
            spots = blight_spots(board)
            if spots:
                board.add_blight(rng.choice(spots), attack["place"]["name"], attack["place"]["icon"], foe.index)
                placed += 1
        out.append(f"placed {placed} {attack['place']['name']}{'s' if placed != 1 else ''}")
    if "curse" in attack:
        seats = list(match.seats.values())
        if attack["to"] == "one" and seats:
            seats = [rng.choice(seats)]
        for seat in seats:
            seat.deck.add(attack["curse"])["from"] = foe.index
        out.append("cursed " + (", ".join(s.name for s in seats) or "nobody"))
    for key, verb in (("plague", "plagued"), ("freeze", "froze")):
        if key in attack:
            healthy = [s for s in board.structures.values() if s.spec["work"] and s.plague is None
                       and (key == "plague" or s.frozen <= match.round)]
            hit = rng.sample(healthy, min(attack[key], len(healthy)))
            for s in hit:
                if key == "plague":
                    s.plague = foe.index
                else:
                    s.frozen = match.round + 1
            board.version += 1
            out.append(f"{verb} " + (", ".join(a(s.spec["name"]) for s in hit) or "nothing"))
    if "kill" in attack:
        killed = min(attack["kill"], match.soldiers)
        match.soldiers -= killed
        out.append(f"killed {killed} soldier{'s' if killed != 1 else ''}")
    return out or ["rested"]
