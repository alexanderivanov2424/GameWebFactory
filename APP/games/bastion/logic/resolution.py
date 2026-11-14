"""Bastion: unit resolution, between the place phase and the planning phase.

When the last player is ready, resolve() goes through every placed unit (tile order, top to
bottom, left to right): automatic jobs happen at once, the rest become prompts in their owner's
queue (seat.prompts), answered one by one (answer()), everyone at the same time. When every
queue is empty the planning phase starts (Match.start_planning).

Automatic (units.job):
    build    one build token off the planned structure; at 0 it is built (a house adds its
             units). The unit goes back to the pool.
    gather   1 wood (forest) or 1 stone (mountain); back to the pool.
    train    the worker becomes a soldier (seat.units - 1, seat.soldiers + 1); off the board.
    work     a building whose work only makes things: it makes them. The unit stays.
    idle / guard   nothing (house / tower). The unit stays (soldiers until the end of the round).
Prompts (the unit stays on a building; on grass it goes back to the pool afterwards):
    "convert"  work with uses: "Spend X to make Y?" -> "yes" / "no"
    "choice"   work with choices: one option id per choice ("0", "1", ...) or "no"
    "tile"     empty grass: "road" (build a road tile there) or "scavenge" (a die: 1/3 nothing,
               1/3 1 wood, 1/3 1 stone)
Every unit stationed on a building is no longer "new" afterwards (it can't be taken back).

    resolve(match)
    options(match, seat, prompt) -> [{"id", "label", "ok", "why"}] for the prompt shown
    answer(match, pid, option)
    SCAVENGE   the die faces
"""

from gamekit import LobbyError

from . import units
from .cards import amount_text
from .structures import GATHER

SCAVENGE = (None, "wood", "stone")


def resolve(match):
    lines = []
    for cell in sorted(match.assigned, key=lambda c: (c[1], c[0])):
        unit = match.assigned[cell]
        seat = match.seats.get(unit["pid"])
        if seat is None:
            continue
        try:
            kind = units.job_here(match, unit["pid"], cell)["job"]
        except LobbyError:  # its building is gone: back to the pool
            units.release(match, cell)
            continue
        uid = match.board.at.get(cell)
        s = match.board.structures[uid] if uid is not None else None
        if kind == "build":
            s.tokens -= 1
            match.board.version += 1
            units.release(match, cell)
            if s.built:
                seat.units += s.spec["units"]
                extra = f" (+{s.spec['units']} units)" if s.spec["units"] else ""
                lines.append((seat.pid, f"built the {s.spec['name']}{extra}"))
            else:
                lines.append((seat.pid, f"worked on the {s.spec['name']} ({s.tokens} to go)"))
        elif kind == "gather":
            got = GATHER[match.board.terrain_at(cell)]
            seat.gain({got: 1})
            units.release(match, cell)
            lines.append((seat.pid, f"gathered 1 {got}"))
        elif kind == "train":
            seat.units -= 1
            seat.soldiers += 1
            units.release(match, cell)
            lines.append((seat.pid, "trained a soldier"))
        elif kind == "work":
            work = s.spec["work"]
            if "choices" in work:
                seat.prompts.append({"type": "choice", "cell": cell})
            elif work["uses"]:
                seat.prompts.append({"type": "convert", "cell": cell})
            else:
                seat.gain(work["makes"])
                lines.append((seat.pid, f"{s.spec['name']}: +{amount_text(work['makes'])}"))
        elif kind == "tile":
            seat.prompts.append({"type": "tile", "cell": cell})
        unit["new"] = False
    match.report = {"round": match.round, "lines": [{"pid": pid, "text": text} for pid, text in lines]}
    for pid, text in lines:
        match.write(f"{match.names[pid]} {text}." if not text[0].isupper() else f"{match.names[pid]}'s {text}.", pid)
    check_done(match)


def options(match, seat, prompt):
    cell = prompt["cell"]
    if prompt["type"] == "tile":
        return [{"id": "road", "label": "Build a road", "ok": True, "why": ""},
                {"id": "scavenge", "label": "Scavenge (roll: nothing, 1 wood or 1 stone)", "ok": True, "why": ""}]
    work = match.board.structures[match.board.at[cell]].spec["work"]
    if prompt["type"] == "convert":
        return [option("yes", work, seat), {"id": "no", "label": "No", "ok": True, "why": ""}]
    return [option(str(i), o, seat) for i, o in enumerate(work["choices"])] + \
        [{"id": "no", "label": "Nothing", "ok": True, "why": ""}]


def option(oid, work, seat):
    short = seat.missing(work["uses"])
    label = (f"Spend {amount_text(work['uses'])} to make {amount_text(work['makes'])}" if work["uses"]
             else f"Make {amount_text(work['makes'])}")
    return {"id": oid, "label": label, "ok": not short, "why": f"Not enough {', '.join(short)}" if short else ""}


def title(match, prompt):
    cell = prompt["cell"]
    if prompt["type"] == "tile":
        return "Empty grass: build a road or scavenge?"
    s = match.board.structures[match.board.at[cell]]
    work = s.spec["work"]
    if prompt["type"] == "convert":
        return f"{s.spec['name']}: spend {amount_text(work['uses'])} to make {amount_text(work['makes'])}?"
    return f"{s.spec['name']}: what should the unit make?"


def answer(match, pid, choice):
    seat = match.seat(pid)
    if match.phase != "resolve" or not seat.prompts:
        raise LobbyError("You have nothing to answer.")
    prompt = seat.prompts[0]
    picked = next((o for o in options(match, seat, prompt) if o["id"] == choice), None)
    if picked is None:
        raise LobbyError("Pick one of the answers.")
    if not picked["ok"]:
        raise LobbyError(picked["why"])
    cell = prompt["cell"]
    said = None
    if prompt["type"] == "tile":
        if choice == "road" and not match.board.empty(cell):
            raise LobbyError("Something is already there.")
        units.release(match, cell)
        if choice == "road":
            match.board.add_road(cell, pid)
            said = "built a road"
        else:
            face = match.rng.choice(SCAVENGE)
            if face:
                seat.gain({face: 1})
            said = f"scavenged {'1 ' + face if face else 'nothing'}"
    elif choice != "no":
        work = match.board.structures[match.board.at[cell]].spec["work"]
        if prompt["type"] == "choice":
            work = work["choices"][int(choice)]
        seat.pay(work["uses"], "That")
        seat.gain(work["makes"])
        name = match.board.structures[match.board.at[cell]].spec["name"]
        said = f"{name}: +{amount_text(work['makes'])}" + (f" for {amount_text(work['uses'])}" if work["uses"] else "")
    seat.prompts.pop(0)
    if said:
        match.report["lines"].append({"pid": pid, "text": said})
        match.write(f"{seat.name} {said}." if not said[0].isupper() else f"{seat.name}'s {said}.", pid)
    match.step += 1
    check_done(match)


def check_done(match):
    if match.phase == "resolve" and not any(s.prompts for s in match.seats.values()):
        match.start_planning()
