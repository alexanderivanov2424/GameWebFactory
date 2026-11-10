"""Bastion 2: what clients see. PatchState: no None inside dicts ("" instead); cells are "x,y".

public(match) = {
    catalog (same all game, cached): "cards" {id: card view}, "resources" {id: {"name", "icon",
        "temporary"}}, "temporary" [ids], "icons", "handSize", "buyActions", "setupPieces"
    "names" / "colors" {pid: ...} (everyone who started), "order" [pids still playing],
    "stage", "round", "mode", "current" (pid or ""), "bounds" [x0, y0, x1, y1],
    "structures" {"x,y": {"kind", "owner", "pending"}},
    "market": {"always": [card id], "slots": [card id or ""], "left": n},
    "seats" {pid: {"name", "color", "food", "foodCap", "population", "popUsed", "actions",
                   "temp" {res: n}, "play" [card id], "hand", "draw", "discard", "deck" (cards
                   owned), "done", "setup" (pieces placed)}},
    "log" {index: {"text", "pid", "round"}}, "logCount" }
private(match, pid) = {
    "hand": [{"uid", "card", "temp", "why", "pay", "discard"}]  why: "" if it can be played now
            (upkeep: pay / discard say why each way can't be used, "" if it can),
    "spots": ["x,y"] where the selected structure / next setup piece may go,
    "setup": the next setup piece or "",
    "uses": {"x,y": {"why"}} your structures with an action ("" = usable now),
    "pending": {"x,y": {"uid", "card", "skip" [optional add indexes turned off]}},
    "buy": why buying is refused now ("" = allowed), "turn": why you can't act now ("" = you can),
    "discardPile": [card id] (yours, newest last), "deckList": {card id: copies you own} }
"""

from .content import CARDS, ICONS, RESOURCES, STRUCTURES, TEMPORARY, card_text, effect_text
from .effects import food_cap, play_reason, use_reason
from .match import BUY_ACTIONS, HAND_SIZE, SETUP_PIECES


def key(cell):
    return f"{cell[0]},{cell[1]}"


def card_view(card):
    view = {"name": card["name"], "icon": card["icon"], "kind": card["kind"], "text": card_text(card)}
    if card["kind"] == "resource":
        view |= {"resource": card["resource"], "value": card["value"]}
    elif card["kind"] == "upkeep":
        view |= {"pay": card["pay"], "discard": card["discard"]}
    elif card["kind"] == "action":
        view |= {"actions": card["actions"]}
    elif card["kind"] == "structure":
        s = STRUCTURES[card["structure"]]
        view |= {"cost": s["cost"], "adds": [{"card": a["card"], "count": a["count"], "optional": a["optional"]}
                                             for a in s["on_build"]["add"]]}
        if s["action"]:
            view["action"] = {"name": s["action"]["name"], "actions": s["action"]["actions"],
                              "bundle": s["action"]["bundle"], "text": effect_text(s["action"])}
    return view


def catalog(match):
    if getattr(match, "_catalog", None) is None:
        match._catalog = {
            "cards": {cid: card_view(c) for cid, c in CARDS.items()},
            "resources": {r: {"name": i["name"], "icon": i["icon"], "temporary": i["temporary"]}
                          for r, i in RESOURCES.items()},
            "temporary": list(TEMPORARY), "icons": dict(ICONS), "handSize": HAND_SIZE,
            "buyActions": BUY_ACTIONS, "setupPieces": list(SETUP_PIECES),
        }
    return match._catalog


def owned_cards(seat):
    counts = {}
    piles = (seat.deck.draw_pile, seat.deck.discard_pile, seat.hand, seat.play,
             [p["inst"] for p in seat.pending.values()])
    for pile in piles:
        for inst in pile:
            if not inst.get("temp"):
                counts[inst["card"]] = counts.get(inst["card"], 0) + 1
    return counts


def seat_public(match, seat):
    return {
        "name": seat.name, "color": seat.color, "food": seat.food, "foodCap": food_cap(match, seat),
        "population": seat.population, "popUsed": seat.pop_used, "actions": seat.actions,
        "temp": {k: n for k, n in seat.temp.items() if n}, "play": [inst["card"] for inst in seat.play],
        "hand": len(seat.hand), "draw": len(seat.deck.draw_pile), "discard": len(seat.deck.discard_pile),
        "deck": sum(owned_cards(seat).values()), "done": seat.done, "setup": seat.setup,
    }


def public(match):
    return {
        **catalog(match),
        "names": dict(match.names), "colors": dict(match.colors), "order": list(match.order),
        "stage": match.stage, "round": match.round, "mode": match.mode, "current": match.current() or "",
        "bounds": list(match.board.bounds()),
        "structures": {key(c): {"kind": s["kind"], "owner": s["owner"], "pending": s["pending"]}
                       for c, s in match.board.structures.items()},
        "market": {"always": list(match.market.always), "slots": list(match.market.slots),
                   "left": match.market.left()},
        "seats": {pid: seat_public(match, seat) for pid, seat in match.seats.items()},
        "log": {str(match.log_count - len(match.log) + i): entry for i, entry in enumerate(match.log)},
        "logCount": match.log_count,
    }


def private(match, pid):
    seat = match.seats.get(pid)
    if seat is None:
        return None
    turn = match.turn_reason(pid)
    hand = []
    for inst in seat.hand:
        card = CARDS[inst["card"]]
        entry = {"uid": inst["uid"], "card": inst["card"], "temp": bool(inst.get("temp")),
                 "why": turn or play_reason(match, seat, inst)}
        if card["kind"] == "upkeep":
            entry["pay"] = turn or play_reason(match, seat, inst, "pay")
            entry["discard"] = turn or play_reason(match, seat, inst, "discard")
        hand.append(entry)
    if match.stage == "setup":
        spots = match.setup_spots(pid)
    else:
        spots = [] if turn else match.board.build_spots(pid)
    uses = {}
    for cell, s in match.board.structures.items():
        if s["owner"] == pid and not s["pending"] and STRUCTURES[s["kind"]]["action"]:
            uses[key(cell)] = {"why": turn or use_reason(match, seat, cell)}
    return {
        "hand": hand, "spots": [key(c) for c in spots], "setup": match.setup_piece(pid) or "",
        "uses": uses,
        "pending": {key(c): {"uid": p["inst"]["uid"], "card": p["inst"]["card"], "skip": sorted(p["skip"])}
                    for c, p in seat.pending.items()},
        "buy": turn or match.buy_reason(seat), "turn": turn,
        "discardPile": [inst["card"] for inst in seat.deck.discard_pile],
        "deckList": owned_cards(seat),
    }
