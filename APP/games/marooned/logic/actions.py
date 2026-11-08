"""Marooned: day actions out on the island: move, explore (+ place), gather (+ report), search.

Each function takes the Match and the acting player's public id, checks the rules (raising
LobbyError), spends energy and applies the action. Turn and "someone is mid-action" checks
are the Match's job (match.py) before it calls these.

Two actions wait for a second message from the same player, kept in match.pending:
    explore -> {"kind": "explore", "player", "cell", "cards"}   then place(uid); the explorer
               steps onto the new square (exploring costs EXPLORE_COST instead of the move)
    gather  -> {"kind": "gather", "player", "item", "roll"}     then report(face)
The gather roll is secret: only the gatherer sees it, and they announce any face from 1 up
to what they really rolled (never better). They get what they announce.
"""

from gamekit import LobbyError

from .content import FINDS, TILES
from .island import tile_types
from .survivor import TOOLS

EXPLORE_COST = 1
EXPLORE_CHOICES = 2
GATHER_COST = 1
SEARCH_COST = 2
DIE = 6
GATHER_YIELD = {1: 0, 2: 1, 3: 1, 4: 2, 5: 2, 6: 3}   # face -> resources
TOOL_BONUS = {"wood": "axe", "stone": "axe", "food": "spear"}  # +1 on a success
MACHETE_TILES = ("jungle", "swamp")


def move_cost(m, survivor, cell):
    cost = m.island.move_cost(cell)
    if "machete" in survivor.tools and m.island.tile(cell)["type"] in MACHETE_TILES:
        cost = max(1, cost - 1)
    return cost


def move(m, pid, cell):
    s = m.people[pid]
    if not m.island.on_grid(cell) or not m.island.adjacent(s.pos, cell):
        raise LobbyError("You can only move to a square next to yours.")
    if m.island.tile(cell) is None:
        raise LobbyError("Explore that square before moving there.")
    s.spend(move_cost(m, s, cell))
    m.arrive(s, cell)


def explore(m, pid, cell):
    s = m.people[pid]
    if not m.island.adjacent(s.pos, cell) or not m.island.explorable(cell):
        raise LobbyError("You can only explore an unexplored square next to yours.")
    s.spend(EXPLORE_COST)
    cards = m.island.draw(EXPLORE_CHOICES)
    if not cards:
        s.energy += EXPLORE_COST
        raise LobbyError("There are no tiles left.")
    m.pending = {"kind": "explore", "player": pid, "cell": tuple(cell), "cards": cards}
    if len(cards) == 1:
        place(m, pid, cards[0]["uid"])


def place(m, pid, uid):
    pending = m.pending
    chosen = next((c for c in pending["cards"] if c["uid"] == uid), None)
    if chosen is None:
        raise LobbyError("Pick one of the tiles you drew.")
    m.pending = None
    m.island.bottom([c for c in pending["cards"] if c is not chosen])
    explored = m.island.place(pending["cell"], chosen["card"], pid)
    s = m.people[pid]
    m.arrive(s, pending["cell"])
    names = []
    for cell in explored:
        kind = TILES[m.island.tile(cell)["type"]]
        s.stats["explored"] += 1
        s.stats["explorePoints"] += kind["points"]
        names.append(kind["name"])
    m.log(f"{m.names[pid]} explored: {', '.join(names)}.")


def gather(m, pid, item):
    s = m.people[pid]
    if not m.island.available(s.pos, item):
        raise LobbyError("There's none of that here.")
    if not s.space():
        raise LobbyError("Your backpack is full.")
    s.spend(GATHER_COST)
    m.pending = {"kind": "gather", "player": pid, "item": item, "roll": m.rng.randint(1, DIE)}


def gather_yield(s, item, face):
    amount = GATHER_YIELD[face]
    if amount and TOOL_BONUS.get(item) in s.tools:
        amount += 1
    return amount


def report(m, pid, face):
    pending = m.pending
    if not 1 <= face <= pending["roll"]:
        raise LobbyError("You can't announce a better roll than you rolled.")
    m.pending = None
    s = m.people[pid]
    item = pending["item"]
    if face < pending["roll"]:
        s.stats["lies"] += 1
    wanted = min(gather_yield(s, item, face), s.space())
    got = m.island.take_resource(s.pos, item, wanted)
    s.add(item, got)
    outcome = f"+{got} {item}" if got else "nothing"
    m.log(f"{m.names[pid]} rolled a {face} gathering {item}: {outcome}.")


def search(m, pid):
    s = m.people[pid]
    tile = m.island.tile(s.pos)
    if not tile["searches"]:
        raise LobbyError("There's nothing left to search here.")
    if not FINDS:
        raise LobbyError("There's nothing to find.")
    s.spend(SEARCH_COST)
    cards = m.finds.draw(1)
    tile["searches"] -= 1
    find = FINDS[cards[0]["card"]]
    m.finds.discard(cards)
    for item, count in find["gives"].items():
        extra = count - s.add(item, count)
        if extra:  # no room: it's left on the ground
            pile = m.island.pile(s.pos)
            pile[item] = pile.get(item, 0) + extra
    if find["energy"] < 0:
        s.lose_energy(-find["energy"])
    else:
        s.energy += find["energy"]
    m.log(f"{m.names[pid]} searched the {tile_types()[tile['type']]['name']}: {find['name']}.")


def tool_rules():
    return {key: {"name": t["name"], "cost": dict(t["cost"]), "text": t["text"]} for key, t in TOOLS.items()}
