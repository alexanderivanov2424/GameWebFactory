"""Metro Lanes players: each player's own stock of road pieces, points and weekly pick.

Every player has their own stock (roads, bridges, tunnels, roundabouts, lights) and
gets the same weekly delivery and the same two upgrade offers as everyone else. Points come from
cars driving over road tiles you built, 1 per car per tile (traffic.py credits them).
"""

from gamekit import LobbyError

START_STOCK = {"roads": 10, "bridges": 1, "tunnels": 0, "roundabouts": 0, "lights": 0}
ITEMS = tuple(START_STOCK)


class Player:
    def __init__(self, pid, name, color):
        self.pid = pid
        self.name = name
        self.color = color
        self.stock = dict(START_STOCK)
        self.points = 0         # 1 per car passing one of your road tiles (traffic.py)
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
