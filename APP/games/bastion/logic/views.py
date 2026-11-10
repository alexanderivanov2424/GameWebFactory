"""Bastion: what clients see. Built fresh for every state; the catalog (structure kinds, cards,
icons, terrain) is the same for the whole game and cached on the match. PatchState: no None in
dicts ("" or -1 instead).

public(match) = {
    catalog: "width", "height", "terrain" (rows of letters), "kinds" {structure id: view},
             "cards" {card id: view}, "icons" {resource / "decrees" / "units" / "soldiers": icon},
             "resources" [ids in order], "reach" (units.REACH), "reshuffleCost"
    "names" / "colors" {pid: ...} (everyone who started, so a leaver's buildings keep a colour)
    "round", "phase" ("setup" | "place" | "resolve" | "plan"), "step",
    "setup": {"pid", "kind"} (setup phase) or "",
    "structures": {uid: {"kind", "x", "y", "owner", "tokens"}}, "roads": {"x,y": owner},
    "units": {"x,y": {"pid", "soldier", "new"}},
    "seats": {pid: Seat.public() + "free", "freeSoldiers"},
    "market": {"blueprints": [card id], "actions": [card id]},
    "report": [{"pid", "text"}] this round's resolution, "log": [{"text", "round", "pid"?}] }
private(match, pid) = {
    "hand": [{"uid", "card"}],
    "places": {"x,y": {"job", "soldier", "text"}} where you may place a unit now (place phase,
              not ready; whether you have a free unit of that kind is up to the client),
    "setup": ["x,y"] where your next setup piece may go (your setup turn),
    "targets": {card uid: ["x,y"] (blueprints) or {"x,y": text} (Orders)} in the plan phase,
    "prompt": {"x", "y", "title", "options": [{"id", "label", "ok", "why"}], "left": n} or "",
    "reshuffled": [halves you reshuffled this round] }
"""

from . import playing, resolution, setup, units
from .cards import CARDS, public as card_public
from .market import RESHUFFLE_COST
from .structures import ICONS, RESOURCE_IDS, STRUCTURES, public as structure_public

LOG_SIZE = 80


def key(cell):
    return f"{cell[0]},{cell[1]}"


def catalog(match):
    if getattr(match, "_catalog", None) is None:
        board = match.board
        rows = ["".join({"grass": ".", "forest": "F", "mountain": "M", "water": "~"}[t] for t in row)
                for row in board.terrain]
        match._catalog = {
            "width": board.width, "height": board.height, "terrain": rows,
            "kinds": {sid: structure_public(s, STRUCTURES) for sid, s in STRUCTURES.items()},
            "cards": {cid: card_public(c) for cid, c in CARDS.items()},
            "icons": dict(ICONS), "resources": list(RESOURCE_IDS), "reach": units.REACH,
            "reshuffleCost": RESHUFFLE_COST,
        }
    return match._catalog


def public(match):
    now = setup.current(match)
    seats = {}
    for pid, seat in match.seats.items():
        seats[pid] = seat.public() | {"free": units.free(match, pid), "freeSoldiers": units.free_soldiers(match, pid)}
    return {
        **catalog(match),
        "names": dict(match.names), "colors": dict(match.colors),
        "round": match.round, "phase": match.phase, "step": match.step,
        "setup": {"pid": now[0], "kind": now[1]} if now else "",
        **match.board.public(),
        "units": {key(c): dict(u) for c, u in match.assigned.items()},
        "seats": seats,
        "market": {half: list(m.slots) for half, m in match.markets.items()},
        "report": [dict(line) for line in match.report["lines"]],
        "log": match.log[-LOG_SIZE:],
    }


def private(match, pid):
    seat = match.seats.get(pid)
    if seat is None:
        return None
    view = {"hand": [dict(c) for c in seat.hand], "places": {}, "setup": [], "targets": {}, "prompt": "",
            "reshuffled": sorted(seat.reshuffled)}
    if match.result is not None:
        return view
    if match.phase == "setup":
        view["setup"] = [key(c) for c in setup.spots(match, pid)]
    elif match.phase == "place" and not seat.ready:
        view["places"] = {key(c): job for c, job in units.targets(match, pid).items()}
    elif match.phase == "resolve" and seat.prompts:
        prompt = seat.prompts[0]
        x, y = prompt["cell"]
        view["prompt"] = {"x": x, "y": y, "title": resolution.title(match, prompt),
                          "options": resolution.options(match, seat, prompt), "left": len(seat.prompts)}
    elif match.phase == "plan" and not seat.ready:
        spots = {}
        for c in seat.hand:
            card = CARDS[c["card"]]
            if card["kind"] == "build":
                kind = card["structure"]
                if kind not in spots:
                    spots[kind] = [key(cell) for cell in playing.build_spots(match, pid, kind)]
                view["targets"][str(c["uid"])] = spots[kind]
            elif card["recall"]:
                view["targets"][str(c["uid"])] = {key(cell): t for cell, t in playing.recall_spots(match, pid).items()}
    return view
