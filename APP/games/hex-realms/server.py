"""Hex Realms: a simultaneous-turn civilization game on a random hex map.

Each player starts with Settlers and founds their first Town Hall wherever they choose (the
starting goods go into it). Fog of war (a setting): units and structures (further) reveal the
map; cells once seen stay explored, enemy structures are remembered as last seen. Every turn all players plan at once, in
secret: place structures (multi-cell footprints, turned in 60-degree steps) inside their
territory, train units, order moves and attacks, research advances, trade at a market. When
everyone has pressed End turn (or the turn timer runs out), all orders resolve together:
units move one cell per step at the same time and fight with dice wherever they meet. Every
structure works if it has its workers (people, who need food and housing). Ordered structures
become construction sites that take a few turns of work, each turn needing builders: people
without a job (switch structures off, all at once, or demolish them to free people). Gold, faith and
science are realm-wide; goods (food, wood, stone, metal) go straight into the realm's stores (Town
Hall, Storage Yard, Granary) up to their room. Structures go anywhere inside your territory;
gold buys more (claim an explored cell next to it, with its neighbours). Land is first come, first
served: it stays yours, and cells two realms reach in the same turn go to no one. No roads. Units on
an Explore order walk on their own to clear the fog.
Lose every Town Hall and you are out. Last
realm standing wins; otherwise the highest score after the last turn.
Full rules: logic/match.py (turn order, score), logic/economy.py, logic/combat.py,
logic/movement.py, logic/orders.py, logic/logistics.py, logic/construction.py,
logic/explore.py; content in structures/, units/,
advances/ (fields in logic/content.py).

Player options:  none (colors by seat)
Settings:        mapSize (small/normal/large/huge), turns (turn limit), turnSeconds (0 = no timer),
                 fog (on/off), bots (computer players added to the seats; logic/bots.py),
                 seed (0 = random map)
State: the public part has no map; each member's private state has "view" (cells, dim, structures,
units, construction sites, territory, events as they see them; spectators see everything).
Game messages (all only while planning; any order un-readies you; never use a "type" key,
the lobby envelope owns it):
    {"action": "build", "kind": stype, "at": "q,r", "rot": 0-5}
    {"action": "claim", "at": "q,r"}                   (2 gold; at resolution the cell and its free neighbours become yours)
    {"action": "recruit", "structure": sid, "kind": utype}
    {"action": "move", "unit": uid, "to": "q,r"}      (to = own cell clears the unit's orders)
    {"action": "shoot", "unit": uid, "at": "q,r"}
    {"action": "hold", "unit": uid}                    (toggle)
    {"action": "explore", "unit": uid}                 (toggle; kept across turns, any other order stops it)
    {"action": "found", "unit": uid, "rot": 0-5}
    {"action": "research", "advance": aid}
    {"action": "cancel", "order": oid}                 (a build / claim / recruit / research order)
    {"action": "trade", "give": res, "get": res}
    {"action": "toggle", "structure": sid}
    {"action": "staff", "on": true|false}              (switch every structure with jobs on / off)
    {"action": "demolish", "structure": sid}           (a structure, no refund, not a Town Hall; or a
                                                        construction site id, cost refunded)
    {"action": "disband", "unit": uid}
    {"action": "done", "done": true|false}             (End turn / take it back)

Code: this file connects the game to the lobby (settings, messages, the turn timer). The rules
live in logic/ (see logic/__init__.py for its modules).
"""

from gamekit import Choice, Int, LobbyError, LobbyGame, PatchState
from gamekit.validate import whole_number

from .logic.match import Match


def text_id(data, k):
    v = data.get(k)
    if not isinstance(v, str) or not 0 < len(v) <= 40:
        raise LobbyError(f"Missing {k}.")
    return v


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
    ACTIONS = {name: name for name in
               ("build", "claim", "recruit", "move", "shoot", "hold", "explore", "found", "research", "cancel", "trade", "toggle", "staff", "demolish",
                "disband", "done")}

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

    def order(self, member, name, *args):
        self.match.act(member.id, name, *args)

    # --- Messages -------------------------------------------------------------------------------

    def build(self, member, data):
        self.order(member, "build", text_id(data, "kind"), text_id(data, "at"), whole_number(data.get("rot", 0), "Rotation", 0, 5))

    def claim(self, member, data):
        self.order(member, "claim", text_id(data, "at"))

    def recruit(self, member, data):
        self.order(member, "recruit", text_id(data, "structure"), text_id(data, "kind"))

    def move(self, member, data):
        self.order(member, "move", text_id(data, "unit"), text_id(data, "to"))

    def shoot(self, member, data):
        self.order(member, "shoot", text_id(data, "unit"), text_id(data, "at"))

    def hold(self, member, data):
        self.order(member, "hold", text_id(data, "unit"))

    def explore(self, member, data):
        self.order(member, "explore", text_id(data, "unit"))

    def found(self, member, data):
        self.order(member, "found", text_id(data, "unit"), whole_number(data.get("rot", 0), "Rotation", 0, 5))

    def research(self, member, data):
        self.order(member, "research", text_id(data, "advance"))

    def cancel(self, member, data):
        self.order(member, "cancel", text_id(data, "order"))

    def trade(self, member, data):
        self.order(member, "trade", text_id(data, "give"), text_id(data, "get"))

    def toggle(self, member, data):
        self.order(member, "toggle", text_id(data, "structure"))

    def staff(self, member, data):
        self.order(member, "staff", data.get("on") is True)

    def demolish(self, member, data):
        self.order(member, "demolish", text_id(data, "structure"))

    def disband(self, member, data):
        self.order(member, "disband", text_id(data, "unit"))

    def done(self, member, data):
        turn = self.match.turn
        self.match.set_done(member.id, data.get("done", True) is True)
        self.after_resolve(turn)

    def on_player_removed(self, member):
        turn = self.match.turn
        self.match.remove(member.id)
        self.after_resolve(turn)
