"""Bastion: a co-op siege defense deck-builder for 1-4 players. Hold the keep through 10 levels.

The board (a map from content/maps/, picked by the host) is shared: grass to build on, rocks,
water and forest, the keep, and two roads that enemies walk down towards the keep. The "main"
road is used from level 1; the "flank" road joins in from level 6 (each level's file says which
roads its waves use, and the client shows them before the level). The keep starts with the
host's "Keep health"; at 0 the game is lost. Holding all 10 levels (content/levels/) wins.

Each level: a few build turns (the level's "buildTurns"), then the siege, then the market.
- Build turn (simultaneous): everyone discards their hand, draws 5 cards, gets 3 labor (+ their
  quarries) and gold from their farms. Play cards from your hand in any order while you have
  the labor (each card's "labor" cost):
  - Structure cards build on an empty cell: walls, spike pits and tar pits go on the road (never
    on a road's first cell, where enemies enter); everything else on grass; barracks must be
    next to the road. Playing a structure card on the same kind of structure upgrades it a
    level (max 3 for most) and repairs it. Structures belong to whoever built them (farm and
    quarry income goes to the owner); anyone may upgrade anyone's.
  - Order cards have an effect (labor, draws, gold, repairs, help for teammates, upgrades).
  - Demolish one of your structures for free.
  Then End turn (it can be taken back until everyone has ended). When everyone has ended, the
  next build turn starts, or after the last one the siege.
- Siege: the level's waves walk the roads; towers shoot, walls and soldiers block, traps hurt
  and slow (logic/battle.py has the exact tick rules). Enemies reaching the keep take their
  "keep" damage off its health. It is simulated at once on the server and sent as a replay
  (game.battle) for the client to animate. Walls keep their damage; destroyed walls are gone.
  Enemy health is scaled by the difficulty (easy 75%, normal 100%, hard 130%) and +40% per
  player after the first (game.hpScale).
- Market (after a siege held, simultaneous): everyone gets the level's reward in gold, chapels
  heal the keep and repair walls next to them, and 6 cards are on offer (cards unlock over the
  levels). Buy any number (copies are unlimited; bought cards go to your discard pile) and retire
  at most one card from your deck for 1 gold (decks keep at least 5 cards). Then Done; when
  everyone is done, the next level starts.
Everyone starts with the same 8 cards (content/starting-deck.json) and 2 gold.

Leaving mid-game: the player's cards are gone and their structures pass to the first remaining
player; enemies are scaled for the players left. If nobody is left the game ends (lost).

Hidden: your hand and your deck's order (state.private: hand, owned cards, whether you retired
this market). Public: everyone's labor, gold, done status, hand/draw/discard sizes and whole deck
(sorted), the board, the keep, the market, the log and the last siege replay.

Content (one JSON file per item, documented in content/README.md): content/cards/,
content/enemies/, content/levels/, content/maps/, content/starting-deck.json.

Player options:  none
Settings:        {"difficulty": "easy" | "normal" | "hard" ("normal"),
                  "keepHealth": 10-60 (30), "map": map id ("valley")}
Game messages:
    {"action": "play", "uid": n, "x"?: col, "y"?: row}   a hand card; structures and targeted
                                                         orders need the cell
    {"action": "demolish", "x": col, "y": row}           one of your structures
    {"action": "end_turn", "done"?: bool}                build turns (false takes it back)
    {"action": "buy", "slot": n}                         market: an offer (0-based)
    {"action": "retire", "uid": n}                       market: a card you own
    {"action": "ready", "done"?: bool}                   market: done shopping (false takes it back)

Code: this file connects the game to the lobby and type-checks message fields. The rules live
in logic/ (see logic/__init__.py for its modules); Match checks stages and who may act.
"""

from gamekit import Choice, Int, LobbyGame, PatchState
from gamekit.validate import LobbyError, whole_number

from .logic.maps import DEFAULT, MAPS, MAX_SIZE
from .logic.match import DIFFICULTY, Match


def cell(data):
    """Optional x, y (both or neither)."""
    if data.get("x") is None and data.get("y") is None:
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
    SYNC = PatchState  # the siege replay is big: send it once, then only what changes
    SETTINGS = {
        "difficulty": Choice("Difficulty", default="normal",
                             options={"easy": "Easy", "normal": "Normal", "hard": "Hard"},
                             hint=" · ".join(f"{k.title()}: enemy health {round(v * 100)}%" for k, v in DIFFICULTY.items())),
        "keepHealth": Int("Keep health", default=30, low=10, high=60),
        "map": Choice("Map", default=DEFAULT, options={k: m.name for k, m in MAPS.items()}),
    }
    ACTIONS = {
        "play": "on_play",
        "demolish": "on_demolish",
        "end_turn": "on_end_turn",
        "buy": "on_buy",
        "retire": "on_retire",
        "ready": "on_ready",
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
        await self.dispatch(member, data)  # Match checks the stage and the player
        self.check_over()

    def on_play(self, member, data):
        x, y = cell(data)
        self.match.play(member.id, whole_number(data.get("uid"), "Card", 0), x, y)

    def on_demolish(self, member, data):
        x, y = cell(data)
        if x is None:
            raise LobbyError("Pick a structure to demolish.")
        self.match.demolish(member.id, x, y)

    def on_end_turn(self, member, data):
        self.match.end_turn(member.id, flag(data, "done"))

    def on_buy(self, member, data):
        self.match.buy(member.id, whole_number(data.get("slot"), "Slot", 0, 50, clamp=False))

    def on_retire(self, member, data):
        self.match.retire(member.id, whole_number(data.get("uid"), "Card", 0))

    def on_ready(self, member, data):
        self.match.ready(member.id, flag(data, "done"))

    def on_player_removed(self, member):
        self.match.leave(member.id)
        self.check_over()

    def check_over(self):
        if self.match.result is not None:
            self.finish(self.match.result)
