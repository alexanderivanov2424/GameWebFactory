"""Bastion: the city's people and feeding them (pure rules; Match calls upkeep at the end of a round).

Population = the "population" of every structure on the board (houses, the keep; ruined ones
still house people). At the end of every round, before the enemies attack, the city eats from
the stockpile: each bread feeds FEEDS["bread"] people and each wheat FEEDS["wheat"]. It eats the
least food that covers everyone (a leftover person still costs a whole wheat), preferring bread
on a tie. People left uncovered are hungry: next round's units are population - hungry.

    population(board) -> people living in the city
    feed(people, stock) -> {"bread": b, "wheat": w, "hungry": h}   what upkeep would eat (stock untouched)
    upkeep(people, stock) -> the same, taken from the stock
"""

FEEDS = {"bread": 4, "wheat": 2}  # people one unit of each food feeds (tune)


def population(board):
    return sum(s.spec["population"] for s in board.structures.values())


def feed(people, stock):
    """The (bread, wheat) pair that leaves the fewest hungry, then wastes the least food, then
    uses the most bread."""
    best = None
    max_bread = min(stock.get("bread", 0), -(-people // FEEDS["bread"]))
    for bread in range(max_bread + 1):
        rest = max(0, people - bread * FEEDS["bread"])
        wheat = min(stock.get("wheat", 0), -(-rest // FEEDS["wheat"]))
        fed = bread * FEEDS["bread"] + wheat * FEEDS["wheat"]
        hungry = max(0, people - fed)
        key = (hungry, fed, -bread)
        if best is None or key < best[0]:
            best = (key, {"bread": bread, "wheat": wheat, "hungry": hungry})
    return best[1]


def upkeep(people, stock):
    eaten = feed(people, stock)
    stock["bread"] -= eaten["bread"]
    stock["wheat"] -= eaten["wheat"]
    return eaten
