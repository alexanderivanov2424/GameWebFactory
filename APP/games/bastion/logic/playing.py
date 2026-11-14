"""Bastion: playing a hand card in the planning phase (Match.play). Every card's cost (cost, or
pay for curses) may include royal decrees; it is paid first.

    build    plans the structure on empty grass within units.REACH of your built buildings and
             roads (and its "requires"): it appears greyed out with its build tokens (built at once
             with 0). The blueprint leaves your deck.
    action   gain, draw, adds (a card into your discard pile), recall (Orders: x, y of your
             building with a stationed unit of yours: it goes back to your pool), trade (to: another
             player, give: {resource: n}, either 3 different resources 1 each or 2 of one).
             Then the card goes to your discard pile.
    curse    paid off: it leaves your deck (dormant enemy curses may hurt their sender).

    play(match, pid, uid, x=None, y=None, to=None, give=None)
    build_spots(match, pid, kind)   [(x, y)] where pid may plan that structure now
    recall_spots(match, pid)        {(x, y): text} pid's buildings with a stationed unit
    gift_reason(match, pid, to, give) -> None or why that trade can't happen
"""

from gamekit import LobbyError

from . import units
from .cards import CARDS, amount_text, price_of
from .structures import RESOURCE_IDS, STRUCTURES


def build_spots(match, pid, kind):
    board = match.board
    out = []
    for cell in sorted(board.reach(pid, units.REACH), key=lambda c: (c[1], c[0])):
        try:
            board.check(kind, *cell)
        except LobbyError:
            continue
        out.append(cell)
    return out


def recall_spots(match, pid):
    board = match.board
    return {cell: f"Send your unit at the {board.structures[board.at[cell]].spec['name']} back to your pool"
            for cell in sorted(match.assigned) if units.stationed(match, pid, cell)}


def gift_reason(match, pid, to, give):
    if to == pid:
        return "Trade with another player."
    if to not in match.seats:
        return "Pick another player to trade with."
    if not isinstance(give, dict) or any(k not in RESOURCE_IDS for k in give):
        return "Pick resources to give."
    give = {k: n for k, n in give.items() if n}
    counts = sorted(give.values())
    if counts not in ([1, 1, 1], [2]):
        return "Give 3 different resources (1 each) or 2 of the same resource."
    short = match.seats[pid].missing(give)
    if short:
        return f"You don't have enough {', '.join(short)}."
    return None


def play(match, pid, uid, x=None, y=None, to=None, give=None):
    seat = match.planning(pid)
    instance = seat.hand_card(uid)
    card = CARDS[instance["card"]]
    cost = price_of(card)
    if not seat.can_pay(cost):
        seat.pay(cost, card["name"])  # raises with the shortfall
    if card["kind"] == "build":
        kind = card["structure"]
        if x is None:
            raise LobbyError("Pick a tile on the board.")
        if (x, y) not in match.board.reach(pid, units.REACH):
            raise LobbyError(f"Plan buildings within {units.REACH} tiles of your buildings and roads.")
        match.board.check(kind, x, y)
        seat.pay(cost, card["name"])
        seat.take(instance)
        tokens = STRUCTURES[kind]["build"]
        s = match.board.place(kind, x, y, pid, tokens)
        if s.built:
            seat.units += s.spec["units"]
        match.write(f"{seat.name} planned {'and built ' if s.built else ''}a {s.spec['name']}.", pid)
        return
    if card["kind"] == "curse":
        seat.pay(cost, card["name"])
        seat.take(instance)
        match.write(f"{seat.name} paid off {card['name']} ({amount_text(cost)}).", pid)
        return
    said = []
    if card["recall"]:
        if x is None or not units.stationed(match, pid, (x, y)):
            raise LobbyError("Pick one of your buildings with a unit on it.")
    if card["trade"]:
        why = gift_reason(match, pid, to, give)
        if why:
            raise LobbyError(why)
        give = {k: n for k, n in give.items() if n}
    seat.pay(cost, card["name"])
    seat.take(instance)
    if card["recall"]:
        name = match.board.structures[match.board.at[(x, y)]].spec["name"]
        units.release(match, (x, y))
        said.append(f"called a unit back from the {name}")
    if card["trade"]:
        seat.pay(give, "Trade")
        match.seats[to].gain(give)
        said.append(f"gave {match.names[to]} {amount_text(give)}")
    if card["gain"]:
        seat.gain(card["gain"])
        said.append(f"gained {amount_text(card['gain'])}")
    if card["draw"]:
        seat.draw(card["draw"])
        said.append(f"drew {card['draw']}")
    seat.deck.discard([instance])
    if card["adds"]:
        seat.deck.add(card["adds"])
        said.append(f"took {a_card(card['adds'])}")
    match.write(f"{seat.name} played {card['name']}" + (f": {', '.join(said)}" if said else "") + ".", pid)


def a_card(card_id):
    name = CARDS[card_id]["name"]
    return ("an " if name[:1].lower() in "aeiou" else "a ") + name
