"""Gilded Trail: moving explorers, paying for spaces and clearing blockades.

Functions take the Match (m) and a player id; they raise LobbyError for illegal moves.
    requirement(m, pid, ei, to)  what entering `to` with explorer `ei` costs (see below)
    move(m, pid, ei, to, uid)    pay with a movement card (uid None = keep using the current one)
    pay(m, pid, ei, to, uids)    enter rubble / a base camp, or clear a rubble blockade, with cards
    guide(m, pid, ei, to)        the Local Guide: an adjacent space, ignoring its requirement
    options(m, pid)              every legal step for pid's explorers right now (for the client)

Rules:
- Spaces: machete (jungle), paddle (water), coin (village) need a movement card of that kind
  (or a joker) with at least the space's value. One card can carry one explorer over several
  spaces until its value runs out; a joker keeps the kind of the first space it paid for.
  Starting another card drops the rest of the current one. Cards are never combined.
- Rubble: discard that many cards from hand. Base camp: remove that many from the game.
- Mountains and start spaces can't be entered, nor spaces with an explorer on them.
- Blockades sit on tile borders. The first player to pay one (like a space: a card of its
  kind and value, or discards for a rubble blockade) takes it and the border is open for
  everyone; the explorer stays where it is, and a card may go on with its leftover value.
- Entering a golden city space takes the explorer off the board: it has arrived.
- Single-use movement cards are removed from the game when they pay for a step or a
  blockade; discarded for rubble, they just go to the discard pile.
"""

from gamekit import LobbyError

from .board import adjacent, neighbors, passable

CARD_PAID = ("machete", "paddle", "coin")


def occupied(m, hex_key):
    return any(hex_key in p["explorers"] for p in m.players.values())


def explorer_at(m, pid, ei):
    explorers = m.players[pid]["explorers"]
    if type(ei) is not int or not 0 <= ei < len(explorers):
        raise LobbyError("Pick one of your explorers.")
    if not explorers[ei]:
        raise LobbyError("That explorer has already arrived.")
    return explorers[ei]


def step_target(m, pid, ei, to):
    """Checks shared by every way of stepping: returns (from hex, to hex data, open blockade)."""
    at = explorer_at(m, pid, ei)
    h = m.board.hexes.get(to)
    if h is None or not adjacent(at, to):
        raise LobbyError("Pick a space next to your explorer.")
    if not passable(h):
        raise LobbyError("Nobody can enter that space.")
    if occupied(m, to):
        raise LobbyError("Another explorer is on that space.")
    blockade = m.board.border(at, to)
    if blockade is not None and blockade["id"] in m.taken:
        blockade = None
    return at, h, blockade


def requirement(m, pid, ei, to):
    """{"need": machete|paddle|coin|discard|remove, "v": n, "blockade"?: id}."""
    _, h, blockade = step_target(m, pid, ei, to)
    if blockade is not None:
        need = "discard" if blockade["t"] == "rubble" else blockade["t"]
        return {"need": need, "v": blockade["v"], "blockade": blockade["id"]}
    need = {"rubble": "discard", "camp": "remove"}.get(h["t"], h["t"])
    return {"need": need, "v": h["v"]}


def can_pay(kind, left, req):
    return req["need"] in CARD_PAID and kind in (req["need"], "joker") and left >= req["v"]


def move(m, pid, ei, to, uid=None):
    req = requirement(m, pid, ei, to)
    if req["need"] not in CARD_PAID:
        raise LobbyError("That costs cards from your hand: choose which to "
                         + ("remove." if req["need"] == "remove" else "discard."))
    moving = m.moving
    if uid is None or (moving and moving["uid"] == uid):
        if not moving or moving["left"] <= 0:
            raise LobbyError("Pick a movement card from your hand first.")
        if moving["explorer"] != ei:
            raise LobbyError("A card moves only one explorer. Pick a new card for this one.")
        if not can_pay(moving["kind"], moving["left"], req):
            raise LobbyError(f"Your {m.card_name(moving['card'])} can't pay that: it has "
                             f"{moving['left']} {moving['kind']} left, and this needs {req['v']} {req['need']}.")
    else:
        card = m.hand_card(pid, uid)
        kind, value = m.cards[card["card"]]["kind"], m.cards[card["card"]]["value"]
        if kind == "action":
            raise LobbyError("Action cards don't move explorers; play them instead.")
        if not can_pay(kind, value, req):
            raise LobbyError(f"{m.card_name(card['card'])} can't pay that: it needs {req['v']} {req['need']}.")
        m.take_from_hand(pid, [uid])
        m.use_card(pid, card, single_removed=True)
        m.moving = moving = {"uid": uid, "card": card["card"], "explorer": ei, "kind": kind, "left": value}
    if moving["kind"] == "joker":
        moving["kind"] = req["need"]
    moving["left"] -= req["v"]
    if "blockade" in req:
        claim(m, pid, req["blockade"])
    else:
        place(m, pid, ei, to)


