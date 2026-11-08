"""Bastion: what order cards do when played. Each stat of an order card is one effect, applied in
this order (cards.ORDER_STATS); a card may combine several:

    labor      +n labor for you this turn          draw       you draw n cards
    gold       +n gold for you                     keep       +n keep health (up to its maximum)
    repair     every wall regains n health (up to its maximum)
    teamLabor  +n labor for every other player     teamGold   +n gold for every other player
    teamDraw   every other player draws n cards    upgrade    raise the targeted structure 1 level

    apply_order(match, seat, card, x, y) -> list of short texts for the log
Targeted orders (upgrade) get the cell; Match checks the target first with check_target.
"""

from gamekit import LobbyError

from .cards import CARDS


def check_target(match, card, x, y):
    if card["stats"].get("upgrade"):
        if x is None:
            raise LobbyError(f"Pick a structure for {card['name']}.")
        structure = match.board.at(x, y) if match.board.map.inside(x, y) else None
        if not structure:
            raise LobbyError("Pick a structure to upgrade.")
        if structure.level >= CARDS[structure.card]["maxLevel"]:
            raise LobbyError("That structure is already at its highest level.")


def apply_order(match, seat, card, x=None, y=None):
    stats = card["stats"]
    notes = []
    others = [s for s in match.seats.values() if s is not seat]
    if stats.get("labor"):
        seat.labor += stats["labor"]
        notes.append(f"+{stats['labor']} labor")
    if stats.get("draw"):
        seat.draw(stats["draw"])
        notes.append(f"drew {stats['draw']}")
    if stats.get("gold"):
        seat.gold += stats["gold"]
        notes.append(f"+{stats['gold']} gold")
    if stats.get("keep"):
        before = match.keep
        match.keep = min(match.keep_max, match.keep + stats["keep"])
        notes.append(f"keep +{match.keep - before}")
    if stats.get("repair"):
        for wall in match.board.of_kind("wall"):
            wall.hp = min(wall.max_hp(), wall.hp + stats["repair"])
        notes.append("walls repaired")
    if stats.get("teamLabor"):
        for other in others:
            other.labor += stats["teamLabor"]
        notes.append(f"everyone else +{stats['teamLabor']} labor")
    if stats.get("teamGold"):
        for other in others:
            other.gold += stats["teamGold"]
        notes.append(f"everyone else +{stats['teamGold']} gold")
    if stats.get("teamDraw"):
        for other in others:
            other.draw(stats["teamDraw"])
        notes.append(f"everyone else drew {stats['teamDraw']}")
    if stats.get("upgrade"):
        structure = match.board.upgrade(x, y)
        notes.append(f"{CARDS[structure.card]['name']} to level {structure.level}")
    return notes
