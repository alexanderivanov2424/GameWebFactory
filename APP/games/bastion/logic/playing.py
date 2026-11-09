"""Bastion: playing a hand card (act phase, on your turn): blueprints build, curses are paid off,
actions pay their cost and do what they say (repair, cure, gain, draw, adds, trash).

    play(match, pid, uid, x=None, y=None, rotation=0, remove=())
        a blueprint goes on x, y (its top-left cell, turned `rotation` quarter turns); a repair or
        cure card on the building covering x, y; anything else as is. `remove`: the other hand
        uids a trash card (Absolution) removes from the deck for good (not curses).
Building: the structure's cost comes from the stockpile; the blueprint leaves the deck; a
structure with "card" adds that card to the builder's discard pile. Structures have no owner;
the log says who built what.
"""

from gamekit import LobbyError

from . import combat, economy
from .cards import CARDS, amount_text
from .structures import STRUCTURES, a


def play(match, pid, uid, x=None, y=None, rotation=0, remove=()):
    seat = match.acting(pid)
    instance = seat.hand_card(uid)
    card = CARDS[instance["card"]]
    if remove and not card["trash"]:
        raise LobbyError(f"{card['name']} doesn't remove cards.")
    if card["kind"] == "build":
        build(match, seat, instance, card, x, y, rotation)
    elif card["kind"] == "curse":
        match.pay(card["pay"], card["name"])
        seat.take(instance)  # gone from the deck for good
        match.write(f"{seat.name} paid off {card['name']}.", pid)
        foe = match.foes[instance["from"]] if "from" in instance else None
        if card["hurts"] and foe and foe.defeat.get("cards"):
            combat.hurt(match, foe, 1)
    else:
        action(match, seat, instance, card, x, y, remove)


def build(match, seat, instance, card, x, y, rotation):
    if x is None or y is None:
        raise LobbyError("Pick where to build.")
    spec = STRUCTURES[card["structure"]]
    match.board.check(spec["id"], rotation, x, y)
    match.pay(spec["cost"], a(spec["name"]).capitalize())
    structure = match.board.place(spec["id"], rotation, x, y)
    seat.take(instance)
    if structure and spec["card"]:
        seat.deck.add(spec["card"])
    extra = f" (+ {CARDS[spec['card']]['name']} card)" if structure and spec["card"] else ""
    match.write(f"{seat.name} built {a(spec['name'])}{extra}.", seat.pid)


def trashed(seat, instance, card, remove):
    """The hand instances a trash card removes (checked, nothing changed yet)."""
    if len(set(remove)) != len(remove) or len(remove) > card["trash"]:
        raise LobbyError(f"{card['name']} removes up to {card['trash']} different cards.")
    picked = [seat.hand_card(uid) for uid in remove]
    if instance in picked:
        raise LobbyError(f"{card['name']} can't remove itself.")
    if any(CARDS[c["card"]]["kind"] == "curse" for c in picked):
        raise LobbyError("Curses can only be paid off.")
    return picked


def action(match, seat, instance, card, x, y, remove=()):
    target = None
    cost = dict(card["cost"])
    picked = trashed(seat, instance, card, remove) if card["trash"] else []
    if card["repair"]:
        target = match.structure_at(x, y)
        for k, n in economy.repair_cost(target).items():
            cost[k] = cost.get(k, 0) + n
    elif card["cure"]:
        target = match.structure_at(x, y)
        if target.plague is None:
            raise LobbyError("That building isn't plagued.")
    match.pay(cost, card["name"])
    seat.take(instance)
    seat.deck.discard([instance])
    said = []
    for removed in picked:
        seat.take(removed)  # gone from the deck for good
    if picked:
        said.append("removed " + ", ".join(CARDS[c["card"]]["name"] for c in picked) + " from their deck")
    elif card["trash"]:
        said.append("removed nothing")
    if card["repair"]:
        match.board.repair(target)
        said.append(f"repaired the {target.spec['name']}")
    if card["cure"]:
        said.append(combat.cure(match, target))
    for k, n in card["gain"].items():
        if k == "soldiers":
            match.soldiers += n
        else:
            match.stock[k] += n
    if card["gain"]:
        said.append("gained " + amount_text(card["gain"]))
    if card["draw"]:
        seat.draw(card["draw"])
        said.append(f"drew {card['draw']}")
    if card["adds"]:
        seat.deck.add(card["adds"])
        said.append(f"took {a(CARDS[card['adds']]['name'])} card")
    match.write(f"{seat.name} played {card['name']}: {', '.join(said) or 'done'}.", seat.pid)
