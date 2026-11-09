"""Bastion: what buildings make, working them and repairs (pure rules on a Board).

Output of a building = its work's base amount + every bonus condition it meets (structures.py)
- 1 per blight tile next to it, never below 0. Bonuses read the board as it is now, so new
buildings change their neighbours' output. A unit working it may spend 1 tool from the
stockpile for +TOOL_BOOST output (one tool per resolution).

Where goods go: a building next to a depot (the keep, a storage yard) or that is one delivers
straight to the stockpile. Otherwise goods wait in the building (up to STORE_CAP) until a unit
hauls them (hauling.py). A building using inputs needs a link (depot or road) to fetch them from
the stockpile. Gold, soldiers, keep health and cures never wait.

    output(board, kind, cells) -> (amount, parts)   parts = [[reason, +/-n], ...], base first
    amount(board, structure, tool=False) -> what working it makes (output + the tool's boost)
    blocked(board, structure, round_no, plagued) -> why no unit may go on it now, or None
                                   (not worked, damaged, plagued, frozen, nothing to cure, makes nothing)
    why_not(board, structure, stock, round_no, plagued, tool=False) -> why a unit can't work it
                                   right now (blocked, already worked, cut off, inputs or the tool
                                   missing from the stockpile), or None
    work(board, structure, stock, tool=False) -> (output key, amount, "stockpile" | "stored" | None)
    preview(board, structure, tool=False) -> "+2 wood (stored)" style text
    repair_cost(structure) -> {"wood": ruined tiles}
    STORE_CAP, TOOL_BOOST
"""

from gamekit import LobbyError

from .cards import amount_text
from .structures import GOODS, OUTPUT_NAMES, STRUCTURES, a, describe

STORE_CAP = 6
TOOL_BOOST = 1  # extra output when a unit spends a tool (tune)


def output(board, kind, cells):
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
        if value:
            parts.append([describe(cond, STRUCTURES), value])
    blights = board.blighted(cells)
    if blights:
        parts.append(["enemy blight next to it", -blights])
    return max(0, sum(v for _, v in parts)), parts


def amount(board, s, tool=False):
    return output(board, s.kind, s.cells)[0] + (TOOL_BOOST if tool else 0)


def blocked(board, s, round_no, plagued):
    if not s.spec["work"]:
        return f"{a(s.spec['name']).capitalize()} isn't worked."
    if s.ruined:
        return f"That {s.spec['name']} is damaged: repair it first."
    if s.plague is not None:
        return f"That {s.spec['name']} is plagued: cure it first."
    if s.frozen == round_no:
        return f"That {s.spec['name']} is frozen this round."
    if "cure" in s.spec["work"]["makes"] and not plagued:
        return "Nothing is plagued."
    if output(board, s.kind, s.cells)[0] <= 0:
        return f"That {s.spec['name']} would make nothing."
    return None


def why_not(board, s, stock, round_no, plagued, tool=False):
    reason = blocked(board, s, round_no, plagued)
    if reason:
        return reason
    if s.worked:
        return f"That {s.spec['name']} has already worked this round."
    uses = dict(s.spec["work"]["uses"])
    if uses and not board.link(s):
        return f"That {s.spec['name']} is cut off: link it to the keep or a storage yard by road."
    if tool:
        uses["tools"] = uses.get("tools", 0) + 1
    if any(stock.get(k, 0) < n for k, n in uses.items()):
        return f"Working it needs {amount_text(uses)} in the stockpile."
    return None


def work(board, s, stock, tool=False):
    """Work s (why_not must be None): pay its inputs (and the tool), mark it worked, deliver goods."""
    spec = s.spec["work"]
    for k, n in spec["uses"].items():
        stock[k] -= n
    if tool:
        stock["tools"] -= 1
    s.worked = True
    key = next(iter(spec["makes"]))
    made = amount(board, s, tool)
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


def preview(board, s, tool=False):
    key = next(iter(s.spec["work"]["makes"]))
    made = amount(board, s, tool)
    text = f"+{made} {OUTPUT_NAMES[key]}"
    if key in GOODS and board.link(s) != "depot":
        room = STORE_CAP - s.stored()
        text += " (stored)" if room >= made else f" (stored: room for {room})"
    uses = dict(s.spec["work"]["uses"])
    if tool:
        uses["tools"] = uses.get("tools", 0) + 1
    return f"{text} for {amount_text(uses)}" if uses else text


def repair_cost(s):
    if not s.ruined:
        raise LobbyError("That structure isn't damaged.")
    return {"wood": len(s.ruined)}
