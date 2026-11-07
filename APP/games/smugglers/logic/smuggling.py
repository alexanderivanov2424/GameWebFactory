"""Smugglers: what smugglers do with their ships (move, pick up and load cargo, deliver).

Every function takes the Match `m` and a smuggler's public id, checks the rules (raising
LobbyError) and changes m. Turn checks (whose turn, pending inspection) happen in Match.

    move(m, pid, ship_id, to)            one ship action: up to the ship's speed
    pickup(m, pid, ship_id, contract_id) one ship action: draw 5 goods; then load(...)
    load(m, pid, load_uids, discard_uids, declare)
                                         finish a pickup: cards onto the ship, declared good,
                                         discard down to HAND_LIMIT; the cargo token moves on
    deliver(m, pid, ship_id)             free: complete the ship's contract at its destination
    payout(cards, contract, goods)       credits for a cargo (see the function)
    reach(m, ship)                       {node: True if it must stop there} for a move: a
                                         loaded ship stops on a patrol's or checkpoint's spot
    pickups(m, ship)                     contract ids the ship could pick up where it is
    can_deliver(m, ship) / can_act(m, ship)
"""

from collections import Counter

from gamekit import LobbyError

from . import inspection
from .content import legal_goods

PICKUP_DRAW = 5
HAND_LIMIT = 5


def own_ship(m, pid, ship_id):
    ship = m.ships.get(ship_id)
    if ship is None or ship["owner"] != pid:
        raise LobbyError("That's not one of your ships.")
    return ship


def ready_ship(ship):
    if ship["acted"]:
        raise LobbyError(f"{ship['name']} has already acted this turn.")


def reach(m, ship):
    stops = m.interpol.nodes("checkpoint") | m.interpol.nodes("patrol") if ship["cargo"] else set()
    found = m.board.reach(ship["at"], ship["speed"], blocked=m.interpol.nodes("barrier"), stops=stops)
    return {node: node in stops for node in found}


def pickups(m, ship):
    if ship["cargo"] or ship.get("contract"):
        return []
    return [cid for cid in m.row if cid not in m.holder and m.contracts[cid]["from"] == ship["at"]]


def can_deliver(m, ship):
    cid = ship.get("contract")
    return cid is not None and m.contracts[cid]["to"] == ship["at"]


def can_act(m, ship):
    return not ship["acted"] and (bool(reach(m, ship)) or bool(pickups(m, ship)))


def move(m, pid, ship_id, to):
    ship = own_ship(m, pid, ship_id)
    ready_ship(ship)
    options = reach(m, ship)
    if to not in options:
        raise LobbyError(f"{ship['name']} can't reach there this turn.")
    ship["at"] = to
    ship["acted"] = True
    m.add_log(pid, f"{m.names[pid]} flew {ship['name']} to {m.label(to)}.")
    inspection.check(m, [ship_id])


def pickup(m, pid, ship_id, contract_id):
    ship = own_ship(m, pid, ship_id)
    ready_ship(ship)
    if ship["cargo"] or ship.get("contract"):
        raise LobbyError(f"{ship['name']} already carries cargo: deliver it first.")
    if contract_id not in pickups(m, ship):
        raise LobbyError("There's no cargo for that contract here.")
    ship["acted"] = True
    drawn = m.goods.draw(PICKUP_DRAW)
    m.smugglers[pid]["hand"].extend(drawn)
    m.loading = {"pid": pid, "ship": ship_id, "contract": contract_id}
    m.add_log(pid, f"{m.names[pid]} is loading cargo #{m.number(contract_id)} onto {ship['name']} "
                   f"at {m.label(ship['at'])} (drew {len(drawn)}).")


def load(m, pid, load_uids, discard_uids, declare):
    loading = m.loading
    if loading is None or loading["pid"] != pid:
        raise LobbyError("You're not loading cargo.")
    hand = m.smugglers[pid]["hand"]
    by_uid = {card["uid"]: card for card in hand}
    chosen = list(load_uids) + list(discard_uids)
    if len(set(chosen)) != len(chosen) or any(uid not in by_uid for uid in chosen):
        raise LobbyError("Pick cards from your hand, each one only once.")
    if not load_uids:
        raise LobbyError("Load at least one card onto the ship.")
    if declare not in legal_goods(m.goods_defs):
        raise LobbyError("Declare one of the legal goods.")
    must_discard = max(0, len(hand) - len(load_uids) - HAND_LIMIT)
    if len(discard_uids) != must_discard:
        raise LobbyError(f"Discard exactly {must_discard} card{'s' if must_discard != 1 else ''} "
                         f"to keep {HAND_LIMIT} in hand." if must_discard else
                         "You don't need to discard: your hand isn't over the limit.")
    ship = m.ships[loading["ship"]]
    ship["cargo"] = [by_uid[uid] for uid in load_uids]
    ship["declared"] = declare
    ship["contract"] = loading["contract"]
    m.holder[loading["contract"]] = ship["id"]
    m.goods.discard(by_uid[uid] for uid in discard_uids)
    m.smugglers[pid]["hand"] = [card for card in hand if card["uid"] not in chosen]
    m.loading = None
    m.add_log(pid, f"{m.names[pid]} loaded {len(load_uids)} goods onto {ship['name']}, "
                   f"declared as {m.goods_defs[declare]['name']}.")
    inspection.check(m, [ship["id"]])  # loading on a patrol's or checkpoint's spot


def payout(cards, contract, goods):
    """Credits for delivering `cards` on `contract`: the largest set of one legal good (ties:
    the one paying most) pays its value per card, +contract bonus if it's the contract's good;
    every illegal good pays its own value."""
    counts = Counter(card["card"] for card in cards if goods[card["card"]]["legal"])
    best, best_key = None, None
    for good, count in counts.items():
        bonus = contract["bonus"] if good == contract["good"] else 0
        key = (count, count * goods[good]["value"] + bonus)
        if best_key is None or key > best_key:
            best, best_key = good, key
    base = counts[best] * goods[best]["value"] if best else 0
    bonus = contract["bonus"] if best == contract["good"] else 0
    illegal = sum(goods[card["card"]]["value"] for card in cards if not goods[card["card"]]["legal"])
    return {"set": best, "count": counts[best] if best else 0, "base": base, "bonus": bonus,
            "illegal": illegal, "total": base + bonus + illegal}


def deliver(m, pid, ship_id):
    ship = own_ship(m, pid, ship_id)
    if not can_deliver(m, ship):
        raise LobbyError(f"{ship['name']} isn't at its contract's destination.")
    cid = ship["contract"]
    contract = m.contracts[cid]
    paid = payout(ship["cargo"], contract, m.goods_defs)
    m.smugglers[pid]["credits"] += paid["total"]
    cards = [card["card"] for card in ship["cargo"]]
    m.goods.discard(ship["cargo"])
    m.clear_cargo(ship)
    m.holder.pop(cid, None)
    m.row.remove(cid)
    m.done.append(cid)
    parts = []
    if paid["set"]:
        parts.append(f"{paid['count']} × {m.goods_defs[paid['set']]['name']} = {paid['base']}")
    if paid["bonus"]:
        parts.append(f"contract bonus +{paid['bonus']}")
    if paid["illegal"]:
        parts.append(f"contraband +{paid['illegal']}")
    m.add_log(pid, f"{m.names[pid]} delivered contract #{m.number(cid)} at {m.label(ship['at'])} for "
                   f"{paid['total']} credits ({', '.join(parts) or 'nothing usable'}).", cards=cards)
    m.reveal_contracts()
