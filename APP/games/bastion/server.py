"""Bastion: a co-op city-builder for 1-4 players with worker placement and a deck each. Grow a city
whose buildings feed each other, keep its people fed, and beat every enemy that comes for it.

The board (a 32 x 22 map from content/maps/, picked by the host) is shared: grass to build on,
forest, mountains and water. The game starts with a small town: a 1x1 keep, a few roads, a
lumbermill by the forest, a farm and one house. Structures belong to nobody. The team shares one
stockpile (gold, wood, stone, ore, wheat, bread, tools; it starts with 4 gold, 6 wood, 4 stone,
6 wheat, 2 tools), its soldiers, a stock of road tiles and of wall tiles, and the keep's health (the
host's "Keep health"; at 0 the game is lost).

People: houses (2 each) and the keep (2) are the city's population; ruined ones still house
people. At the end of every round the city eats: each bread feeds 4, each wheat 2, using the
least food that covers everyone (bread on a tie). People it can't feed are hungry.

Each round:
1. Start: hands are discarded and refilled to 5 (the round-1 hand always holds a House
   blueprint), the market is dealt anew, an enemy arrives if due, the first player moves one
   seat on, and the city's units (population - last round's hungry) are split equally among
   the players; the remainder goes one each from the first player on.
2. Place (everyone at once): put your units on
   - a building that is worked: 1 unit per building per round, first come (not one that is
     damaged, plagued, frozen this round or would make nothing);
   - Hauling (any number);
   - Fighting an active enemy that soldiers can beat (any number);
   - an enemy lair or blight tile (1 unit per tile).
   Take placements back until you're ready; ready can be taken back until the last player
   confirms. Then the act phase starts.
3. Act (one player at a time, from the first player in seat order). On your turn, in any order:
   - resolve your units one at a time; each acts once and leaves the board:
     work: the building makes its output = base + adjacency bonuses (each building's file lists
       what it likes or hates next to it) - 1 per enemy blight next to it; spend 1 tool from
       the stockpile for +1. Inputs come from the stockpile and need a link (next to the keep
       or a storage yard (a depot), or a road reaching one). Goods go straight to the stockpile
       from a building next to a depot, otherwise into its store (up to 6) until hauled. Gold,
       soldiers, keep health and cures never wait.
     haul: pick a building with stored goods that is next to a depot or whose roads reach one;
       up to 3 goods move from it to the stockpile at once, biggest piles first. Each round the
       first N hauls carry 5 instead, N = undamaged Carriages.
     fight: 1 strike on that enemy; every "soldiers per damage" strikes deal 1 damage, and the
       rest carry over (the soldier counter's Strike uses them up first).
     raze: 1 strike on that tile; a blight takes 1, a lair tile its raze cost.
   - play cards: blueprints build (place the shape on empty grass or over roads, turned any of 4
     ways, never mirrored, pay its cost; the blueprint leaves your deck; a chapel adds an
     Absolution card), actions do what they say (repair, cure, gain, draw, remove cards from
     your deck), curses are paid off to remove them;
   - buy from the market (6 cards, team gold, unlimited copies: a bought slot is refilled; a
     blueprint comes in its bundle, e.g. House x3) or reroll it (2 gold, +1 per reroll this round);
   - place road and wall tiles (1x1, on empty grass) from the team's stock; with the stock at 0
     a placement first buys 3 (roads: 1 gold, walls: 1 stone). Removing a tile is free.
   - spend soldiers: Strike an enemy (its soldiers per damage) or raze an enemy tile.
   End turn: your unresolved units are lost and the next player acts.
4. End of round (after the last player): the keep makes 2 gold and 1 wheat, upkeep (the city eats; the
   hungry don't work next round), every active enemy makes its next attack (each has 2-3 it
   takes in turn), then the next round starts.

Enemies are cards above the board. The first arrives on round peaceRounds + 1, then one every
enemyGap rounds ("enemies" in all; lower tiers first, a boss last). Each has its own ways to be
beaten (on its card): soldiers or fighting units per damage, resources per damage (Frost Witch:
wood), curing the plague it spread (Rat King), paying off the curse cards it sends (Bandit
Lord), razing its lair tiles (Necromancer). Attacks steal from the stockpile, loot goods waiting
in buildings that aren't protected, ruin building tiles (not ones next to a wall or near a
watchtower; with none open they break a wall), damage the keep, put blight tiles on the board,
add curse cards to decks, plague buildings (no unit until cured) or freeze them (no unit next
round), kill soldiers. Enemy health scales with difficulty (75/100/130%) and +50% per player
after the first. Beating every enemy wins. The keep at 0, or any enemy left 6 rounds after the
last one arrived, loses.

Leaving mid-game: the player's cards and units are gone; if it was their turn, the turn passes.
If nobody is left the game ends (lost).

Hidden: your hand and your deck's order. Public: everything else (each player's whole deck,
sorted; the next enemies only show when they arrive).

Content (one JSON file per item, documented in content/README.md): content/structures/,
content/cards/, content/enemies/, content/maps/, content/starting-deck.json.

Player options:  none
Settings:        {"difficulty": "easy" | "normal" | "hard" ("normal"), "keepHealth": 10-40 (20),
                  "map": map id ("valley"), "enemies": 3-7 (5), "peaceRounds": 2-8 (5),
                  "enemyGap": 2-5 (3)}
Game messages (targets: "s<structure uid>" | "haul" | "fight<enemy index>" | "raze<x>,<y>"):
  Place phase:
    {"action": "place", "target": t}             one of your free units onto t
    {"action": "unplace", "target": t}           take one of your units off t (not while ready)
    {"action": "ready", "done"?: bool}           done placing (false takes it back)
  Act phase, on your turn only:
    {"action": "resolve", "target": t, "tool"?: bool, "from"?: structure uid}
                       one of your units on t acts; "tool": spend a tool on work (+1 output);
                       "from": the building a haul takes from (default: the one with most goods)
    {"action": "play", "uid": n, "x"?: col, "y"?: row, "rotation"?: 0-3, "remove"?: [uid, ...]}
                       a hand card; blueprints need x, y (top-left of the turned shape) and
                       rotation; repair/cure cards need x, y on the building; trash cards
                       (Absolution) list the other hand cards to remove in "remove"
    {"action": "buy", "slot": n}                  a market card (0-based)
    {"action": "reroll"}                          deal the market anew (state.game.rerollCost gold)
    {"action": "tile", "kind": "road" | "wall", "x": col, "y": row}   place one tile from the stock
    {"action": "remove_tile", "x": col, "y": row}  remove a road or wall tile (free)
    {"action": "strike", "foe": i, "way": "soldiers" | "resources", "times"?: n (1)}
    {"action": "raze", "x": col, "y": row}        an enemy tile, with soldiers
    {"action": "end_turn"}                        unresolved units are lost; the next player acts

Code: this file connects the game to the lobby and type-checks message fields. The rules live
in logic/ (see logic/__init__.py for its modules); Match checks who may act and when.
"""

