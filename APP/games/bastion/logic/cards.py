"""Bastion: the cards, loaded when the game is imported: content/cards/*.json (actions and enemy
curses) plus a blueprint made from every structure file that has a price (structures.py):
    "plan-<id>"  the blueprint (kind "build"), sold for the structure's "price" in bundles of its
                 "bundle" copies; building it removes the card from the deck (roads and walls
                 have no blueprint: tiles.py)
Working buildings, hauling and fighting are done by units (units.py), never by cards.
Fields are documented in content/README.md. Bad files are logged (logger "bastion") and skipped.

    CARDS   {id: card}, card = {
        "id", "name", "kind": "build" | "action" | "curse", "text" (generated unless given),
        "price":    gold in the market (None: never sold)
        "bundle":   copies one purchase adds (blueprints: the structure's bundle; others 1)
        "structure": what a build card builds
        "cost":     {resource: n} paid when an action is played
        "repair":   repair one damaged structure (a target; 1 wood per ruined tile)
        "cure":     cure one plagued structure (a target)
        "gain":     {resource or "soldiers": n}
        "draw":     draw n cards
        "adds":     card id put in the player's discard pile when played (Tax: Unrest)
        "trash":    remove up to n other cards in the hand from the deck for good (not curses);
                    the play message lists them ("remove")
        "pay":      curse: {resource: n} to play it, which removes it from the deck
        "hurts":    curse: playing it deals 1 damage to the enemy that sent it }
    targeted(card)   whether playing it needs a structure picked on the board
    STARTING_DECK    {card id: copies} (content/starting-deck.json)
    load_cards(folder, structures) / load_counts(path, cards)   (tests feed temporary files)
"""

import logging

from gamekit.data import flag, load_json, load_json_dir, text, whole

from .structures import CONTENT, OUTPUT_NAMES, RESOURCE_IDS, STRUCTURES, a, amounts

log = logging.getLogger("bastion")

KINDS = ("action", "curse")
REPAIR_COST = "wood"  # 1 per ruined tile


def amount_text(values):
    return ", ".join(f"{n} {OUTPUT_NAMES.get(k, k)[:-1] if k in ('soldiers', 'tools') and n == 1 else OUTPUT_NAMES.get(k, k)}"
                     for k, n in values.items())


def card_text(card, structures):
    if card["kind"] == "build":
        s = structures[card["structure"]]
        cost = f" for {amount_text(s['cost'])}" if s["cost"] else ""
        return f"Build {a(s['name'])}{cost}. Leaves your deck once built."
    if card["kind"] == "curse":
        hurt = " and deal 1 damage to its sender" if card["hurts"] else ""
        return f"Pay {amount_text(card['pay'])} to remove this card from your deck{hurt}."
    parts = []
    if card["cost"]:
        parts.append(f"Pay {amount_text(card['cost'])}:")
    if card["repair"]:
        parts.append("Repair a damaged structure (1 wood per tile).")
    if card["cure"]:
        parts.append("Cure a plagued building.")
    if card["gain"]:
        parts.append(f"Gain {amount_text(card['gain'])}.")
    if card["draw"]:
        parts.append(f"Draw {card['draw']} card{'s' if card['draw'] > 1 else ''}.")
    if card["trash"]:
        parts.append(f"Remove up to {card['trash']} other card{'s' if card['trash'] > 1 else ''} in your hand "
                     f"from your deck for good (not curses).")
    if card["adds"]:
        parts.append(f"Adds {a(card['adds'])} card to your discard pile.")
    if card["cost"] and len(parts) > 1:
        parts[1] = parts[1][0].lower() + parts[1][1:]
    return " ".join(parts)


def blank(card_id, name, kind):
    return {"id": card_id, "name": name, "kind": kind, "text": "", "price": None, "bundle": 1, "structure": None,
            "cost": {}, "repair": False, "cure": False, "gain": {}, "draw": 0,
            "adds": None, "trash": 0, "pay": {}, "hurts": False}


def parse_card(card_id, data, structures):
    kind = data.get("kind", "action")
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    card = blank(card_id, text(data, "name", 30, required=True), kind)
    card["price"] = whole(data, "price", 0, 30) if "price" in data else None
    if kind == "curse":
        card["pay"] = amounts(data, "pay", RESOURCE_IDS)
        card["hurts"] = flag(data, "hurts")
    else:
        card.update(
            cost=amounts(data, "cost", RESOURCE_IDS), repair=flag(data, "repair"), cure=flag(data, "cure"),
            gain=amounts(data, "gain", RESOURCE_IDS + ["soldiers"]), draw=whole(data, "draw", 0, 5, default=0),
            trash=whole(data, "trash", 0, 5, default=0), adds=data.get("adds"))
        if card["adds"] is not None and not isinstance(card["adds"], str):
            raise ValueError("adds must be a card id")
        if card["repair"] and card["cure"]:
            raise ValueError("a card may target only one way (repair or cure)")
    card["text"] = text(data, "text", 200) or card_text(card, structures)
    return card


def structure_cards(structures):
    cards = {}
    for sid, s in structures.items():
        if s["price"] is not None:
            card = blank(f"plan-{sid}", s["name"], "build")
            card.update(price=s["price"], structure=sid, bundle=s["bundle"])
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
    for sid, s in structures.items():
        if s["card"] and s["card"] not in cards:
            log.error("Structure %s gives unknown card %s", sid, s["card"])
            s["card"] = None
    return cards


def targeted(card):
    return bool(card["repair"] or card["cure"])


def load_counts(path, cards):
    def parse(data):
        if not isinstance(data, dict) or any(k not in cards for k in data):
            raise ValueError(f"must map known card ids to copies: {sorted(set(data) - set(cards))}")
        return {k: whole(data, k, 1, 10) for k in data}
    return load_json(path, parse, log, default={})


def public(card):
    view = {k: card[k] for k in ("name", "kind", "text", "price", "bundle", "structure", "cost", "pay", "hurts", "trash")}
    return {k: v for k, v in view.items() if v is not None} | {"targeted": targeted(card)}  # PatchState: no nulls


CARDS = load_cards(CONTENT / "cards", STRUCTURES)
STARTING_DECK = load_counts(CONTENT / "starting-deck.json", CARDS)
