"""Snowbound: a real-time co-op idle game about digging a huge valley out of the snow.

1-8 players each walk a character around one snowed-in valley (a grid of lots, up to 384 x 384)
with a cabin in the middle; the camera follows you. Deep snow is a wall: stand next to it and hold
the mouse (or Space) on it to shovel (holding is the only way); every unit of snow you clear pays you $1. Spend it on
machines (each kind costs 15% more per copy). Every machine is its own unit and each kind clears
snow its own way (logic/machines.py): Neighbour Kids shovel, Drift Dogs tunnel straight lines that
become roads, Dust Sweepers clean up blizzard snow, Braziers (placed where you stand) melt a ring
and keep you warm, Shovel Buddies follow you and boost your shovel, Blade Dozers shove drifts
outward, Deep Augers drill the deepest snow, Snow Stills (placed) turn snow into diesel, Road
Graders widen roads, Jet Blowers fire beams. Mobile ones work near your rally point if you set one
(a spot, or "follow me").
Hauling: digging machines (kids, dogs, sweepers, dozers, augers, graders) carry what they dig and
are paid only when they unload it at a drop point: the cabin, a Snow Depot (built where you stand,
used by everyone) or an Old Rail Station. Roads (Track, Gravel, Paved, Heated: laid and upgraded
by players on cleared ground, Track also left by dogs, graders and jets) make machines and people
faster, and machines route along the road network (logic/roads.py, logic/hauling.py).
Factory: processors (placed) take snow from your own haulers and turn it into goods worth more
(Brick Press -> Snow Bricks, Ice Press -> Ice Blocks); a processor placed next to another one pulls
its goods (Igloo Workshop next to a Brick Press, Ice Carver next to an Ice Press). Conveyors (laid
on cleared ground, each pointing one way, each player's own) carry goods from their owner's processors
beside them to a market
(a belt pointing into the cabin or an Old Rail Station sells them) or into another of their owner's
processors; goods never cross onto someone else's belt (logic/factory.py, logic/conveyors.py).
Landmarks: a few one-of-a-kind ruins are hidden in each valley (landmarks/*.json). Whoever clears
the last of a ruin's lots gets its reward: a unique helper (Woolly Mammoth, Snow Spirit, St. Bernard,
Reindeer Plough, Snow Golem, Old Snowcat), a unique building (Ice Factory, Snow Cone Stand, Hot
Spring) or a team perk (Old Rail Station, Weather Station, Observatory) (logic/landmarks.py). Upgrades mostly change how one machine works (Snow Angels, Sled
Harness, Corkscrew, Long Throw...), plus shovel, survival, delivery and shared team upgrades;
Snowshoes let you walk over deeper snow. Snow gets deeper the further you get from
the cabin. Each player has their own wallet, machines and upgrades.
Lots hide things: forests (logs for the stove), buried cabins (cash), gas stations (diesel),
supply caches and lost skiers (free helpers). Golden snowflakes appear near players now and then:
the first to walk into one gets a x5 Frenzy or a lump of cash.
Demolish: your own placed machines, Snow Depots, warming huts, conveyors and roads can be torn down
for 25% of what they cost (roads: of what players paid; landmark buildings, rail stations and the cabin stay).
Survival: the cabin stove and warming huts (bought, built where you stand) burn logs from a shared
woodpile. Near a lit one you warm up; anywhere else you get colder, and at 0 warmth you get
frostbite (can't shovel, walk slowly) until you warm up. Food drops over time, faster while
shoveling; rations are eaten automatically; at 0 food you shovel weakly, walk slower and get colder.
Machines burn diesel and stop when your tank is empty. Blizzards (with a 20 s warning) slow
machines, burn logs fast, chill you faster, stop deliveries and drop snow back on cleared ground.
The game is won when the goal share of the valley is clear (or ended with the End game vote).
Numbers: logic/ (see logic/__init__.py), machines/*.json and upgrades/*.json.

Player options:  none
Settings:        {"mapSize": "small" | "medium" | "large" | "huge", "goal": 10-100 (%),
                  "survival": "easy" | "normal" | "harsh"}
Input messages:  {"type": "input", "keys": [up/down/left/right held], "aim": [x, y] | null
                  (lot under the mouse), "dig": bool (dig button held: the only way to
                  shovel, avatars.SWING_RATE swings a second at the aimed lot)}
Game messages (players only):
                 {"action": "buy", "machine": id, "count": 1 | 10}   (placed machines: 1, built on the
                     cleared lot you stand on, one per lot)
                 {"action": "upgrade", "upgrade": id}
                 {"action": "supply", "item": "rations" | "diesel" | "logs", "qty": number > 0}
                     (logs go to the shared woodpile; diesel and logs can't be bought in a blizzard)
                 {"action": "rally", "x": int, "y": int} | {"action": "rally", "follow": true}
                     | {"action": "rally"}   where your units look for work first (none: anywhere)
                 {"action": "hut"}                              build a warming hut where you stand
                 {"action": "depot"}                            build a Snow Depot where you stand
                 {"action": "road", "level": 1-4, "lots": [[x, y], ...]}   lay or upgrade road
                     (at most 200 lots; pays the difference per lot; lots already that good are skipped)
                 {"action": "belt", "lots": [[x, y, dir 0-3: right/down/left/up], ...]}   lay conveyors
                     (at most 200; a lot with a conveyor turns to the new direction for free)
                 {"action": "demolish", "lots": [[x, y], ...], "lines": bool}   tear down what's on
                     each lot for 25% back (lines: true only takes conveyors and roads; logic/demolish.py)
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
from .logic.roads import MAX_LOTS as MAX_ROAD_LOTS

PALETTE = ["#ff5c5c", "#4fc3f7", "#ffd54f", "#81c784", "#ba68c8", "#ff8a65", "#4db6ac", "#f06292"]


def _xy(data):
    x, y = data.get("x"), data.get("y")
    if type(x) is not int or type(y) is not int:
        raise LobbyError("Bad lot.")
    return x, y


def _lots(data):
    lots = data.get("lots")
    if not isinstance(lots, list) or not 0 < len(lots) <= MAX_ROAD_LOTS or not all(
            isinstance(lot, list) and len(lot) == 2 and all(type(v) is int for v in lot) for lot in lots):
        raise LobbyError("Bad lots.")
    return lots


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
    ACTIONS = {"buy": "buy", "upgrade": "upgrade", "supply": "supply",
               "rally": "rally", "hut": "hut", "depot": "depot", "road": "road", "belt": "belt", "demolish": "demolish"}

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

    def depot(self, member, data):
        self.match.build_depot(member.id)

    def road(self, member, data):
        level = data.get("level")
        if type(level) is not int:
            raise LobbyError("Unknown road level.")
        self.match.lay_road(member.id, _lots(data), level)

    def belt(self, member, data):
        lots = data.get("lots")
        if not isinstance(lots, list) or not 0 < len(lots) <= MAX_ROAD_LOTS or not all(
                isinstance(lot, list) and len(lot) == 3 and all(type(v) is int for v in lot) for lot in lots):
            raise LobbyError("Bad lots.")
        self.match.lay_belt(member.id, lots)

    def demolish(self, member, data):
        self.match.demolish(member.id, _lots(data), data.get("lines") is True)

    def on_player_removed(self, member):
        if self.match is not None:
            self.match.remove(member.id)
            self.check_over()

    def check_over(self):
        if self.match.result is not None:
            self.finish(self.match.result)
