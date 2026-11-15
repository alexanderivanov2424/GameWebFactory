"""Hex Realms: the lobby side (settings, messages, turn timer). The rules live in logic/.

Each player starts with Settlers and a Scout and founds their first Town Hall anywhere. Every turn
everyone plans in secret at once: build inside their territory, train units, order moves and attacks,
research, trade. When all have ended their turn (or the timer runs out), orders resolve together:
units move step by step and fight with dice where they meet. Structures are built by idle people;
production, eating and population are settled per realm (logic/economy.py). Gold, faith and science
are realm-wide; goods sit in stores. Only Town Halls spread land: free land around each city (first
come, first served) and weak land bought with gold (1 gold upkeep a turn per cell). Fog of war (a
setting) hides what your units and structures don't see. Standing orders (Explore, Fight, Pillage,
Travel) carry over turns. Lose every Town Hall and you are out; the last realm standing wins,
otherwise the highest score after the last turn.

Settings: mapSize, turns, turnSeconds (0 = no timer), fog, bots, seed (0 = random).
State: the public part has no map; each member's private state has "view", their fog-limited map.
Game messages ({"action": name, ...fields}; planning only, any order un-readies you):
    build      kind, at "q,r", rot 0-5
    claim      at "q,r"                    2 gold, weak land at once (no cancel)
    recruit    structure, kind
    move       unit, to "q,r"              own cell clears orders; out of reach = Travel
    shoot      unit, at "q,r"
    hold       unit                        toggle
    auto       unit, mode                  toggle a standing order: explore, fight, pillage
    found      unit, rot 0-5
    research   advance
    cancel     order                       a build / claim / recruit / research order
    trade      give, get
    toggle     structure
    staff      on true|false               every structure with jobs
    demolish   structure                   a structure (no refund) or a site id (refunded)
    disband    unit
    done       done true|false             End turn / take it back
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
               ("build", "claim", "recruit", "move", "shoot", "hold", "auto", "found", "research", "cancel", "trade", "toggle", "staff", "demolish",
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

    def auto(self, member, data):
        self.order(member, "auto", text_id(data, "unit"), text_id(data, "mode"))

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