from gamekit import Choice, Int, LobbyGame, PatchState
from gamekit.validate import LobbyError, one_of, whole_number

from .logic.foes import DIFFICULTY
from .logic.maps import DEFAULT, MAPS, MAX_SIZE
from .logic.match import Match


def cell(data, required=False):
    """Optional x, y (both or neither)."""
    if data.get("x") is None and data.get("y") is None:
        if required:
            raise LobbyError("Pick a cell.")
        return None, None
    return (whole_number(data.get("x"), "Column", 0, MAX_SIZE - 1, clamp=False),
            whole_number(data.get("y"), "Row", 0, MAX_SIZE - 1, clamp=False))


def flag(data, key, default=True):
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise LobbyError(f"{key} must be true or false.")
    return value


def target(data):
    value = data.get("target")
    if not isinstance(value, str) or not 1 <= len(value) <= 20:
        raise LobbyError("Pick a target.")
    return value


class Game(LobbyGame):
    MIN_PLAYERS = 1
    MAX_PLAYERS = 4
    SYNC = PatchState  # big state (board, catalog): send only what changes
    SETTINGS = {
        "difficulty": Choice("Difficulty", default="normal",
                             options={"easy": "Easy", "normal": "Normal", "hard": "Hard"},
                             hint=" · ".join(f"{k.title()}: enemy health {round(v * 100)}%" for k, v in DIFFICULTY.items())),
        "keepHealth": Int("Keep health", default=20, low=10, high=40),
        "map": Choice("Map", default=DEFAULT, options={k: m.name for k, m in MAPS.items()}),
        "enemies": Int("Enemies", default=5, low=3, high=7),
        "peaceRounds": Int("Peaceful rounds", default=5, low=2, high=8),
        "enemyGap": Int("Rounds between enemies", default=3, low=2, high=5),
    }
    ACTIONS = {
        "place": "on_place",
        "unplace": "on_unplace",
        "ready": "on_ready",
        "resolve": "on_resolve",
        "play": "on_play",
        "strike": "on_strike",
        "raze": "on_raze",
        "buy": "on_buy",
        "reroll": "on_reroll",
        "tile": "on_tile",
        "remove_tile": "on_remove_tile",
        "end_turn": "on_end_turn",
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

    def on_place(self, member, data):
        self.match.place(member.id, target(data))

    def on_unplace(self, member, data):
        self.match.unplace(member.id, target(data))

    def on_ready(self, member, data):
        self.match.ready(member.id, flag(data, "done"))

    def on_resolve(self, member, data):
        source = data.get("from")
        if source is not None:
            source = whole_number(source, "Haul source", 0, clamp=False)
        self.match.resolve(member.id, target(data), flag(data, "tool", False), source)

    def on_play(self, member, data):
        x, y = cell(data)
        rotation = whole_number(data.get("rotation", 0), "Rotation", 0, 3, clamp=False)
        remove = data.get("remove", [])
        if not isinstance(remove, list) or len(remove) > 10:
            raise LobbyError("remove must be a list of cards.")
        remove = [whole_number(uid, "Card", 0) for uid in remove]
        self.match.play(member.id, whole_number(data.get("uid"), "Card", 0), x, y, rotation, remove)

    def on_strike(self, member, data):
        self.match.strike(member.id, whole_number(data.get("foe"), "Enemy", 0, 20, clamp=False),
                          one_of(data.get("way"), ("soldiers", "resources"), "Strike with soldiers or resources."),
                          whole_number(data.get("times", 1), "Times", 1, 50, clamp=False))

    def on_raze(self, member, data):
        self.match.raze(member.id, *cell(data, required=True))

    def on_buy(self, member, data):
        self.match.buy(member.id, whole_number(data.get("slot"), "Slot", 0, 20, clamp=False))

    def on_tile(self, member, data):
        kind = one_of(data.get("kind"), ("road", "wall"), "Pick a road or a wall.")
        self.match.place_tile(member.id, kind, *cell(data, required=True))

    def on_remove_tile(self, member, data):
        self.match.remove_tile(member.id, *cell(data, required=True))

    def on_reroll(self, member, data):
        self.match.reroll(member.id)

    def on_end_turn(self, member, data):
        self.match.end_turn(member.id)

    def on_player_removed(self, member):
        self.match.leave(member.id)
        self.check_over()

    def check_over(self):
        if self.match.result is not None:
            self.finish(self.match.result)
