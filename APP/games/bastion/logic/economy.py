"""Bastion: what buildings make, working them and repairs (pure rules on a Board).

Output of a building = its work's base amount + every bonus condition it meets (structures.py)
- 1 per blight tile next to it, never below 0. Bonuses read the board as it is now, so new
buildings change their neighbours' output. Unskilled work (Villagers) gets the base and the
penalties but none of the bonuses.

Where goods go: a building next to a depot (the keep, a storage yard) or that is one delivers
straight to the stockpile. Otherwise goods wait in the building (up to STORE_CAP) until a haul
card sends them off in a carriage (carriages.py). A building using inputs needs a link (depot or
road) to fetch them from the stockpile. Gold, soldiers, keep health and cures never wait.

    output(board, kind, cells, unskilled=False) -> (amount, parts)   parts = [[reason, +/-n], ...], base first
    amount(board, structure, card=None) -> what working it with that card makes (output + boost)
    why_not(board, structure, stock, round_no, plagued) -> reason it can't work now, or None
    work(board, structure, stock, card=None) -> (output key, amount, "stockpile" | "stored" | None)
    repair_cost(structure) -> {"wood": ruined tiles}
    STORE_CAP
"""

from gamekit import LobbyError

from .cards import amount_text
from .structures import GOODS, STRUCTURES, a, describe

STORE_CAP = 6


def output(board, kind, cells, unskilled=False):
    spec = STRUCTURES[kind]
    makes = spec["work"]["makes"]
    base = next(iter(makes.values()))
    parts = [["base", base]]
    for cond in spec["bonuses"]:
        count = board.near(cells, cond["near"])
        if "each" in cond:
            value = cond["each"] * min(count, cond["max"])
        else:
            value = cond["bonus"] if count >= cond["min"] else 0
        if value and not (unskilled and value > 0):
            parts.append([describe(cond, STRUCTURES), value])
    blights = board.blighted(cells)
    if blights:
        parts.append(["enemy blight next to it", -blights])
    return max(0, sum(v for _, v in parts)), parts


def amount(board, s, card=None):
    if card is None:
        return output(board, s.kind, s.cells)[0]
    return output(board, s.kind, s.cells, card["unskilled"])[0] + card["boost"]


def why_not(board, s, stock, round_no, plagued):
    work = s.spec["work"]
    if not work:
        return f"{a(s.spec['name']).capitalize()} isn't worked."
    if s.worked:
        return f"That {s.spec['name']} has already worked this round."
    if s.ruined:
        return f"That {s.spec['name']} is damaged: repair it first."
    if s.plague is not None:
        return f"That {s.spec['name']} is plagued: cure it first."
    if s.frozen == round_no:
        return f"That {s.spec['name']} is frozen this round."
    if work["uses"]:
        if not board.link(s):
            return f"That {s.spec['name']} is cut off: link it to the keep or a storage yard by road."
        missing = {k: n for k, n in work["uses"].items() if stock.get(k, 0) < n}
        if missing:
            return f"Working it needs {amount_text(work['uses'])} in the stockpile."
    if "cure" in work["makes"] and not plagued:
        return "Nothing is plagued."
    if output(board, s.kind, s.cells)[0] <= 0:
        return f"That {s.spec['name']} would make nothing."
    return None


def work(board, s, stock, card=None):
    """Work s with card (why_not must be None, amount > 0): pay its inputs, mark it worked,
    deliver goods."""
    spec = s.spec["work"]
    for k, n in spec["uses"].items():
        stock[k] -= n
    s.worked = True
    key = next(iter(spec["makes"]))
    made = amount(board, s, card)
    if key in GOODS:
        if board.link(s) == "depot":
            stock[key] += made
            return key, made, "stockpile"
        kept = min(made, STORE_CAP - s.stored())
        if kept:
            s.store[key] = s.store.get(key, 0) + kept
        return key, kept, "stored"
    if key == "gold":
        stock["gold"] += made
        return key, made, "stockpile"
    return key, made, None


def repair_cost(s):
    if not s.ruined:
        raise LobbyError("That structure isn't damaged.")
    return {"wood": len(s.ruined)}
