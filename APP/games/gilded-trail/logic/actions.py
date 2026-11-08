"""Gilded Trail: buying cards and playing action cards (and the choices they wait for).

    coins(card_def)              what a card pays toward a purchase
    buy(m, pid, card_id, uids)   pay with cards from hand, gain card_id on the discard pile
    play(m, pid, uid)            play an action card; may leave m.pending set (see below)
    trash(m, pid, uids)          pending "remove": remove up to N cards in hand from the game
    take(m, pid, card_id)        pending "free": gain any card (None = skip)
    guide(m, pid, ei, to)        pending "guide": step (None = skip)

Rules:
- One purchase per turn. Coin cards and jokers pay their value; every other card (machete,
  paddle, action) pays 1/2. Unused coins are lost. Bought cards go to the discard pile.
- Paying: single-use coin cards and jokers (Gold Cache, Airship) are removed from the game,
  because they were used for their value; anything else goes to the discard pile.
- Action cards go to the discard pile when played (single-use ones are removed). Effects
  (cards/*.json "effect"): draw N; then remove up to N cards in hand; free = take any card
  from the market or reserve (not a purchase); guide = the Local Guide's step
  (movement.guide). While a choice is pending, nothing else can be done.
"""

from gamekit import LobbyError

from . import movement


def coins(card_def):
    return card_def["value"] if card_def["kind"] in ("coin", "joker") else 0.5


def buy(m, pid, card_id, uids):
    if m.bought:
        raise LobbyError("You can only buy one card per turn.")
    reason = m.market.available(card_id)
    if reason:
        raise LobbyError(reason)
    if len(set(uids)) != len(uids) or not uids:
        raise LobbyError("Choose the cards to pay with.")
    offered = [m.hand_card(pid, uid) for uid in uids]
    total = sum(coins(m.cards[c["card"]]) for c in offered)
    cost = m.cards[card_id]["cost"]
    if total < cost:
        raise LobbyError(f"{m.card_name(card_id)} costs {cost}; those cards pay {fmt(total)}.")
    m.take_from_hand(pid, uids)
    for card in offered:
        m.use_card(pid, card, single_removed=m.cards[card["card"]]["kind"] in ("coin", "joker"))
    m.market.gain(card_id)
    m.players[pid]["deck"].add(card_id)
    m.bought = True
    m.add_log(pid, f"{m.names[pid]} bought {m.card_name(card_id)} for {fmt(total)}.")


def play(m, pid, uid):
    card = m.hand_card(pid, uid)
    definition = m.cards[card["card"]]
    if definition["kind"] != "action":
        raise LobbyError("Only action cards are played on their own.")
    effect = definition["effect"]
    if effect.get("guide") and not any(movement.guide_targets(m, pid).values()):
        raise LobbyError("None of your explorers has a space to step to.")
    m.take_from_hand(pid, [uid])
    m.add_log(pid, f"{m.names[pid]} played {definition['name']}.")
    m.use_card(pid, card, single_removed=True, quiet=True)
    if effect.get("draw"):
        m.draw(pid, effect["draw"])
    if effect.get("remove"):
        m.pending = {"kind": "remove", "max": effect["remove"]}
    elif effect.get("free"):
        m.pending = {"kind": "free"}
    elif effect.get("guide"):
        m.pending = {"kind": "guide"}


def require_pending(m, kind):
    if not m.pending or m.pending["kind"] != kind:
        raise LobbyError("There's nothing like that to choose now.")


def trash(m, pid, uids):
    require_pending(m, "remove")
    if len(uids) > m.pending["max"] or len(set(uids)) != len(uids):
        raise LobbyError(f"Remove at most {m.pending['max']} card{'s' if m.pending['max'] > 1 else ''}.")
    cards = m.take_from_hand(pid, uids)
    m.players[pid]["removed"].extend(cards)
    if cards:
        m.add_log(pid, f"{m.names[pid]} removed {', '.join(m.card_name(c['card']) for c in cards)} from the game.")
    m.pending = None


def take(m, pid, card_id):
    require_pending(m, "free")
    if card_id is not None:
        m.market.check(card_id)
        m.market.gain(card_id, bought=False)
        m.players[pid]["deck"].add(card_id)
        m.add_log(pid, f"{m.names[pid]} took {m.card_name(card_id)} for free.")
    m.pending = None


def guide(m, pid, ei, to):
    require_pending(m, "guide")
    if to is not None:
        movement.guide(m, pid, ei, to)
    m.pending = None


def fmt(value):
    whole = int(value)
    return f"{whole or ''}½" if value != whole else str(whole)
