"""Bastion: units, the city's fed people put to work each round (worker placement).

Start of a round (hand_out): units = population - hungry (from the last upkeep, food.py), split
equally among the seated players; the remainder goes one each to players in turn order from
this round's first player.

Targets are strings, the keys of Match.placed ({target: {pid: units}}) and of the public
"placements":
    "s<uid>"       a structure that is worked: 1 unit per structure per round (first come;
                   structures belong to nobody). Not one that is ruined, plagued, frozen this
                   round or would make nothing (economy.blocked).
    "haul"         the Hauling pool (unlimited)
    "fight<i>"     the pool of active enemy i (unlimited; only enemies with defeat.soldiers)
    "raze<x>,<y>"  an enemy lair or blight tile: 1 unit per tile
Place phase: everyone places at once; a player may take placements back until they're ready.
Act phase, on your turn: each unit resolves once and leaves the board:
    work   the structure makes its output (economy.work); tool=True spends 1 tool for +1
    haul   up to hauling.capacity goods from a source building ("from" uid; default: the one
           with the most goods) straight to the stockpile
    fight  1 strike on that enemy (combat.unit_fight)
    raze   1 strike toward razing that tile (combat.unit_raze)
Unresolved units are lost when their player ends the turn.

    hand_out(match)                      units for this round (Match.start_round)
    parse(match, target) -> (kind, value)   kind "s" (Structure) | "haul" (None) | "fight" (Foe) |
                                         "raze" ((x, y)); LobbyError if it names nothing
    place_reason(match, target) -> why no unit may go there now (ignoring who asks), or None
    place(match, pid, target) / unplace(match, pid, target)
    resolve(match, pid, target, tool=False, source=None)
    resolve_reason(match, target, tool=False, source=None) -> why it can't resolve now, or None
    mine(match, pid) -> {target: units} pid's placed units
    free(match, pid) -> units pid may still place (0 in the act phase)
    lose(match, pid)                     drop pid's placements (end of turn, leaving)
    clear_gone(match)                    drop placements on enemies or tiles that are gone
    targets(match) -> [target]           every target a unit could be placed on now
    preview(match, target) -> {"text", "tool", "why"}   what resolving it would do (tool: the
                                         text with a tool, "" when no tool applies; why: why it
                                         couldn't resolve right now, "" when it could)
"""

from gamekit import LobbyError

from . import combat, economy, hauling
from .cards import amount_text
from .structures import OUTPUT_NAMES

POOLS = ("haul", "fight")  # targets that take any number of units


def hand_out(match):
    total = max(0, match.population() - match.hungry)
    order = match.order
    base, extra = divmod(total, len(order)) if order else (0, 0)
    for i, pid in enumerate(order):
        seat = match.seats[pid]
        seat.units, seat.spent, seat.ready = base + (1 if i < extra else 0), 0, False
    return total


# --- targets -------------------------------------------------------------------------------

def parse(match, target):
    if not isinstance(target, str):
        raise LobbyError("Pick a target.")
    try:
        if target == "haul":
            return "haul", None
        if target.startswith("s"):
            s = match.board.structures.get(int(target[1:]))
            if s:
                return "s", s
        elif target.startswith("fight"):
            index = int(target[5:])
            if 0 <= index < len(match.foes) and match.foes[index].active:
                return "fight", match.foes[index]
        elif target.startswith("raze"):
            x, y = (int(v) for v in target[4:].split(","))
            if (x, y) in match.board.blights:
                return "raze", (x, y)
    except ValueError:
        pass
    raise LobbyError("There's nothing there to send a unit to.")


def taken(match, target):
    return sum(match.placed.get(target, {}).values())


def place_reason(match, target):
    try:
        kind, value = parse(match, target)
    except LobbyError as error:
        return str(error)
    if kind == "s":
        if taken(match, target):
            return f"Someone is already working that {value.spec['name']}."
        return economy.blocked(match.board, value, match.round, match.plagued())
    if kind == "fight" and not value.fightable:
        return f"Units can't fight the {value.name}."
    if kind == "raze" and taken(match, target):
        return "A unit is already on that tile."
    return None


def targets(match):
    found = ["haul"]
    found += [f"fight{f.index}" for f in match.foes if f.active and f.fightable]
    found += [f"raze{x},{y}" for x, y in sorted(match.board.blights)]
    found += [f"s{uid}" for uid, s in sorted(match.board.structures.items()) if s.spec["work"]]
    return [t for t in found if not place_reason(match, t)]


def mine(match, pid):
    return {t: by[pid] for t, by in match.placed.items() if by.get(pid)}


def free(match, pid):
    seat = match.seats[pid]
    if match.phase != "place":
        return 0
    return seat.units - seat.spent - sum(mine(match, pid).values())


