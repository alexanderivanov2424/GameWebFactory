"""Bastion: the cards, loaded when the game is imported: content/cards/*.json (actions and enemy
curses) plus two cards made from every structure file (structures.py):
    "plan-<id>"  the blueprint (kind "build"), sold for the structure's "price"; building it
                 removes the card from the deck unless the structure is "reusable"
    "crew-<id>"  for buildings that work: "work a <structure>", added to the builder's deck
Fields are documented in content/README.md. Bad files are logged (logger "bastion") and skipped.

    CARDS   {id: card}, card = {
        "id", "name", "kind": "build" | "action" | "curse", "text" (generated unless given),
        "price":    gold in the market (None: never sold)
        "structure": what a build card builds; "keep": it stays in the deck when played
        "cost":     {resource: n} paid when an action is played
        "work":     None, "any" or [structure id]: work one such building (a target)
        "boost":    extra output for that work
        "unskilled": that work gets the base output and penalties but no bonuses (Villagers)
        "repair":   repair one damaged structure (a target; 1 wood per ruined tile)
        "cure":     cure one plagued structure (a target)
        "haul":     move up to n goods (+1 per population: cottages) from buildings and roads
                    towards a depot, each up to "reach" steps along roads (economy.haul)
        "reach":    how far a haul carries each good (cells)
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
    return ", ".join(f"{n} {'soldier' if k == 'soldiers' and n == 1 else OUTPUT_NAMES.get(k, k)}"
                     for k, n in values.items())


def card_text(card, structures):
    if card["kind"] == "build":
        s = structures[card["structure"]]
        cost = f" for {amount_text(s['cost'])}" if s["cost"] else ""
        stays = " Stays in your deck." if card["keep"] else " Leaves your deck once built."
        return f"Build {a(s['name'])}{cost}.{stays}"
    if card["kind"] == "curse":
        hurt = " and deal 1 damage to its sender" if card["hurts"] else ""
        return f"Pay {amount_text(card['pay'])} to remove this card from your deck{hurt}."
    parts = []
    if card["cost"]:
        parts.append(f"Pay {amount_text(card['cost'])}:")
    if card["work"] == "any":
        parts.append("Work any building")
    elif card["work"]:
        parts.append("Work " + " or ".join(a(structures[s]["name"]) for s in card["work"] if s in structures))
    if card["work"]:
        if card["unskilled"]:
            parts[-1] += " (base output: no bonuses)"
        parts[-1] += f" (+{card['boost']} output)." if card["boost"] else "."
    if card["repair"]:
        parts.append("Repair a damaged structure (1 wood per tile).")
    if card["cure"]:
        parts.append("Cure a plagued building.")
    if card["haul"]:
        parts.append(f"Haul up to {card['haul']} goods (+1 per cottage), each {card['reach']} cells along roads "
                     f"towards the keep or a storage yard.")
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
    return {"id": card_id, "name": name, "kind": kind, "text": "", "price": None, "structure": None, "keep": False,
            "cost": {}, "work": None, "boost": 0, "repair": False, "cure": False, "haul": 0, "reach": 0, "gain": {}, "draw": 0,
            "unskilled": False, "adds": None, "trash": 0, "pay": {}, "hurts": False}


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
        work = data.get("work")
        if work is not None and work != "any" and not (
                isinstance(work, list) and work and all(w in structures and structures[w]["work"] for w in work)):
            raise ValueError("work must be \"any\" or a list of structure ids that work")
        card.update(
            cost=amounts(data, "cost", RESOURCE_IDS), work=work, boost=whole(data, "boost", 0, 5, default=0),
            repair=flag(data, "repair"), cure=flag(data, "cure"), haul=whole(data, "haul", 0, 20, default=0),
            reach=whole(data, "reach", 1, 30, default=4), unskilled=flag(data, "unskilled"),
            gain=amounts(data, "gain", RESOURCE_IDS + ["soldiers"]), draw=whole(data, "draw", 0, 5, default=0),
            trash=whole(data, "trash", 0, 5, default=0), adds=data.get("adds"))
        if card["adds"] is not None and not isinstance(card["adds"], str):
            raise ValueError("adds must be a card id")
        if sum(1 for k in ("work", "repair", "cure") if card[k]) > 1:
            raise ValueError("a card may target only one way (work, repair or cure)")
    card["text"] = text(data, "text", 200) or card_text(card, structures)
    return card


def structure_cards(structures):
    cards = {}
    for sid, s in structures.items():
        if s["price"] is not None:
            card = blank(f"plan-{sid}", s["name"], "build")
            card.update(price=s["price"], structure=sid, keep=s["reusable"])
            card["text"] = card_text(card, structures)
            cards[card["id"]] = card
        if s["card"] == f"crew-{sid}":
            card = blank(s["card"], s["crew"], "action")
            card["work"] = [sid]
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
    return bool(card["work"] or card["repair"] or card["cure"])


def load_counts(path, cards):
    def parse(data):
        if not isinstance(data, dict) or any(k not in cards for k in data):
            raise ValueError(f"must map known card ids to copies: {sorted(set(data) - set(cards))}")
        return {k: whole(data, k, 1, 10) for k in data}
    return load_json(path, parse, log, default={})


def public(card):
    view = {k: card[k] for k in ("name", "kind", "text", "price", "structure", "keep", "cost", "pay", "hurts", "trash")}
    return {k: v for k, v in view.items() if v is not None} | {"targeted": targeted(card)}  # PatchState: no nulls


CARDS = load_cards(CONTENT / "cards", STRUCTURES)
STARTING_DECK = load_counts(CONTENT / "starting-deck.json", CARDS)
