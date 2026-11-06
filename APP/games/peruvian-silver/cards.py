"""Peruvian Silver: loading the card files (cards/) when the game is imported.

What the files mean is documented in cards/README.md. Bad files are logged (logger
"peruvian-silver") and skipped, so one broken card never takes the game down.

Loaded once, here:
    HAND_CARDS     {id: card}   cards/hand/*.json, sorted by "order"
    DECK_CARDS     {id: card}   cards/deck/*.json
    STARTING_DECK  {deck card id: copies}   cards/starting-deck.json
    POOL           {deck card id: weight}   cards/pool.json (what a Red Gem can add)
    MARKS          [emoji]      cards/marks.json

The load_* functions take a folder or file so tests can feed them temporary files.
A new card `type` needs a name in DECK_TYPES / HAND_TYPES here and code in server.py.
"""

import logging
import random
from pathlib import Path

from gamekit.data import ID, flag, load_json, load_json_dir, text, whole

log = logging.getLogger("peruvian-silver")

CARDS_DIR = Path(__file__).resolve().parent / "cards"
DECK_TYPES = {
    "treasure", "hazard", "charm", "idol", "relic", "mirror", "gremlin", "fountain", "pot", "fork",
    "altar", "blessing", "death", "robbery", "gem",
}
HAND_TYPES = {"stay", "leave", "flee", "stash", "guard", "return", "backstab", "peek"}
GEM_COLORS = {"red", "blue"}
MARK_CHOICES = 3  # emoji drawn from the mark pool each marking round (the same for everyone)


def _id_field(data, key, default, message):
    value = data.get(key, default)
    if not isinstance(value, str) or not ID.match(value):
        raise ValueError(message)
    return value


def _common(card_id, data, types):
    kind = data.get("type")
    if kind not in types:
        raise ValueError(f"type must be one of {sorted(types)}")
    return {
        "id": card_id,
        "name": text(data, "name", 40, required=True),
        "type": kind,
        "icon": text(data, "icon", 8),
        "text": text(data, "text", 300),
    }


def load_hand_cards(folder):
    """cards/hand: {id: card}, sorted by (order, id)."""

    def parse(card_id, data):
        card = _common(card_id, data, HAND_TYPES)
        card["starting"] = whole(data, "starting", 0, 20, default=0)
        card["reusable"] = flag(data, "reusable")
        card["order"] = whole(data, "order", 0, 1000, default=100)
        return card

    cards = load_json_dir(folder, parse, log)
    return dict(sorted(cards.items(), key=lambda item: (item[1]["order"], item[0])))


def load_deck_cards(folder, hand_cards):
    """cards/deck: {id: card}. A relic's "gives" must be in hand_cards; a charm must protect a hazard card."""

    def parse(card_id, data):
        card = _common(card_id, data, DECK_TYPES)
        kind = card["type"]
        card["back"] = _id_field(data, "back", "default", "back must be lowercase letters, digits, - or _")
        card["blackSquare"] = flag(data, "blackSquare")
        if kind in ("treasure", "idol"):
            card["value"] = whole(data, "value", 0, 1000)
        if kind == "charm":
            card["protects"] = _id_field(data, "protects", None, "protects must be the id of a hazard card")
        if kind == "relic":
            gives = data.get("gives")
            if gives not in hand_cards:
                raise ValueError("gives must be the id of a card in cards/hand")
            card["gives"] = gives
        if kind == "gem":
            color = data.get("color")
            if color not in GEM_COLORS:
                raise ValueError(f"color must be one of {sorted(GEM_COLORS)}")
            card["color"] = color
        if kind == "pot":
            card["growth"] = whole(data, "growth", 0, 1000, default=5)
        return card

    cards = load_json_dir(folder, parse, log)
    for card_id, card in list(cards.items()):
        if card["type"] == "charm" and cards.get(card["protects"], {}).get("type") != "hazard":
            log.error("Skipping card %s: protects %r, which isn't a hazard card", card_id, card["protects"])
            del cards[card_id]
    return cards


def load_counts(path, deck_cards, label, high):
    """Read {"<deck card id>": number, ...}. Unknown ids and bad numbers are logged and skipped."""

    def parse(data):
        if not isinstance(data, dict):
            raise ValueError("must be a JSON object")
        counts = {}
        for card_id, count in data.items():
            if card_id not in deck_cards:
                log.error("%s: no card %r in cards/deck, skipped", path.name, card_id)
            elif type(count) is not int or not 0 <= count <= high:
                log.error("%s: %s for %r must be a whole number from 0 to %d, skipped", path.name, label, card_id, high)
            elif count:
                counts[card_id] = count
        return counts

    return load_json(path, parse, log, default={})


def load_marks(path):
    """The emoji pool players mark cards with: {"emoji": ["🔺", ...]} (at least MARK_CHOICES)."""

    def parse(data):
        marks = data.get("emoji") if isinstance(data, dict) else None
        if not isinstance(marks, list) or not all(isinstance(m, str) and 0 < len(m) <= 8 for m in marks):
            raise ValueError('needs {"emoji": ["...", ...]}')
        marks = list(dict.fromkeys(marks))
        if len(marks) < MARK_CHOICES:
            raise ValueError(f"needs at least {MARK_CHOICES} different emoji")
        return marks

    return load_json(path, parse, log, default=[])


HAND_CARDS = load_hand_cards(CARDS_DIR / "hand")
DECK_CARDS = load_deck_cards(CARDS_DIR / "deck", HAND_CARDS)
STARTING_DECK = load_counts(CARDS_DIR / "starting-deck.json", DECK_CARDS, "copies", 50)
POOL = load_counts(CARDS_DIR / "pool.json", DECK_CARDS, "weight", 1000)  # what a Red Gem can add
MARKS = load_marks(CARDS_DIR / "marks.json")


def random_pool_cards(count):
    """Up to `count` different pool cards, picked by weight."""
    weights = dict(POOL)
    picked = []
    while weights and len(picked) < count:
        card_id = random.choices(list(weights), weights=list(weights.values()))[0]
        picked.append(card_id)
        del weights[card_id]
    return picked
