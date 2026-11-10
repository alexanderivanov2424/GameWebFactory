"""Bastion 2: what cards and structures do. Called by Match once it has checked whose turn it is.

    play(match, seat, uid, cell, option, uids)   play a hand card:
        resource   -> +value of its resource (temporary counter, or food up to the storage)
        action     -> costs its action points, then its effect (King: draw 2)
        upkeep     -> option "pay" (its pay cost) or "discard" (exactly `discard` other hand cards,
                      uids); paid-off cards leave the deck, the rest go to the play area
        structure  -> cell: an empty tile next to one of your built structures; pays its cost
                      (temporary resources, food, available population) and goes on the board as
                      pending, built at the end of your turn
    unbuild(match, seat, cell)            take back a pending build: refund, card back to hand
    use(match, seat, cell, uids)          a built structure's action, once a turn (bundle: uids)
    apply(match, seat, effect)            pay / gain / temporary card / draw
    discard(match, seat, inst)            a card leaves the hand unplayed: temporary cards vanish,
                                          upkeep cards punish ("discarded": add a card, lose
                                          population, leave the deck)
    lose_population(match, seat, n)       population -n and as many Villager cards removed
    complete(match, seat)                 end of turn: pending builds become built (+population,
                                          cards added to the discard pile)
"""

from gamekit.validate import LobbyError

from .content import CARDS, STRUCTURES, resource_card

POPULATION_CARD = "villager"


def food_cap(match, seat):
    return sum(STRUCTURES[s["kind"]]["provides"]["food_cap"] for s in match.board.structures.values()
               if s["owner"] == seat.pid and not s["pending"])


def actions_per_turn(match, seat):
    return sum(STRUCTURES[s["kind"]]["provides"]["actions"] for s in match.board.structures.values()
               if s["owner"] == seat.pid and not s["pending"])


def hand_cards(seat, uids, exclude=None):
    """The hand instances for uids (all different, all in hand, none of them `exclude`)."""
    if len(set(uids)) != len(uids):
        raise LobbyError("Pick each card once.")
    cards = []
    for uid in uids:
        inst = seat.find(uid)
        if inst is None or inst is exclude:
            raise LobbyError("Pick cards from your hand.")
        cards.append(inst)
    return cards


# --- why a card can't be played (also sent to the client) -----------------------------------------

def play_reason(match, seat, inst, option=""):
    card = CARDS[inst["card"]]
    kind = card["kind"]
    if kind == "action":
        if seat.actions < card["actions"]:
            return "No actions left."
        return seat.missing(card["pay"])
    if kind == "upkeep":
        if option == "pay":
            return seat.missing(card["pay"]) if card["pay"] else "It can't be paid for."
        if option == "discard":
            if not card["discard"]:
                return "It can't be paid for with cards."
            if len(seat.hand) - 1 < card["discard"]:
                return f"You need {card['discard']} other cards in hand."
            return ""
        reasons = [play_reason(match, seat, inst, o) for o in ("pay", "discard")]
        return "" if "" in reasons else reasons[0]
    if kind == "structure":
        why = seat.missing(STRUCTURES[card["structure"]]["cost"])
        if not why and not match.board.build_spots(seat.pid):
            why = "No room next to your buildings."
        return why
    return ""


# --- playing a hand card --------------------------------------------------------------------------

def play(match, seat, uid, cell=None, option="", uids=()):
    inst = seat.find(uid)
    if inst is None:
        raise LobbyError("That card isn't in your hand.")
    card = CARDS[inst["card"]]
    kind = card["kind"]
    if kind == "structure":
        return build(match, seat, inst, cell)
    if kind == "upkeep":
        return pay_upkeep(match, seat, inst, option, uids)
    why = play_reason(match, seat, inst)
    if why:
        raise LobbyError(why)
    seat.hand.remove(inst)
    seat.play.append(inst)
    if kind == "resource":
        seat.gain({card["resource"]: card["value"]}, food_cap(match, seat))
    else:
        seat.actions -= card["actions"]
        apply(match, seat, card)


def pay_upkeep(match, seat, inst, option, uids):
    card = CARDS[inst["card"]]
    if option not in ("pay", "discard"):
        raise LobbyError("Pay for it or discard cards.")
    why = play_reason(match, seat, inst, option)
    if why:
        raise LobbyError(why)
    victims = []
    if option == "discard":
        victims = hand_cards(seat, list(uids), exclude=inst)
        if len(victims) != card["discard"]:
            raise LobbyError(f"Pick exactly {card['discard']} other cards to discard.")
    seat.hand.remove(inst)
    if option == "pay":
        seat.pay(card["pay"])
    for victim in victims:
        seat.hand.remove(victim)
        discard(match, seat, victim)
    if card["paid_off"]:
        match.note(f"{seat.name} paid off {card['name']}.", seat.pid)
    else:
        seat.play.append(inst)


