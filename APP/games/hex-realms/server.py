"""Hex Realms: the lobby side (settings, messages, turn timer). The rules live in logic/.

Each player starts with Settlers and a Scout (no people) and founds their first Town Hall anywhere;
every Town Hall settlers found brings 2 people. Every turn
everyone plans in secret at once: build inside their territory (Walls and Towers also next to it), train units, order moves and attacks,
research, set up trade. When all have ended their turn (or the timer runs out), orders resolve together:
units move step by step (over enemy structures except Walls and Towers; ending a move on one attacks it)
and fight with dice where they meet. Structures are built by idle people;
production, eating and population are settled per realm (logic/economy.py). Gold is realm-wide, food
is never stored, goods sit in stores, and faith and science are flat (what working structures give now,
minus what advances cost; may go below 0). Swords ⚔️ come from military structures (Barracks 3, Stable and
Shipyard 2); every troop holds 1-2 of them while it lives (instead of people) and gives them back when it dies,
and a recruiting structure can auto-train a unit, recruited each turn it can be paid. Only Town Halls spread land: free land around each city (first
come, first served) and weak land bought with gold (1 gold upkeep a turn per cell). Fog of war (a
setting) hides what your units and structures don't see. Standing orders (Explore, Fight, Pillage,
Travel) carry over turns. Lose every Town Hall and you are out; the last realm standing wins,
otherwise the highest score after the last turn.

Settings: mapSize, turns, turnSeconds (0 = no timer), fog, bots, seed (0 = random).
State: the public part has no map; each member's private state has "view", their fog-limited map.
Game messages ({"action": name, ...fields}; planning only, any order un-readies you):
    build      kind, at "q,r", rot 0-5
    claim      at "q,r"                    2 gold, weak land at once (no cancel)
    recruit    structure, kind             costs swords (held until the unit dies), no people (but settlers)
    train      structure, kind?            auto-train kind there every turn it can be paid; no kind = stop
    move       unit, to "q,r"              own cell clears orders; out of reach = Travel
    shoot      unit, at "q,r"
    hold       unit                        toggle
    auto       unit, mode                  toggle a standing order: explore, fight, pillage
    found      unit, rot 0-5
    research   advance
    cancel     order                       a build / claim / recruit / research order
    trade      structure, give, get        a trade structure trades every turn; no give = stop
    toggle     structure
    staff      on true|false               every structure with jobs
    demolish   structure                   a structure (no refund) or a site id (refunded)
    disband    unit
    done       done true|false             End turn / take it back
"""

from gamekit import Choice, Int, LobbyError, LobbyGame, PatchState
from gamekit.validate import whole_number

from .logic.match import Match


def field(k, optional=False):
    def read(data):
        v = data.get(k)
        if v is None and optional:
            return None
        if not isinstance(v, str) or not 0 < len(v) <= 40:
            raise LobbyError(f"Missing {k}.")
        return v
    return read


def rotation(data):
    return whole_number(data.get("rot", 0), "Rotation", 0, 5)


# Game message action -> readers for the arguments of the orders.py function of the same name.
ORDERS = {
    "build": (field("kind"), field("at"), rotation),
    "claim": (field("at"),),
    "recruit": (field("structure"), field("kind")),
    "train": (field("structure"), field("kind", optional=True)),
    "move": (field("unit"), field("to")),
    "shoot": (field("unit"), field("at")),
    "hold": (field("unit"),),
    "auto": (field("unit"), field("mode")),
    "found": (field("unit"), rotation),
    "research": (field("advance"),),
    "cancel": (field("order"),),
    "trade": (field("structure"), field("give", optional=True), field("get", optional=True)),
    "toggle": (field("structure"),),
    "staff": (lambda data: data.get("on") is True,),
    "demolish": (field("structure"),),
    "disband": (field("unit"),),
}


class Game(LobbyGame):
    MIN_PLAYERS = 1
    MAX_PLAYERS = 6
    SYNC = PatchState
    SETTINGS = {
        "mapSize": Choice("Map size", default="normal", options={"small": "Small", "normal": "Normal", "large": "Large", "huge": "Huge"}),
        "turns": Int("Turn limit", default=40, low=10, high=150),
        "turnSeconds": Int("Turn timer", default=0, low=0, high=600, suffix="s", hint="0 = no timer"),
        "fog": Choice("Fog of war", default="on", options={"on": "On", "off": "Off"}),
        "bots": Int("Bots", default=0, low=0, high=5, hint="computer players"),
        "seed": Int("Map seed", default=0, low=0, high=999999, hint="0 = a new random map"),
    }
    ACTIONS = {**{name: "order" for name in ORDERS}, "done": "done"}

    def __init__(self, room):
        super().__init__(room)
        self.reset_game()

    def reset_game(self):
        self.match = None

    def start_check(self):
        if len(self.players) + self.settings["bots"] > self.MAX_PLAYERS:
            return f"At most {self.MAX_PLAYERS} realms: fewer bots, please."
        return None

    def start_game(self):
        names = {p.id: p.name for p in self.players}
        bots = [f"b{i}" for i in range(1, self.settings["bots"] + 1)]
        names.update({b: f"Bot {b[1:]}" for b in bots})
        self.match = Match(names, self.settings, bots=bots)
        self.start_timer()

    def game_state(self):
        state = self.match.public()
        state["turnSeconds"] = self.settings["turnSeconds"]
        return state

    def private_state(self, member):
        """The map as this member sees it (fog of war), plus their own stock and orders."""
        return self.match.private(member.id if member.playing else None)

    # --- Turn timer ----------------------------------------------------------------------------

    def start_timer(self):
        if self.settings["turnSeconds"]:
            turn = self.match.turn
            self.schedule(self.settings["turnSeconds"], lambda: self.timeout(turn))

    def timeout(self, turn):
        if self.match and self.match.result is None and self.match.turn == turn:
            self.match.resolve()
            self.after_resolve(turn)

    def after_resolve(self, turn):
        if self.match.result is not None:
            self.finish(self.match.result)
        elif self.match.turn != turn:
            self.start_timer()

    # --- Messages -------------------------------------------------------------------------------

    def order(self, member, data):
        action = data["action"]
        self.match.act(member.id, action, *(read(data) for read in ORDERS[action]))

    def done(self, member, data):
        turn = self.match.turn
        self.match.set_done(member.id, data.get("done", True) is True)
        self.after_resolve(turn)

    def on_player_removed(self, member):
        turn = self.match.turn
        self.match.remove(member.id)
        self.after_resolve(turn)
