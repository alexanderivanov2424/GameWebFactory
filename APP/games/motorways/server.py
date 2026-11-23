"""Metro Lanes: real-time co-op road building in one shared city (after Mini Motorways).

1-6 players build roads in the same growing city. Houses and shops appear over time in colours;
shops make demand (pins) and cars from houses of the same colour drive there along the roads to
take it. Each player has their own stock of pieces (15 roads for the whole team, split
between the players, and 1 bridge each to start): road tiles
(drag to draw, 8 directions), bridges and tunnels (drawn straight across water / mountains),
motorways (fast links between two road tiles), roundabouts and traffic lights (busier
junctions). You can erase only what you built (refunded). Everyone may link onto anyone's road.
Points: every trip (a car reaching a shop) is worth 10, split between the players whose tiles
the car drove on, by tiles. The team's trips are the shared score.
Weeks: every `weekLength` seconds the city limits grow, every player gets 5 roads, and the
game pauses while each player picks one of the same two upgrades (time limit `pickTime`; the
first offer if you don't pick). Building works during the pause.
Losing: a shop with 6+ pins runs its timer; when any timer reaches `overflow` seconds, everyone
loses. The game goes on until then (or the End game vote).
Rules and numbers: logic/ (see logic/__init__.py).

Player options:  none (player colours come from join order)
Settings:        {"mapSize": "small" | "medium" | "large", "weekLength": s, "growth": %,
                  "overflow": s, "pickTime": s}
Input messages:  {"type": "input", "cur": [x, y] | null}  your mouse in tiles (shown to the others)
Game messages (players only, during play):
                 {"action": "road", "a": t, "b": t}       draw from tile a to the neighbouring tile b
                                                          (into water/mountain: a bridge/tunnel)
                 {"action": "erase", "t": t}              your piece on that tile
                 {"action": "motorway", "a": t, "b": t}
                 {"action": "place", "t": t, "item": "roundabout" | "light"}
                 {"action": "pick", "option": 0 | 1}      this week's upgrade
Public state:    logic/view.py (no private state).
Result:          {"reason", "week", "trips", "points": {pid: n}, "names": {pid: name}}
"""

from gamekit import Choice, Int, LobbyError, RealtimeGame
from gamekit.sync import quantize

from .logic import view
from .logic.match import Match

PALETTE = ["#0b8f8f", "#c2255c", "#4c6ef5", "#5c940d", "#e8590c", "#7048e8"]


def _tile(data, key):
    t = data.get(key)
    if type(t) is not int:
        raise LobbyError("Bad tile.")
    return t


class Game(RealtimeGame):
    MIN_PLAYERS = 1
    MAX_PLAYERS = 6
    TICK_RATE = 10
    SETTINGS = {
        "mapSize": Choice("City size", default="medium", options={
            "small": "Small (28x18)", "medium": "Medium (36x22)", "large": "Large (44x28)"}),
        "weekLength": Int("Week length", default=60, low=20, high=300, suffix=" s"),
        "growth": Int("City growth", default=100, low=25, high=400, suffix="%"),
        "overflow": Int("Overflow time", default=60, low=10, high=300, suffix=" s"),
        "pickTime": Int("Upgrade pick time", default=30, low=5, high=120, suffix=" s"),
    }
    ACTIONS = {"road": "road", "erase": "erase", "motorway": "motorway", "place": "place", "pick": "pick"}

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
        cur = data.get("cur")
        if cur is None:
            self.match.cursor(member.id, None)
            return
        if not (isinstance(cur, list) and len(cur) == 2 and all(type(v) in (int, float) and -1 <= v <= 100 for v in cur)):
            raise LobbyError("Bad cursor.")
        self.match.cursor(member.id, [quantize(cur[0], 0.1), quantize(cur[1], 0.1)])

    def tick(self, dt):
        if self.match is None or self.match.result is not None:
            return
        self.match.step(dt)
        self.check_over()

    def game_state(self):
        return view.public(self.match)

    def private_state(self, member):
        return None

    # --- actions --------------------------------------------------------------------------

    async def on_game_message(self, member, data):
        if not member.playing or self.match is None or member.id not in self.match.players:
            raise LobbyError("Join the game to build.")
        if self.match.result is not None:
            raise LobbyError("The game is over.")
        await self.dispatch(member, data)

    def road(self, member, data):
        self.match.road(member.id, _tile(data, "a"), _tile(data, "b"))

    def erase(self, member, data):
        self.match.erase(member.id, _tile(data, "t"))

    def motorway(self, member, data):
        self.match.motorway(member.id, _tile(data, "a"), _tile(data, "b"))

    def place(self, member, data):
        item = data.get("item")
        self.match.place(member.id, _tile(data, "t"), item if isinstance(item, str) else "")

    def pick(self, member, data):
        self.match.pick(member.id, data.get("option") if type(data.get("option")) is int else -1)

    def on_player_removed(self, member):
        if self.match is not None:
            self.match.remove(member.id)
            self.check_over()

    def check_over(self):
        if self.match.result is not None:
            self.finish(self.match.result)