def build(match, seat, inst, cell):
    structure = STRUCTURES[inst["card"]]
    if cell is None:
        raise LobbyError("Pick a tile to build on.")
    why = seat.missing(structure["cost"])
    if why:
        raise LobbyError(why)
    if cell in match.board.structures:
        raise LobbyError("That tile is taken.")
    if cell not in match.board.build_spots(seat.pid):
        raise LobbyError("Build next to one of your buildings.")
    seat.hand.remove(inst)
    seat.pay(structure["cost"])
    seat.pending[cell] = {"inst": inst, "paid": dict(structure["cost"]), "skip": set()}
    match.board.add(cell, structure["id"], seat.pid, pending=True)


def unbuild(match, seat, cell):
    plan = seat.pending.pop(cell, None)
    if plan is None:
        raise LobbyError("You have no build planned there.")
    match.board.remove(cell)
    seat.refund(plan["paid"])
    seat.hand.append(plan["inst"])


def choose(seat, cell, index, on):
    plan = seat.pending.get(cell)
    if plan is None:
        raise LobbyError("You have no build planned there.")
    adds = STRUCTURES[plan["inst"]["card"]]["on_build"]["add"]
    if not 0 <= index < len(adds) or not adds[index]["optional"]:
        raise LobbyError("That isn't a choice.")
    (plan["skip"].discard if on else plan["skip"].add)(index)


# --- structure actions ----------------------------------------------------------------------------

def use_reason(match, seat, cell):
    s = match.board.structures.get(cell)
    if s is None or s["owner"] != seat.pid or s["pending"]:
        return "That isn't one of your built structures."
    action = STRUCTURES[s["kind"]]["action"]
    if action is None:
        return "That structure has no action."
    if cell in seat.used:
        return "Already used this turn."
    if seat.actions < action["actions"]:
        return "No actions left."
    return seat.missing(action["pay"])


def use(match, seat, cell, uids=()):
    why = use_reason(match, seat, cell)
    if why:
        raise LobbyError(why)
    action = STRUCTURES[match.board.structures[cell]["kind"]]["action"]
    if action["bundle"]:
        bundle(match, seat, action, list(uids))
    seat.used.add(cell)
    seat.actions -= action["actions"]
    apply(match, seat, action)


def bundle(match, seat, action, uids):
    cards = hand_cards(seat, uids)
    defs = [CARDS[inst["card"]] for inst in cards]
    if not defs or any(d["kind"] != "resource" for d in defs):
        raise LobbyError("Pick resource cards to bundle.")
    if len({d["resource"] for d in defs}) != 1:
        raise LobbyError("Bundle cards of one resource.")
    total = sum(d["value"] for d in defs)
    if total not in action["bundle"]:
        raise LobbyError(f"The cards must add up to {' or '.join(map(str, action['bundle']))}.")
    result = resource_card(defs[0]["resource"], total)
    if result is None or len(cards) < 2:
        raise LobbyError("There's nothing to bundle those into.")
    for inst in cards:
        seat.hand.remove(inst)  # bundled cards leave the deck
    seat.hand.append(seat.deck.make(result))


def apply(match, seat, effect):
    if effect["pay"]:
        seat.pay(effect["pay"])
    if effect["gain"]:
        seat.gain(effect["gain"], food_cap(match, seat))
    if effect["card"]:
        inst = seat.deck.make(effect["card"])
        inst["temp"] = True
        seat.hand.append(inst)
    if effect["draw"]:
        seat.hand.extend(seat.deck.draw(effect["draw"]))


# --- discarding, population, end-of-turn builds ---------------------------------------------------

def discard(match, seat, inst):
    """inst has left the hand without being played."""
    if inst.get("temp"):
        return
    card = CARDS[inst["card"]]
    hit = card.get("discarded")
    if not hit:
        seat.deck.discard([inst])
        return
    if not hit["remove"]:
        seat.deck.discard([inst])
    if hit["add"]:
        seat.deck.add(hit["add"])
        match.note(f"{seat.name} discarded {card['name']}: {CARDS[hit['add']]['name']} joins their deck.", seat.pid)
    if hit["population"]:
        lose_population(match, seat, -hit["population"])


def lose_population(match, seat, n):
    for _ in range(n):
        if seat.population <= 0:
            break
        seat.population -= 1
        for pile in (seat.deck.discard_pile, seat.deck.draw_pile, seat.hand):
            villager = next((inst for inst in pile if inst["card"] == POPULATION_CARD), None)
            if villager is not None:
                pile.remove(villager)
                break
        match.note(f"{seat.name} lost 1 population to starvation.", seat.pid)


def complete(match, seat, adds=True):
    """Pending builds are built. adds=False (setup pieces) skips the cards they add."""
    for cell, plan in list(seat.pending.items()):
        structure = STRUCTURES[plan["inst"]["card"]]
        match.board.add(cell, structure["id"], seat.pid)
        seat.population += structure["on_build"]["population"]
        if adds:
            for index, add in enumerate(structure["on_build"]["add"]):
                if index not in plan["skip"]:
                    for _ in range(add["count"]):
                        seat.deck.add(add["card"])
        match.note(f"{seat.name} built a {structure['name']}.", seat.pid)
    seat.pending = {}
