"""Snowbound: a real-time co-op idle game about digging a huge valley out of the snow.

1-8 players each walk a character around one snowed-in valley (a grid of lots, up to 384 x 384)
with a cabin in the middle; the camera follows you. Deep snow is a wall: stand next to it and hold
the mouse on it (or click fast) to shovel; every unit of snow you clear pays you $1. Spend it on
machines (Neighbour Kid, Snowblower, Pickup Plow ... Jet Blower: each kind costs 15% more per
copy). Every machine you buy is its own unit that heads out from the cabin and clears snow on its
own, near your rally point if you set one (a spot, or "follow me"). Upgrades: x2 machine tiers,
stronger shoveling, deliveries, shared team upgrades. Snow gets deeper the further you get from
the cabin. Each player has their own wallet, machines and upgrades.
Lots hide things: forests (logs for the stove), buried cabins (cash), gas stations (diesel),
supply caches and lost skiers (free helpers). Golden snowflakes appear near players now and then:
the first to walk into one gets a x5 Frenzy or a lump of cash.
Survival: the cabin stove and warming huts (bought, built where you stand) burn logs from a shared
woodpile. Near a lit one you warm up; anywhere else you get colder, and at 0 warmth you get
frostbite (can't shovel, walk slowly) until you warm up. Food drops over time and with each
swing; rations are eaten automatically; at 0 food you shovel weakly, walk slower and get colder.
Machines burn diesel and stop when your tank is empty. Blizzards (with a 20 s warning) slow
machines, burn logs fast, chill you faster, stop deliveries and drop snow back on cleared ground.
The game is won when the goal share of the valley is clear (or ended with the End game vote).
Numbers: logic/ (see logic/__init__.py), machines/*.json and upgrades/*.json.

Player options:  none
Settings:        {"mapSize": "small" | "medium" | "large" | "huge", "goal": 10-100 (%),
                  "survival": "easy" | "normal" | "harsh"}
Input messages:  {"type": "input", "keys": [up/down/left/right held], "aim": [x, y] | null
                  (lot under the mouse), "dig": bool (dig button held: swings at the aimed lot)}
Game messages (players only):
                 {"action": "dig", "x": int, "y": int}         one swing now (a click)
                 {"action": "buy", "machine": id, "count": 1 | 10}
                 {"action": "upgrade", "upgrade": id}
                 {"action": "supply", "item": "rations" | "diesel" | "logs", "qty": number > 0}
                     (logs go to the shared woodpile; diesel and logs can't be bought in a blizzard)
                 {"action": "rally", "x": int, "y": int} | {"action": "rally", "follow": true}
                     | {"action": "rally"}   where your units look for work first (none: anywhere)
                 {"action": "hut"}                              build a warming hut where you stand
Public / private state: logic/view.py (spectators get the units near any character).
Result:          {"reason": str, "cleared": {pid: snow}}
"""

from gamekit import Choice, Int, LobbyError, RealtimeGame
from gamekit.validate import one_of, whole_number

from .logic import view
from .logic.avatars import KEYS
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
    ACTIONS = {"dig": "dig", "buy": "buy", "upgrade": "upgrade", "supply": "supply",
               "rally": "rally", "hut": "hut"}

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
        if self.match is None or member.id not in self.match.players:
            return
        keys = data.get("keys", [])
        if not isinstance(keys, list) or len(keys) > len(KEYS) or not all(isinstance(k, str) and k in KEYS for k in keys):
            raise LobbyError("Bad keys.")
        aim = data.get("aim")
        if aim is not None and not (isinstance(aim, list) and len(aim) == 2 and all(type(v) is int for v in aim)):
            raise LobbyError("Bad aim.")
        self.match.set_input(member.id, sorted(set(keys)), aim, data.get("dig") is True)

    def tick(self, dt):
        if self.match is None or self.match.result is not None:
            return
        self.match.step(dt)
        self.check_over()

    def game_state(self):
        return view.public(self.match)

    def private_state(self, member):
        if self.match is None:
            return None
        if member.playing and member.id in self.match.players:
            return view.private(self.match, member.id)
        return view.spectator(self.match)

    # --- actions --------------------------------------------------------------------------

    async def on_game_message(self, member, data):
        if not member.playing or member.id not in self.match.players:
            raise LobbyError("Join the game to dig.")
        await self.dispatch(member, data)

    def dig(self, member, data):
        self.match.dig(member.id, *_xy(data))
        self.check_over()

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

    def rally(self, member, data):
        if data.get("follow") is True:
            self.match.rally(member.id, "follow")
        elif "x" in data or "y" in data:
            self.match.rally(member.id, _xy(data))
        else:
            self.match.rally(member.id, None)

    def hut(self, member, data):
        self.match.build_hut(member.id)

    def on_player_removed(self, member):
        if self.match is not None:
            self.match.remove(member.id)
            self.check_over()

    def check_over(self):
        if self.match.result is not None:
            self.finish(self.match.result)
