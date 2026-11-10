"""Bastion: a city-builder for 1-4 players where each player runs their own city and the focus is
trading with each other. Worker placement, a deck each, simultaneous phases. Endless (for testing):
enemies are switched off, so the game goes on until the players vote to end it.

The board (a 32 x 22 map from content/maps/, picked by the host) is shared: grass to build on,
forest, mountains and water. Every structure is one tile and belongs to one player; each player
has their own resources (gold, wood, stone, metal, food, tools; start: 3 gold, 2 wood, 2 stone,
2 food), units, soldiers, deck and hand.

Setup: in seat order, each player places their keep (castle), then a house, then a farm, one
click each, built at once. A keep goes at least 5 tiles from other players' cities; the house and
farm within 3 tiles of it. The keep gives 1 unit, a house 2.

Reach: units and plans only go within 3 tiles (square, diagonals count) of the player's built
buildings and roads. One unit per tile, whoever owns it.

Each round (every phase is played by everyone at the same time):
1. Place: put units from your pool on tiles (click; right-click takes back one placed this
   phase), then Done (it can be taken back until the last player is done):
   - your planned structure (greyed out, with build tokens): each unit removes one token, then
     returns to the pool; at 0 the structure is built (a house adds 2 units);
   - your built building: it works for you (farm 2 food, lumber mill 3 wood, quarry 3 stone:
     automatic; mine: pick 1 metal or 3 stone; workshop: may turn 3 wood into 1 tool), a
     barracks turns the worker into a soldier for good, a house does nothing yet. Units stay on
     buildings round after round (Orders sends one back); they can't be taken back;
   - a tower takes soldiers only (does nothing yet); soldiers return to their pool at the end of
     every round;
   - forest / mountain: gather 1 wood / 1 stone; empty grass: build a road or scavenge (a die:
     nothing, 1 wood or 1 stone). These units return to the pool.
2. Resolve: automatic jobs happen at once; then each player answers their prompts one by one
   ("Spend 3 wood to make 1 tool?", "1 metal or 3 stone?", "road or scavenge?").
3. Plan: each player gets 3 royal decrees (from their keep). Play cards (each costs its decrees
   and resources): blueprints plan a structure on empty grass within reach (lumber mill next to
   a forest, mine next to a mountain) and leave your deck; Tax (+1 gold, an Unrest card into your
   discard pile), Orders (one of your stationed units back to your pool), Trade (give another
   player 3 different resources or 2 of the same one); Unrest is paid off (1 decree, 1 food).
   Buy cards with your gold from the market (two halves: blueprints and actions; it persists
   between rounds; each player may reshuffle each half once per round for 1 gold). Then Done.
4. End of round: soldiers go back to their pool, the keep makes 1 food and 1 gold, every unit
   (workers and soldiers) eats 1 food; units that can't be fed are lost (soldiers first, then
   unplaced workers, then stationed workers). Hands are discarded and 5 new cards drawn.

Starting deck: Tax, 2 Orders, Trade. Hidden: your hand and your deck's order. Public: everything
else (each player's resources and whole deck, sorted).

Leaving mid-game: the player's units leave the board, their structures stay; setup skips their
pieces. If nobody is left the game ends.

Content (one JSON file per item, documented in content/README.md): content/structures/,
content/cards/, content/maps/, content/starting-deck.json; content/enemies/ (dormant).

Player options:  none
Settings:        {"map": map id ("valley")}
Game messages (cells are x, y; markets are "blueprints" | "actions"):
  {"action": "setup", "x", "y"}             your next setup piece (your setup turn)
  {"action": "place", "x", "y"}             place phase: a unit (or a soldier, on a tower) there
  {"action": "unplace", "x", "y"}           take back a unit you placed this phase
  {"action": "ready", "done"?: bool}         done placing / planning (false takes it back)
  {"action": "answer", "option": id}        resolve phase: answer your current prompt
  {"action": "play", "uid": n, "x"?, "y"?, "to"?: pid, "give"?: {resource: n}}
                                            plan phase: a hand card (blueprints and Orders need
                                            x, y; Trade needs to and give)
  {"action": "buy", "market": half, "slot": n}   plan phase: a market card (0-based slot)
  {"action": "reshuffle", "market": half}   plan phase: deal that half anew (1 gold, once a round)

Code: this file connects the game to the lobby and type-checks message fields. The rules live
in logic/ (see logic/__init__.py for its modules); Match checks who may act and when.
"""