def place(match, pid, target):
    seat = match.placing(pid)
    if free(match, pid) <= 0:
        raise LobbyError("You have no units left to place.")
    reason = place_reason(match, target)
    if reason:
        raise LobbyError(reason)
    by = match.placed.setdefault(target, {})
    by[pid] = by.get(pid, 0) + 1
    return seat


def drop(match, pid, target):
    by = match.placed.get(target, {})
    if not by.get(pid):
        raise LobbyError("You have no unit there.")
    by[pid] -= 1
    if not by[pid]:
        del by[pid]
    if not by:
        del match.placed[target]


def unplace(match, pid, target):
    match.placing(pid)
    drop(match, pid, target)


def lose(match, pid):
    for target in list(match.placed):
        by = match.placed[target]
        if pid in by:
            if pid in match.seats:
                match.seats[pid].spent += by[pid]
            del by[pid]
            if not by:
                del match.placed[target]


def clear_gone(match):
    for target in list(match.placed):
        try:
            parse(match, target)
        except LobbyError:
            for pid, n in match.placed.pop(target).items():
                if pid in match.seats:
                    match.seats[pid].spent += n


# --- resolving -------------------------------------------------------------------------------

def resolve_reason(match, target, tool=False, source=None):
    try:
        kind, value = parse(match, target)
    except LobbyError as error:
        return str(error)
    if kind == "s":
        return economy.why_not(match.board, value, match.stock, match.round, match.plagued(), tool)
    if tool:
        return "Tools only help working a building."
    if kind == "haul":
        if source is not None:
            s = match.board.structures.get(source)
            return hauling.why_not(match.board, s) if s else "Pick a building to haul from."
        return None if hauling.best_source(match.board) else "Nothing is waiting to be hauled."
    if kind == "fight" and not value.fightable:
        return f"Units can't fight the {value.name}."
    return None


def resolve(match, pid, target, tool=False, source=None):
    seat = match.acting(pid)
    if not match.placed.get(target, {}).get(pid):
        raise LobbyError("You have no unit there.")
    reason = resolve_reason(match, target, tool, source)
    if reason:
        raise LobbyError(reason)
    kind, value = parse(match, target)
    drop(match, pid, target)
    seat.spent += 1
    if kind == "s":
        said = work(match, value, tool)
    elif kind == "haul":
        said = haul(match, value if source is None else match.board.structures[source])
    elif kind == "fight":
        said = combat.unit_fight(match, seat, value)
    else:
        said = combat.unit_raze(match, seat, value)
    match.write(f"{seat.name}'s unit {said}.", pid)


def work(match, s, tool=False):
    key, amount, where = economy.work(match.board, s, match.stock, tool)
    match.board.version += 1
    name = s.spec["name"]
    with_tool = " with a tool" if tool else ""
    if key == "soldiers":
        match.soldiers += amount
    elif key == "keep":
        healed = min(amount, match.keep_max - match.keep)
        match.keep += healed
        return f"worked the {name}{with_tool}: the keep healed by {healed}"
    elif key == "cure":
        # beating the enemy that spread the plague lifts the rest of it: skip those
        cured = [combat.cure(match, p) for p in match.plagued()[:amount] if p.plague is not None]
        return f"worked the {name}{with_tool}: " + ", ".join(cured)
    stored = " (stored, waiting for a haul)" if where == "stored" else ""
    return f"worked the {name}{with_tool}: {amount} {OUTPUT_NAMES[key]}{stored}"


def haul(match, s=None):
    s = s or hauling.best_source(match.board)
    cap = hauling.capacity(match.board, match.hauled)
    match.hauled += 1
    taken_goods = hauling.take(s, cap)
    for k, n in taken_goods.items():
        match.stock[k] += n
    match.board.version += 1
    return f"hauled {amount_text(taken_goods)} from the {s.spec['name']} (carries {cap})"


# --- previews --------------------------------------------------------------------------------

def preview(match, target):
    kind, value = parse(match, target)
    tool = ""
    if kind == "s":
        text = economy.preview(match.board, value)
        tool = economy.preview(match.board, value, tool=True)
    elif kind == "haul":
        best = hauling.best_source(match.board)
        cap = hauling.capacity(match.board, match.hauled)
        text = f"haul up to {cap} goods" + (f" (most waiting: {amount_text(best.store)} at the {best.spec['name']})"
                                            if best else "")
    elif kind == "fight":
        per = value.defeat["soldiers"]
        text = f"1 damage to the {value.name}" if per - value.strikes <= 1 else \
            f"1 strike on the {value.name} ({value.strikes} of {per} toward the next damage so far)"
    else:
        blight = match.board.blights[value]
        cost = combat.raze_cost(match, blight)
        text = f"raze the {blight['name']}" if cost - blight["strikes"] <= 1 else \
            f"1 strike toward razing the {blight['name']} ({blight['strikes']} of {cost} so far)"
    return {"text": text, "tool": tool, "why": resolve_reason(match, target) or ""}
