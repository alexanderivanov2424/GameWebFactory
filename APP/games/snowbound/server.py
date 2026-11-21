"""Snowbound: a real-time co-op idle game about digging a huge valley out of the snow.

1-8 players share one snowed-in valley (a grid of lots, up to 384 x 384) with a cabin in the
middle. Click snow on lots next to cleared ground to shovel it by hand; every unit of snow you
clear pays you $1. Spend it on machines (Neighbour Kid, Snowblower, Pickup Plow ... Jet Blower:
each kind costs 15% more per copy) that drive out and clear snow on their own, and on upgrades
(x2 machine tiers, stronger clicks, deliveries, shared team upgrades). Snow gets deeper the
further you get from the cabin. Each player has their own wallet, machines and upgrades.
Lots hide things: forests (logs for the stove), buried cabins (cash), gas stations (diesel),
supply caches and lost skiers (free helpers). Golden snowflakes appear on cleared ground now
and then: the first to click one gets a x5 Frenzy or a lump of cash.
Survival: a shared stove burns logs from the woodpile; while it's out everyone gets colder,
and at 0 warmth you get frostbite (no clicking, machines at half speed). Your food drops over
time and with each click; rations are eaten automatically; at 0 food clicks are weak and you
get colder. Machines burn diesel and stop when your tank is empty. Blizzards (with a 20 s
warning) slow machines, burn logs fast, stop deliveries and drop snow back on cleared ground.
The game is won when the goal share of the valley is cleared (or ended with the End game vote).
Numbers: logic/ (see logic/__init__.py), machines/*.json and upgrades/*.json.

Player options:  none
Settings:        {"mapSize": "small" | "medium" | "large" | "huge", "goal": 10-100 (%),
                  "survival": "easy" | "normal" | "harsh"}
Input messages:  {"type": "input", "cursor": [x, y] | null}   the lot you point at, shown to everyone
Game messages (players only):
                 {"action": "click", "x": int, "y": int}       shovel a lot (15 clicks/s at most)
                 {"action": "flake", "x": int, "y": int}       catch the golden snowflake there
                 {"action": "buy", "machine": id, "count": 1 | 10}
                 {"action": "upgrade", "upgrade": id}
                 {"action": "supply", "item": "rations" | "diesel" | "logs", "qty": number > 0}
                     (logs go to the shared woodpile; diesel and logs can't be bought in a blizzard)
                 {"action": "focus", "x": int, "y": int} | {"action": "focus"}   where your crews
                     head first (no x/y: clear it)
Public / private state: logic/view.py.
Result:          {"reason": str, "cleared": {pid: snow}}
"""

from gamekit import Choice, Int, LobbyError, RealtimeGame
from gamekit.validate import one_of, whole_number

from .logic import view
from .logic.content import MACHINES, UPGRADES
from .logic.economy import PRICES
from .logic.match import Match

PALETTE = ["#ff5c5c", "#4fc3f7", "#ffd54f", "#81c784", "#ba68c8", "#ff8a65", "#4db6ac", "#f06292"]


def _xy(data):
    x, y = data.get("x"), data.get("y")
    if type(x) is not int or type(y) is not int:
        raise LobbyError("Bad lot.")
    return x, y


def _name(data, key):
    value = data.get(key)
    return value if isinstance(value, str) else None


class Game(RealtimeGame):
    MIN_PLAYERS = 1
    MAX_PLAYERS = 8
    TICK_RATE = 10
    SETTINGS = {
        "mapSize": Choice("Valley size", default="large", options={
            "small": "Small (96x96)", "medium": "Medium (160x160)",
            "large": "Large (256x256)", "huge": "Huge (384x384)"}),
        "goal": Int("Clear to win", default=75, low=10, high=100, suffix="%"),
        "survival": Choice("Survival", default="normal",
                           options={"easy": "Easy", "normal": "Normal", "harsh": "Harsh"}),
    }
    ACTIONS = {"click": "click", "flake": "flake", "buy": "buy", "upgrade": "upgrade",
               "supply": "supply", "focus": "focus"}

    def __init__(self, room):
        super().__init__(room)
        self.reset_game()

    def reset_game(self):
        self.match = None

    def start_game(self):
        players = self.players
        colors = {p.id: PALETTE[i % len(PALETTE)] for i, p in enumerate(players)}
        self.match = Match({p.id: p.name for p in players}, self.settings, colors=colors)

    # --- real time ------------------------------------------------------------------------

    def on_input(self, member, data):
        cursor = data.get("cursor")
        player = self.match.players.get(member.id) if self.match else None
        if player is None:
            return
        if cursor is None:
            player.cursor = None
        elif (isinstance(cursor, list) and len(cursor) == 2 and all(type(v) is int for v in cursor)
              and self.match.world.index(*cursor) is not None):
            player.cursor = cursor
        else:
            raise LobbyError("Bad cursor.")

    def tick(self, dt):
        if self.match is None or self.match.result is not None:
            return
        self.match.step(dt)
        self.check_over()

    def game_state(self):
        return view.public(self.match)

    def private_state(self, member):
        if not member.playing or self.match is None:
            return None
        return view.private(self.match, member.id)

    # --- actions --------------------------------------------------------------------------

    async def on_game_message(self, member, data):
        if not member.playing or member.id not in self.match.players:
            raise LobbyError("Join the game to dig.")
        await self.dispatch(member, data)

    def click(self, member, data):
        self.match.click(member.id, *_xy(data))
        self.check_over()

    def flake(self, member, data):
        self.match.catch_flake(member.id, *_xy(data))

    def buy(self, member, data):
        machine = one_of(_name(data, "machine"), MACHINES, "Unknown machine.")
        count = data.get("count")
        if type(count) is not int or count not in (1, 10):
            raise LobbyError("Buy 1 or 10.")
        self.match.buy(member.id, machine, count)

    def upgrade(self, member, data):
        self.match.upgrade(member.id, one_of(_name(data, "upgrade"), UPGRADES, "Unknown upgrade."))

    def supply(self, member, data):
        item = one_of(_name(data, "item"), PRICES, "Unknown supply.")
        qty = data.get("qty")
        if type(qty) not in (int, float) or qty != qty:
            raise LobbyError("Bad amount.")
        if item != "diesel":
            qty = whole_number(qty, "The amount")
        self.match.supply(member.id, item, qty)

    def focus(self, member, data):
        if "x" not in data and "y" not in data:
            self.match.set_focus(member.id, None)
        else:
            self.match.set_focus(member.id, _xy(data))

    def on_player_removed(self, member):
        if self.match is not None:
            self.match.remove(member.id)
            self.check_over()

    def check_over(self):
        if self.match.result is not None:
            self.finish(self.match.result)
