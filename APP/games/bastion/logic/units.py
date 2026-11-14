"""Bastion: units (worker placement). Each player has workers (seat.units: 1 from the keep, 2 per
built house) and soldiers (seat.soldiers: workers trained at a barracks, split from the workers
for good). One unit per tile, whoever owns it.

Where units stand: match.assigned = {(x, y): {"pid", "soldier": bool, "new": bool}}. "new" units
were placed in this place phase and may be taken back until everyone is ready; the others are
stationed on a building from earlier rounds and stay there (Orders sends one back to the pool).

What a unit placed on a tile does (job()):
    your planned structure      "build": removes one build token, then back to the pool
    your built building         "work" (its work: automatic, or a prompt to convert / pick one),
                                "train" (barracks: becomes a soldier), "idle" (house: nothing yet)
                                or "guard" (tower: soldiers only, does nothing yet); stays there
    empty grass                 "tile": at resolution, build a road there or scavenge (prompt);
                                then back to the pool
    forest / mountain           "gather": 1 wood / 1 stone, then back to the pool
Only tiles within REACH of your built buildings and roads (board.reach), never another player's
structure, a road, water, the keep (staff "none") or a taken tile.

    REACH                        3
    free(match, pid) / free_soldiers(match, pid)   unplaced workers / soldiers
    job(match, pid, cell) -> {"job", "soldier", "text"} or LobbyError why not (ignores whether a
                                 free unit is left); job_here: the same for a unit already there
    targets(match, pid)          {(x, y): job} every tile pid may place on now
    place(match, pid, x, y) / unplace(match, pid, x, y)   place phase only
    stationed(match, pid, cell)  pid's unit stationed there (Orders' target), else None
    release(match, cell)         take the unit off that tile (back to its pool)
    lose(match, pid)             a leaving player's units leave the board
    starve(match, seat, n)       n of the seat's units are lost: soldiers first, then unplaced
                                 workers, then stationed workers (latest tile first), so the
                                 last one left is a worker
"""

from gamekit import LobbyError

from .cards import amount_text
from .structures import GATHER, a

REACH = 3


def placed(match, pid, soldier):
    return sum(1 for u in match.assigned.values() if u["pid"] == pid and u["soldier"] == soldier)


def free(match, pid):
    return match.seats[pid].units - placed(match, pid, False)


def free_soldiers(match, pid):
    return match.seats[pid].soldiers - placed(match, pid, True)


def job(match, pid, cell, placing=True):
    board = match.board
    if not board.inside(*cell):
        raise LobbyError("That's off the board.")
    if placing and cell in match.assigned:
        raise LobbyError("There's already a unit on that tile.")
    if placing and cell not in board.reach(pid, REACH):
        raise LobbyError(f"Units only go within {REACH} tiles of your buildings and roads.")
    uid = board.at.get(cell)
    if uid is not None:
        s = board.structures[uid]
        spec = s.spec
        if s.owner != pid:
            raise LobbyError("That's another player's building.")
        if not s.built:
            left = f"{s.tokens} build token{'s' if s.tokens != 1 else ''} left"
            return {"job": "build", "soldier": False, "text": f"Build the {spec['name']} ({left})"}
        if spec["staff"] == "none":
            raise LobbyError(f"Units have nothing to do at {a(spec['name'])}.")
        if spec["staff"] == "soldier":
            return {"job": "guard", "soldier": True, "text": f"A soldier guards the {spec['name']} (does nothing yet)"}
        if spec["trains"]:
            return {"job": "train", "soldier": False, "text": "Becomes a soldier for good"}
        if spec["work"]:
            return {"job": "work", "soldier": False, "text": work_text(spec["work"])}
        return {"job": "idle", "soldier": False, "text": f"Stays at the {spec['name']} (does nothing yet)"}
    if cell in board.roads:
        raise LobbyError("Nothing to do on a road.")
    terrain = board.terrain_at(cell)
    if terrain in GATHER:
        return {"job": "gather", "soldier": False, "text": f"Gather 1 {GATHER[terrain]}"}
    if board.empty(cell):
        return {"job": "tile", "soldier": False, "text": "Build a road or scavenge (you pick at resolution)"}
    raise LobbyError("Units can't go there.")


def job_here(match, pid, cell):
    """What the unit already on that tile does (resolution: no reach or occupancy checks)."""
    return job(match, pid, cell, placing=False)


def work_text(work):
    if "choices" in work:
        return "Pick one: " + " or ".join(option_text(o) for o in work["choices"])
    return option_text(work) if not work["uses"] else f"You may {option_text(work)}"


def option_text(option):
    if option["uses"]:
        return f"turn {amount_text(option['uses'])} into {amount_text(option['makes'])}"
    return f"make {amount_text(option['makes'])}"


def targets(match, pid):
    out = {}
    board = match.board
    for cell in sorted(board.reach(pid, REACH)):
        try:
            out[cell] = job(match, pid, cell)
        except LobbyError:
            pass
    return out


def place(match, pid, x, y):
    match.placing(pid)
    what = job(match, pid, (x, y))
    if what["soldier"]:
        if free_soldiers(match, pid) <= 0:
            raise LobbyError("You have no soldiers left to place.")
    elif free(match, pid) <= 0:
        raise LobbyError("You have no units left to place.")
    match.assigned[(x, y)] = {"pid": pid, "soldier": what["soldier"], "new": True}


def unplace(match, pid, x, y):
    match.placing(pid)
    unit = match.assigned.get((x, y))
    if not unit or unit["pid"] != pid:
        raise LobbyError("You have no unit there.")
    if not unit["new"]:
        raise LobbyError("That unit is stationed there: only Orders can send it back.")
    del match.assigned[(x, y)]


def stationed(match, pid, cell):
    unit = match.assigned.get(cell)
    if unit and unit["pid"] == pid and not unit["new"] and not unit["soldier"] and cell in match.board.at:
        return unit
    return None


def release(match, cell):
    match.assigned.pop(cell, None)


def lose(match, pid):
    for cell in [c for c, u in match.assigned.items() if u["pid"] == pid]:
        del match.assigned[cell]


def starve(match, seat, n):
    """Lose n units (workers or soldiers). Returns how many were lost."""
    lost = 0
    while lost < n:
        if free_soldiers(match, seat.pid) > 0:
            seat.soldiers -= 1
        elif free(match, seat.pid) > 0:
            seat.units -= 1
        else:
            mine = sorted((c for c, u in match.assigned.items() if u["pid"] == seat.pid), reverse=True)
            if not mine:
                break
            unit = match.assigned.pop(mine[0])
            if unit["soldier"]:
                seat.soldiers -= 1
            else:
                seat.units -= 1
        lost += 1
    return lost
