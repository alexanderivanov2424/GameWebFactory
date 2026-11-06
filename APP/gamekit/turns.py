"""Turn order by turn counters.

Each player has a turn value. The player with the lowest value goes next; on a tie, whoever
reached that value first goes first. Taking an action adds its cost to the player's value,
so a player can act several times in a row if their actions are cheap.

By default everyone starts at the same value, so ties put them in the given order. With
every action costing 1 this is plain round-robin, so simple turn-based games can use it too.
staggered=True starts them at 1, 2, 3, ... instead (Tanks). Don't combine that with
round-robin: with 3+ players the first player would move twice in a row (A=1, B=2, C=3:
A moves to 2, B moves to 3, and A is lowest again).

    queue = TurnQueue(player_ids)             # or TurnQueue(player_ids, staggered=True)
    queue.current()           # whose turn it is (None if empty)
    queue.advance(pid, cost)  # pid acted; add cost to their value
    queue.remove(pid)         # pid is out
    queue.order()             # ids, next to act first
    queue.offsets()           # {pid: value - lowest value}  -> shown as (T+X)
"""

import itertools


class TurnQueue:
    def __init__(self, player_ids=(), staggered=False):
        self._sequence = itertools.count()
        self.values = {}
        self._reached = {}
        for value, pid in enumerate(player_ids, start=1):
            self.values[pid] = value if staggered else 0
            self._reached[pid] = next(self._sequence)

    def __len__(self):
        return len(self.values)

    def __contains__(self, pid):
        return pid in self.values

    def ids(self):
        return list(self.values)

    def order(self):
        return sorted(self.values, key=lambda pid: (self.values[pid], self._reached[pid]))

    def current(self):
        order = self.order()
        return order[0] if order else None

    def advance(self, pid, cost=1):
        self.values[pid] += cost
        self._reached[pid] = next(self._sequence)

    def remove(self, pid):
        self.values.pop(pid, None)
        self._reached.pop(pid, None)

    def offsets(self):
        if not self.values:
            return {}
        lowest = min(self.values.values())
        return {pid: value - lowest for pid, value in self.values.items()}
