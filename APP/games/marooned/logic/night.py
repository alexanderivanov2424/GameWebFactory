"""Marooned: the night: the suspicion vote, then hunger and sleep.

The vote changes no rules: everyone secretly names a suspect (or "nobody") and only the
tally is shown. Ballots stay secret until the end, where they score (scoring.py). Then
everyone gets hungrier, and sleeps sheltered or not:
- Camp shelter: SHELTER_PER_LEVEL spots per level, taken by whoever reached camp first.
- A tile with "shelter" (a cave) shelters that many, also first come first served.
- Sheltered: Rested (+1 max energy tomorrow), and it heals Sick or else one wound.
  SICK_AFTER unsheltered nights in a row make you Sick (max energy -1 until healed).

    night.start_vote(m)        # m.votes = SecretChoices of everyone still in
    night.vote(m, pid, choice) # choice: a public id or NOBODY
    night.tally(m)             # once complete: {"p2": 3, "nobody": 1}; stored in m.vote_history
    night.sleep(m)             # hunger and sleep for everyone
"""

from gamekit import LobbyError, SecretChoices

from .island import tile_types
from .survivor import MAX_HUNGER

NOBODY = "nobody"
HUNGER_PER_NIGHT = 1
SICK_AFTER = 3   # unsheltered nights in a row


def start_vote(m):
    m.votes = SecretChoices(list(m.order))


def vote(m, pid, choice):
    if choice != NOBODY and choice not in m.order:
        raise LobbyError("Vote for a player who's still in the game, or nobody.")
    if not m.votes.choose(pid, choice):
        raise LobbyError("You've already voted tonight.")


def tally(m):
    ballots = m.votes.peek()
    counts = {}
    for pid, choice in ballots.items():
        counts[choice] = counts.get(choice, 0) + 1
        m.people[pid].stats["votes"].append(choice)
    m.vote_history[m.day] = {"tally": counts, "voters": len(ballots)}
    m.votes = None
    if counts:
        text = ", ".join(f"{m.names.get(c, 'nobody')} {n}" for c, n in sorted(counts.items(), key=lambda kv: -kv[1]))
        m.log(f"Night {m.day} vote: {text}.")
    return counts


def sleep(m):
    sheltered = set()
    by_square = {}
    for pid in m.order:
        by_square.setdefault(m.people[pid].pos, []).append(m.people[pid])
    kinds = tile_types()
    for cell, people in by_square.items():
        if cell == m.island.camp:
            spots = m.camp.shelter_spots()
        else:
            spots = kinds[m.island.tile(cell)["type"]]["shelter"]
        people.sort(key=lambda s: s.arrived)
        for s in people[:spots]:
            sheltered.add(s.pid)
    for pid in m.order:
        s = m.people[pid]
        s.add_hunger(HUNGER_PER_NIGHT)
        if s.hunger >= MAX_HUNGER:
            s.stats["starving"] += 1
        if pid in sheltered:
            s.rested = True
            s.unsheltered = 0
            if s.sick:
                s.sick = False
            elif s.wounds:
                s.wounds -= 1
            if s.pos == m.island.camp:
                s.stats["campShelter"] += 1
        else:
            s.rested = False
            s.unsheltered += 1
            if s.unsheltered >= SICK_AFTER:
                s.sick = True
    inside = [m.names[pid] for pid in m.order if pid in sheltered]
    m.log(f"Night {m.day}: sheltered: {', '.join(inside) if inside else 'nobody'}.")
    starving = [m.names[pid] for pid in m.order if m.people[pid].hunger >= MAX_HUNGER]
    if starving:
        m.log(f"Starving: {', '.join(starving)}.")
