"""Bastion: a co-op city-builder deck-builder for 1-4 players. Grow a city whose buildings feed
each other, then beat every enemy that comes for it.

The board (a map from content/maps/, picked by the host) is shared: grass to build on, forest,
mountains and water. The game starts with a small town: a 1x1 keep, a few roads, a lumbermill
and a workshop. The team shares one stockpile (gold, wood, stone, ore, food, tools), its
soldiers and the keep's health (the host's "Keep health"; at 0 the game is lost).

Rounds (everyone plays at once, in any order): each round everyone discards their hand and
draws 5. Play cards from your hand, buy from the market, fight; then End turn (it can be taken
back until everyone has ended). When everyone has ended, the round ends.
- Blueprints (bought in the market) build a structure: place its shape on empty grass, turned
  any of 4 ways (never mirrored), and pay its cost from the stockpile. Buildings may also go
  over road tiles (replacing them) unless goods wait on them. The blueprint then leaves your
  deck (roads and walls stay) and, if the building is worked, its crew card joins your deck
  (cottages give Villagers, storage yards Haul, watchtowers Lookout, chapels Absolution).
  Some buildings must go next to something (a mine next to a mountain, a lumbermill next to
  forest).
- Working: a work card (a crew card, Villagers for any building) makes one building produce
  once this round. Output = base + adjacency bonuses (each building's file lists what it likes
  or hates next to it: terrain, empty grass, roads, walls, other buildings) - 1 per enemy
  blight tile next to it. Villagers are unskilled: base output and penalties, no bonuses.
  Buildings that use inputs take them from the stockpile.
- Goods: a building next to the keep or a storage yard (a depot) delivers to the stockpile
  at once; others keep their goods (up to 6) until a Haul card carries them along roads that
  reach a depot. A haul moves a number of goods (the card's, +1 per cottage) a number of cells
  each; goods that don't reach a depot are left on the road tile they stopped on, where the
  next haul picks them up first and raids (loot) can take them unless the tile is next to a
  wall or near a watchtower. A building with inputs must be next to a depot or a road that
  reaches one. Gold, soldiers, keep health and cures never wait.
- Other actions: haul, repair a damaged building (1 wood per ruined tile), cure a plagued one,
  gain resources or soldiers (Sell: tools for gold; Tax: gold, but it adds an Unrest curse),
  draw cards, remove other cards in your hand from your deck for good (Absolution; not
  curses). Each card says what it does and costs.
- Market: 6 cards anyone may buy at any time with the team's gold (unlimited copies: a bought
  slot is refilled at once); bought cards go to the buyer's discard pile.
End of a round: the keep makes 1 gold, then every active enemy makes its next attack (each
has 2-3 it takes in turn), then the next round starts; an enemy that is due arrives.

Enemies are cards above the board. The first arrives on round peaceRounds + 1, then one every
enemyGap rounds ("enemies" in all; lower tiers first, a boss last). Each has its own ways to
be beaten (on its card): soldiers per damage, resources per damage (Frost Witch: wood), curing
the plague it spread (Rat King), paying off the curse cards it sends (Bandit Lord), razing its
lair tiles with soldiers (Necromancer). Attacks steal from the stockpile, ruin building tiles
(not ones next to a wall or near a watchtower; with none open they break a wall), damage the
keep, loot goods left on unprotected roads, put blight tiles on the board (raze one with 1 soldier), add curse cards to decks (pay
their cost to play them and remove them for good), plague or freeze buildings, kill soldiers.
Enemy health scales with difficulty (75/100/130%) and +50% per player after the first.
Beating every enemy wins. The keep at 0, or any enemy left 6 rounds after the last one
arrived, loses.

Leaving mid-game: the player's cards are gone; their buildings stay. If nobody is left the
game ends (lost).

Hidden: your hand and your deck's order. Public: everything else (each player's whole deck,
sorted; the next enemies only show when they arrive).

Content (one JSON file per item, documented in content/README.md): content/structures/,
content/cards/, content/enemies/, content/maps/, content/starting-deck.json.

Player options:  none
Settings:        {"difficulty": "easy" | "normal" | "hard" ("normal"), "keepHealth": 10-40 (20),
                  "map": map id ("valley"), "enemies": 3-7 (5), "peaceRounds": 2-8 (5),
                  "enemyGap": 2-5 (3)}
Game messages:
    {"action": "play", "uid": n, "x"?: col, "y"?: row, "rotation"?: 0-3, "remove"?: [uid, ...]}
                       a hand card; blueprints need x, y (top-left of the turned shape) and
                       rotation; work/repair/cure cards need x, y on the building; trash cards
                       (Absolution) list the other hand cards to remove in "remove"
    {"action": "strike", "foe": i, "way": "soldiers" | "resources", "times"?: n (1)}
    {"action": "raze", "x": col, "y": row}        an enemy tile, with soldiers
    {"action": "buy", "slot": n}                  a market card (0-based)
    {"action": "end_turn", "done"?: bool}         false takes it back

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


def flag(data, key):
    value = data.get(key, True)
    if not isinstance(value, bool):
        raise LobbyError(f"{key} must be true or false.")
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
        "play": "on_play",
        "strike": "on_strike",
        "raze": "on_raze",
        "buy": "on_buy",
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
        await self.dispatch(member, data)  # Match checks the player and the turn
        self.check_over()

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

    def on_end_turn(self, member, data):
        self.match.end_turn(member.id, flag(data, "done"))

    def on_player_removed(self, member):
        self.match.leave(member.id)
        self.check_over()

    def check_over(self):
        if self.match.result is not None:
            self.finish(self.match.result)
