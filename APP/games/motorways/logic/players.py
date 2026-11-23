"""Metro Lanes players: each player's own stock of road pieces, points and weekly pick.

Every player has their own stock (roads, bridges, tunnels, motorways, roundabouts, lights) and
gets the same weekly delivery and the same two upgrade offers as everyone else. Points come from
cars driving on roads you built (traffic.py credits them).
The starting roads are START_ROADS for the whole team, split as evenly as possible (start_roads();
earlier players get the spare ones).
"""

from gamekit import LobbyError

START_ROADS = 15      # for the whole team, split between the players
START_STOCK = {"roads": 0, "bridges": 1, "tunnels": 0, "motorways": 0, "roundabouts": 0, "lights": 0}
ITEMS = tuple(START_STOCK)


def start_roads(count):
    """Starting roads for each of count players, in join order (they add up to START_ROADS)."""
    share, spare = divmod(START_ROADS, count)
    return [share + (k < spare) for k in range(count)]


class Player:
    def __init__(self, pid, name, color):
        self.pid = pid
        self.name = name
        self.color = color
        self.stock = dict(START_STOCK)
        self.points = 0.0
        self.trips = 0          # trips that used at least one of your tiles
        self.picked = None      # index of this week's chosen offer (None: not chosen yet)
        self.gone = False       # left the game (their roads stay)
        self.cursor = None      # [x, y] in tiles, shown to the others

    def spend(self, item, n=1, what=None):
        if self.stock[item] < n:
            raise LobbyError(f"You have no {what or item} left.")
        self.stock[item] -= n

    def refund(self, item, n=1):
        self.stock[item] += n