def pay(m, pid, ei, to, uids):
    req = requirement(m, pid, ei, to)
    if req["need"] in CARD_PAID:
        raise LobbyError("That space is paid with a movement card, not by discarding.")
    if len(uids) != req["v"] or len(set(uids)) != len(uids):
        raise LobbyError(f"Choose exactly {req['v']} card{'s' if req['v'] > 1 else ''}.")
    cards = m.take_from_hand(pid, uids)
    names = ", ".join(m.card_name(c["card"]) for c in cards)
    if req["need"] == "remove":
        m.players[pid]["removed"].extend(cards)
        m.add_log(pid, f"{m.names[pid]} removed {names} from the game to enter a base camp.")
    else:
        m.played.extend(cards)
        m.add_log(pid, f"{m.names[pid]} discarded {names}" + (" to clear a blockade." if "blockade" in req else " to cross rubble."))
    m.moving = None
    if "blockade" in req:
        claim(m, pid, req["blockade"])
    else:
        place(m, pid, ei, to)


def guide(m, pid, ei, to):
    _, _, blockade = step_target(m, pid, ei, to)
    if blockade is not None:
        claim(m, pid, blockade["id"])
    else:
        place(m, pid, ei, to)


def claim(m, pid, blockade_id):
    m.taken[blockade_id] = pid
    m.players[pid]["blockades"].append(blockade_id)
    b = m.board.blockades[blockade_id]
    m.add_log(pid, f"{m.names[pid]} cleared blockade {blockade_id + 1} ({b['v']} {b['t']}).")


def place(m, pid, ei, to):
    player = m.players[pid]
    if not m.board.hexes[to].get("goal"):
        player["explorers"][ei] = to
        return
    player["explorers"][ei] = ""
    if m.moving and m.moving["explorer"] == ei:
        m.moving = None
    m.add_log(pid, f"{m.names[pid]}'s explorer reached the golden city!")
    if not any(player["explorers"]):
        player["arrived"] = m.turn_number
        if not m.final_round:
            m.add_log(None, "The round finishes so everyone gets the same number of turns.")
        m.final_round = True


def options(m, pid):
    """{explorer index: {hex: {"need", "v", "blockade"?, "cards": [uids], "continue": bool}}}."""
    out = {}
    hand = m.players[pid]["hand"]
    for ei, at in enumerate(m.players[pid]["explorers"]):
        if not at:
            continue
        steps = {}
        for to in neighbors(at):
            try:
                req = requirement(m, pid, ei, to)
            except LobbyError:
                continue
            if req["need"] in CARD_PAID:
                req["cards"] = [c["uid"] for c in hand
                                if can_pay(m.cards[c["card"]]["kind"], m.cards[c["card"]]["value"], req)]
                mv = m.moving
                req["continue"] = bool(mv and mv["explorer"] == ei and can_pay(mv["kind"], mv["left"], req))
            else:
                req["cards"] = [c["uid"] for c in hand] if len(hand) >= req["v"] else []
                req["continue"] = False
            steps[to] = req
        out[str(ei)] = steps
    return out


def guide_targets(m, pid):
    """{explorer index: [hexes]} the Local Guide may step to."""
    out = {}
    for ei, at in enumerate(m.players[pid]["explorers"]):
        if not at:
            continue
        targets = []
        for to in neighbors(at):
            try:
                step_target(m, pid, ei, to)
            except LobbyError:
                continue
            targets.append(to)
        out[str(ei)] = targets
    return out
