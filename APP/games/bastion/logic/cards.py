"""Bastion: the cards, loaded when the game is imported: content/cards/*.json (actions and curses)
plus a blueprint made from every structure file that has a price (structures.py):
    "plan-<id>"  the blueprint (kind "build"), sold for the structure's "price"; playing it plans
                 the structure on the board (greyed out with its build tokens) and removes the
                 card from the deck
Fields are documented in content/README.md. Bad files are logged (logger "bastion") and skipped.

    CARDS   {id: card}, card = {
        "id", "name", "kind": "build" | "action" | "curse", "text" (generated unless given),
        "price":     gold in the market (None: never sold). Blueprints sit in the market's
                     blueprint half, actions in its action half (market.py)
        "structure": what a build card plans
        "cost":      {resource or "decrees": n} paid when played (blueprints: the structure's cost)
        "gain":      {resource: n}
        "draw":      draw n cards
        "adds":      card id put in the player's discard pile when played (Tax: Unrest)
        "recall":    Orders: one of your units stationed on a building goes back to your pool
                     (a target: the building)
        "trade":     Trade: give another player 3 different resources or 2 of the same one
                     (the play message names the player and the gift)
        "pay":       curse: {resource or "decrees": n} to play it, which removes it from the deck
        "hurts":     curse: playing it deals 1 damage to the enemy that sent it (dormant enemies) }
    price_of(card)   what playing it costs (cost or pay)
    targeted(card)   whether playing it needs a building picked on the board
    STARTING_DECK    {card id: copies} (content/starting-deck.json)
    load_cards(folder, structures) / load_counts(path, cards)   (tests feed temporary files)
"""

import logging

from gamekit.data import flag, load_json, load_json_dir, text, whole

from .structures import CONTENT, COST_KEYS, OUTPUT_NAMES, RESOURCE_IDS, STRUCTURES, a, amounts

log = logging.getLogger("bastion")

KINDS = ("action", "curse")


def amount_text(values):
    def name(k, n):
        word = OUTPUT_NAMES.get(k, k)
        if n == 1 and k in ("soldiers", "tools", "decrees"):
            word = word[:-1]
        return word
    return ", ".join(f"{n} {name(k, n)}" for k, n in values.items())


def card_text(card, structures):
    if card["kind"] == "build":
        s = structures[card["structure"]]
        turns = s["build"]
        when = f"{turns} build turn{'s' if turns != 1 else ''}" if turns else "built at once"
        return f"Plan {a(s['name'])} ({when}). {s['text']}"
    if card["kind"] == "curse":
        hurt = " and deal 1 damage to its sender" if card["hurts"] else ""
        return f"Pay to remove this card from your deck{hurt}."
    parts = []
    if card["gain"]:
        parts.append(f"Gain {amount_text(card['gain'])}.")
    if card["draw"]:
        parts.append(f"Draw {card['draw']} card{'s' if card['draw'] > 1 else ''}.")
    if card["recall"]:
        parts.append("One of your units on a building goes back to your pool (for the next round).")
    if card["trade"]:
        parts.append("Give another player 3 different resources or 2 of the same resource.")
    if card["adds"]:
        parts.append(f"Adds {a(card['adds'])} card to your discard pile.")
    return " ".join(parts)


def blank(card_id, name, kind):
    return {"id": card_id, "name": name, "kind": kind, "text": "", "price": None, "structure": None,
            "cost": {}, "gain": {}, "draw": 0, "adds": None, "recall": False, "trade": False,
            "pay": {}, "hurts": False}


def parse_card(card_id, data, structures):
    kind = data.get("kind", "action")
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    card = blank(card_id, text(data, "name", 30, required=True), kind)
    card["price"] = whole(data, "price", 0, 30) if "price" in data else None
    if kind == "curse":
        card["pay"] = amounts(data, "pay", COST_KEYS)
        card["hurts"] = flag(data, "hurts")
    else:
        card.update(
            cost=amounts(data, "cost", COST_KEYS), gain=amounts(data, "gain", RESOURCE_IDS),
            draw=whole(data, "draw", 0, 5, default=0), adds=data.get("adds"),
            recall=flag(data, "recall"), trade=flag(data, "trade"))
        if card["adds"] is not None and not isinstance(card["adds"], str):
            raise ValueError("adds must be a card id")
        if card["recall"] and card["trade"]:
            raise ValueError("a card may be either recall or trade")
    card["text"] = text(data, "text", 200) or card_text(card, structures)
    return card


def structure_cards(structures):
    cards = {}
    for sid, s in structures.items():
        if s["price"] is not None:
            card = blank(f"plan-{sid}", s["name"], "build")
            card.update(price=s["price"], structure=sid, cost=dict(s["cost"]))
            card["text"] = card_text(card, structures)
            cards[card["id"]] = card
    return cards


def check_adds(cards):
    """Card text names the added card, so it's filled in once every card is loaded."""
    for cid, card in list(cards.items()):
        if card["adds"] is None:
            continue
        if card["adds"] not in cards:
            log.error("Card %s adds unknown card %s", cid, card["adds"])
            del cards[cid]
        else:
            card["text"] = card["text"].replace(f"{a(card['adds'])} card", f"{a(cards[card['adds']]['name'])} card")
    return cards


def load_cards(folder, structures):
    cards = load_json_dir(folder, lambda cid, data: parse_card(cid, data, structures), log)
    check_adds(cards)
    cards.update(structure_cards(structures))
    return cards


def price_of(card):
    return card["pay"] if card["kind"] == "curse" else card["cost"]


def targeted(card):
    return bool(card["recall"])


def load_counts(path, cards):
    def parse(data):
        if not isinstance(data, dict) or any(k not in cards for k in data):
            raise ValueError(f"must map known card ids to copies: {sorted(set(data) - set(cards))}")
        return {k: whole(data, k, 1, 10) for k in data}
    return load_json(path, parse, log, default={})


def public(card):
    view = {k: card[k] for k in ("name", "kind", "text", "price", "structure", "cost", "pay", "trade", "recall")}
    view["price"] = card["price"] if card["price"] is not None else -1
    view["structure"] = card["structure"] or ""
    return view | {"targeted": targeted(card)}  # PatchState: no nulls


CARDS = load_cards(CONTENT / "cards", STRUCTURES)
STARTING_DECK = load_counts(CONTENT / "starting-deck.json", CARDS)
