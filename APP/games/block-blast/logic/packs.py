"""Block Blast: card packs, the sets of bonus cards the market (market/) is dealt from. The host
picks which packs go into the pool (the "packs" setting, built in server.py from PACKS).

One file per pack in cards/packs/<id>.json (fields in cards/README.md); bad files are logged
(logger "block-blast") and skipped, unknown cards in a pack are logged and left out.

    PACKS                  {pack id: {"id", "name", "description", "cards": {card id: copies}}},
                           in file name order (the lobby's order)
    pool(selected, packs)  [card id, ...]: every copy of every card in the selected packs (a card
                           in two packs counts in both)
"""

from gamekit.data import load_json_dir, text

from .cards import CARDS, CARDS_DIR, deck_ids, log, parse_counts


def parse_pack(pack_id, data, cards):
    counts = parse_counts(data.get("cards"), cards, f"pack {pack_id}")
    if not counts:
        raise ValueError("needs at least one card")
    return {
        "id": pack_id,
        "name": text(data, "name", 30, required=True),
        "description": text(data, "description", 200),
        "cards": counts,
    }


def load_packs(folder, cards):
    return load_json_dir(folder, lambda pack_id, data: parse_pack(pack_id, data, cards), log)


def pool(selected, packs):
    return [card_id for pack_id in selected for card_id in deck_ids(packs[pack_id]["cards"])]


PACKS = load_packs(CARDS_DIR / "packs", CARDS)