from gamekit import Choice, LobbyGame, PatchState
from gamekit.validate import LobbyError, one_of, whole_number

from .logic.maps import DEFAULT, MAPS, MAX_SIZE
from .logic.match import Match
from .logic.structures import RESOURCE_IDS

HALVES = ("blueprints", "actions")


def cell(data, required=False):
    """Optional x, y (both or neither)."""
    if data.get("x") is None and data.get("y") is None:
        if required:
            raise LobbyError("Pick a tile.")
        return None, None
    return (whole_number(data.get("x"), "Column", 0, MAX_SIZE - 1, clamp=False),
            whole_number(data.get("y"), "Row", 0, MAX_SIZE - 1, clamp=False))


def flag(data, key, default=True):
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise LobbyError(f"{key} must be true or false.")
    return value


def gift(data):
    value = data.get("give")
    if value is None:
        return None
    if not isinstance(value, dict) or len(value) > len(RESOURCE_IDS) or any(k not in RESOURCE_IDS for k in value):
        raise LobbyError("Pick resources to give.")
    return {k: whole_number(n, "Amount", 0, 9, clamp=False) for k, n in value.items()}


class Game(LobbyGame):
    MIN_PLAYERS = 1
    MAX_PLAYERS = 4
    SYNC = PatchState  # big state (board, catalog): send only what changes
    SETTINGS = {
        "map": Choice("Map", default=DEFAULT, options={k: m.name for k, m in MAPS.items()}),
    }
    ACTIONS = {
        "setup": "on_setup",
        "place": "on_place",
        "unplace": "on_unplace",
        "ready": "on_ready",
        "answer": "on_answer",
        "play": "on_play",
        "buy": "on_buy",
        "reshuffle": "on_reshuffle",
    }

    def __init__(self, room):
        super().__init__(room)
        self.reset_game()

    def reset_game(self):
        self.match = None

    def start_game(self):
        self.match = Match({p.id: p.name for p in self.players}, self.settings)

    def game_state(self):
        return self.match.public()

    def private_state(self, member):
        return self.match.private(member.id) if member.playing else None

    async def on_game_message(self, member, data):
        await self.dispatch(member, data)  # Match checks the player, the phase and the turn
        self.check_over()

    def on_setup(self, member, data):
        self.match.setup_place(member.id, *cell(data, required=True))

    def on_place(self, member, data):
        self.match.place(member.id, *cell(data, required=True))

    def on_unplace(self, member, data):
        self.match.unplace(member.id, *cell(data, required=True))

    def on_ready(self, member, data):
        self.match.ready(member.id, flag(data, "done"))

    def on_answer(self, member, data):
        option = data.get("option")
        if not isinstance(option, str) or not 1 <= len(option) <= 20:
            raise LobbyError("Pick one of the answers.")
        self.match.answer(member.id, option)

    def on_play(self, member, data):
        x, y = cell(data)
        to = data.get("to")
        if to is not None and (not isinstance(to, str) or len(to) > 20):
            raise LobbyError("Pick a player.")
        self.match.play(member.id, whole_number(data.get("uid"), "Card", 0), x, y, to, gift(data))

    def on_buy(self, member, data):
        half = one_of(data.get("market"), HALVES, "Pick the blueprints or the actions market.")
        self.match.buy(member.id, half, whole_number(data.get("slot"), "Slot", 0, 20, clamp=False))

    def on_reshuffle(self, member, data):
        self.match.reshuffle(member.id, one_of(data.get("market"), HALVES, "Pick the blueprints or the actions market."))

    def on_player_removed(self, member):
        self.match.leave(member.id)
        self.check_over()

    def check_over(self):
        if self.match.result is not None:
            self.finish(self.match.result)
