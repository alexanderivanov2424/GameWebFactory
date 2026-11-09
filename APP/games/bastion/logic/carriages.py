"""Bastion: carriages, the goods a haul card is carrying along the roads (pure rules on a Board).

A haul card (Haul, Wagon Train, or Villagers played as a haul) is played on a building holding
goods: a carriage loads everything stored there and the card leaves its player's deck while it
travels. At the end of every round, before the enemies attack, each carriage moves the card's
`haul` value in cells: first onto the building's road tile nearest a depot, then along the roads
(board.road_distances) and into the depot (that step counts too). On arrival its goods join the
stockpile and the card goes back to its player's discard pile. A building next to a depot is
already there: hauling from it delivers at once and the card is discarded as usual. A carriage
whose roads no longer reach a depot waits where it is.

Carriages on road tiles can be looted unless the tile is protected (next to a wall or within a
watchtower's reach); a carriage that loses everything turns back (its card returns at once).
A road tile with a carriage on it can't be built over.

    Carriage(uid, owner, card, speed, goods, cells, name)   cell None: still at its building
    why_not(board, structure) -> reason nothing can be hauled from it, or None
    load(board, structure, owner, card, speed) -> Carriage, its goods taken from the building
    move(board, carriage, dist) -> True when it reached a depot (dist = board.road_distances())
    at_depot(board, cells)      whether goods in those cells are already at a depot
    steps(board, cells, dist)   cells to travel from that building (0: at a depot; None: cut off)
    view(board, carriage) -> public dict for clients
With the match (shared stockpile, seats, log):
    send(match, seat, instance, card, structure) -> log text   play a haul on that building
    move_all(match)            end of round: every carriage moves; arrivals deliver
    deliver(match, carriage) / return_card(match, carriage)   goods to the stockpile / card home
"""

from dataclasses import dataclass

from .cards import CARDS, amount_text


@dataclass
class Carriage:
    uid: int
    owner: str  # pid of the player whose card it is
    card: dict  # the card instance, back to its owner on arrival
    speed: int  # cells a round
    goods: dict
    cells: list  # the building it loaded at
    name: str  # that building's name
    cell: tuple = None  # the road cell it is on (None: still at the building)

    def where(self):
        return self.cell or min(self.cells, key=lambda c: (c[1], c[0]))


def at_depot(board, cells):
    return bool(board.neighbors(cells) & board.depot_cells() or set(cells) & board.depot_cells())


def steps(board, cells, dist):
    """Cells a carriage loaded at those building cells travels to a depot (0: already there), or
    None when no road from it reaches one."""
    if at_depot(board, cells):
        return 0
    roads = [dist[r] for r in board.neighbors(cells) if r in dist]
    return min(roads) + 1 if roads else None


def why_not(board, s):
    if not s.stored():
        return f"That {s.spec['name']} has no goods waiting."
    if not board.link(s):
        return f"That {s.spec['name']} is cut off: link it to the keep or a storage yard by road."
    return None


def load(board, s, owner, card, speed):
    carriage = Carriage(board.next_carriage, owner, card, speed, dict(s.store), list(s.cells), s.spec["name"])
    board.next_carriage += 1
    s.store.clear()
    board.version += 1
    return carriage


def move(board, c, dist):
    for _ in range(c.speed):
        if c.cell is None:
            if at_depot(board, c.cells):
                return True
            roads = sorted((r for r in board.neighbors(c.cells) if r in dist), key=lambda r: (dist[r], r))
            if not roads:
                return False
            c.cell = roads[0]
        elif c.cell not in dist:
            return False
        elif dist[c.cell] == 1:
            return True
        else:
            c.cell = board.toward_depot(c.cell, dist)
    return False


def view(board, c):
    x, y = c.where()
    return {"x": x, "y": y, "owner": c.owner, "card": c.card["card"], "speed": c.speed, "goods": dict(c.goods),
            "from": c.name, "road": c.cell is not None, "safe": c.cell is None or board.protected(c.cell)}


def send(match, seat, instance, card, s):
    carriage = load(match.board, s, seat.pid, instance, card["haul"])
    if at_depot(match.board, carriage.cells):
        deliver(match, carriage)
        return f"hauled {amount_text(carriage.goods)} from the {s.spec['name']} to the stockpile"
    match.board.carriages[carriage.uid] = carriage
    return (f"loaded {amount_text(carriage.goods)} at the {s.spec['name']} onto a carriage "
            f"({card['haul']} cell{'s' if card['haul'] > 1 else ''} a round)")


def return_card(match, c):
    """c is done (arrived or emptied): its card goes back to its owner's discard pile."""
    match.board.carriages.pop(c.uid, None)
    match.board.version += 1
    seat = match.seats.get(c.owner)
    if seat:
        seat.deck.discard([c.card])


def deliver(match, c):
    for k, n in c.goods.items():
        match.stock[k] += n
    return_card(match, c)


def move_all(match):
    dist = match.board.road_distances()
    for c in list(match.board.carriages.values()):
        if move(match.board, c, dist):
            deliver(match, c)
            card = CARDS[c.card["card"]]["name"]
            match.write(f"{match.names[c.owner]}'s {card} delivered {amount_text(c.goods)} from the {c.name}.", c.owner)
    match.board.version += 1
