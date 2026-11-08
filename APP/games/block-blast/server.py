"""Block Blast: a turn-based tile-placing deck-builder for 2-4 players. Last one standing wins.

Every player has a 9x9 board (empty at the start), health, gold, shield and card removals.
Cards place tiles (up to 5x5) and symbols on them; tiles and symbols are separate ideas:
- Tile types decide how a tile behaves: blue (plain), grey (can't be spoiled), goblin (the
  purple tile: spoils the lines it's in). logic/tiles.py.
- Symbols act when their cell is cleared: coin, attack, shield, chapel, siege (below). The goblin
  face is a decorative symbol with no effect. Any symbol can sit on any tile type.
  logic/symbols.py, effects in logic/effects.py.
Card files: cards/README.md. Boards and card rotations reach clients as two layers,
{"tiles": [rows of tile codes], "symbols": [rows of symbol codes]} ("." = none), with the code
tables in game.tileTypes and game.symbolTypes; game.rules holds the constants the client needs
(boardSize, handSize, buysPerTurn, siegePerStrength, patch: the 1x1 patch tile as layers). The
help window's legend reads tileTypes[code].help and game.symbolHelp (symbol name -> text).

Setup: turn order is random. Everyone's deck is the starting deck (Square: a 2x2 with a shield
in one corner, Hook: an L with an attack in its corner, Tee: a T with a coin on its left arm,
a bar of 4 with a shield, a bar of 3 with an attack at one end and a bar of 2 with a coin
at one end), shuffled; everyone draws 3. Starting gold
follows turn order: 1 for the first player, 2 for the second, and so on.

Card packs: the host picks which packs of bonus cards make up the market's pool, the bonus deck
(cards/packs/, logic/packs.py; at least one, all by default): Base cards (coins, attacks,
shields), Chapel cards, Goblin cards and Siege cards. Most cards come in 2 copies, goblin and
siege cards in 1.

Market: the shared pool of bonus cards, dealt face up from the shuffled bonus deck. Cards bought
or removed never return to it. The host picks its type and each type's size (logic/market/):
- Conveyor Market (5 cards by default, 1-10): a card's price is its slot position: slot 1 costs
  1 gold ... the last slot costs its size. A bought slot stays empty until the end of the turn;
  then the remaining cards shift towards slot 1 and new ones fill the empty slots at the end.
- Cost Market (10 cards by default, 1-20): any card can be bought for its own cost (each card
  file's "cost"). Instead of buying, a player may remove a card from the market: it leaves the
  game. Empty slots refill in place at the end of the turn.
New cards stop coming once the bonus deck runs out.

On your turn, in any order (place and patch as often as you like):
- Place: play a hand card, putting its shape on your board. Shapes may be rotated in quarter
  turns but never mirrored; every tile must land on an empty cell of the board.
- Patch: discard a hand card to place a blank 1x1 tile instead.
- Goblin cards (purple, from the market) are placed the same way but on an opponent's board (one
  still in), then leave your deck. Their tiles need not touch.
  A cleared row or column holding a goblin (purple) tile has no effect (its symbols give nothing, unless
  another cleared, goblin-free line crosses that cell), except on grey tiles: goblins never
  spoil those. Siege cards are grey. Lines a goblin completes clear too.
- Buy (once per turn): take a market card for its price. Bought cards go to your discard pile.
  In the Cost Market, removing a card from the market instead counts as your buy.
Played and patched cards go to your discard pile. After each placement, every full row and
column on your board clears at once (a cell where a row and a column cross counts once). Each
symbol on a cleared cell:
- coin: +1 gold.
- attack: 1 damage to your target. The target's shield absorbs damage first, point for point,
  and is used up doing so; the rest comes off their health.
- shield: +1 shield. Shield also drops by 1 at the start of each of your turns.
- chapel: +1 card removal. Spend one at any time (also on other players' turns) to remove a card
  in your hand from your deck for good (not discarded).
- siege: every 3 siege symbols cleared (counted across clears) give +1 strength. Each point of
  strength adds 1 to the total damage of each of your attacks (a clear with attack symbols:
  2 attack symbols do 3 damage with strength 1); strength gained in a clear applies from the
  next clear on.
Cards marked with the discard icon (goblin and siege cards) leave your deck for good once played
(they still go to the discard pile when patched). Siege cards are 4x4 with 3 separate siege tiles
and go on your own board.
Then End turn: you draw back up to 3 cards (your discard pile is shuffled into a new draw pile
when it runs out; cards you didn't play stay in your hand) and the market refills.

Target: each player aims at one opponent (shown to everyone), changeable at any time, also on
other players' turns; it starts as the next player in turn order and moves on by itself when
the target is out. At 0 health a player is out (off the turn order, board greyed). The last
player left wins. A player who leaves mid-game is out the same way; if it was their turn, the
market refills and the turn passes.

Hidden: hands and the order of draw piles (state.private: your hand, and your draw pile's
contents sorted). Everything else is public: boards, health, gold, shield, card removals, siege,
strength, targets, hand/draw/discard sizes, each player's whole deck (seats[pid].deck: every card
they own, hand and piles together, sorted by cost then name so it doesn't say where each one is),
the market, the log.

Player options:  none
Settings:        {"health": 1-50 (10), "market": "conveyor" | "cost" ("conveyor"),
                  "conveyorSize": 1-10 (5), "costSize": 1-20 (10),
                  "packs": [pack ids, at least 1] (all: ["base", "chapel", "goblin", "siege"])}
Game messages:
    {"action": "place", "uid": n, "rotation": 0-3, "row": r, "col": c}
        a hand card's shape, turned `rotation` quarter turns clockwise (card.rotations[rotation]
        in the state), with its top-left corner at (row, col); goblin cards add
        "player": "<public id>", the opponent whose board it goes on
    {"action": "patch", "uid": n, "row": r, "col": c}    discard a hand card for a 1x1 tile
    {"action": "buy", "slot": n}                         0 to the market's size - 1
    {"action": "market_remove", "slot": n}               Cost Market: remove that card instead of
                                                         buying (uses the turn's buy)
    {"action": "aim", "player": "<public id>"}           any time while you're in
    {"action": "remove", "uid": n}                       spend a card removal on a hand card;
                                                         any time while you're in
    {"action": "end_turn"}

Code: this file connects the game to the lobby (settings, messages, phases) and type-checks
message fields. The rules live in logic/ (see logic/__init__.py for its modules); Match decides
whose turn it is and which actions are allowed off-turn.
"""

from gamekit import Choice, Int, LobbyGame, MultiChoice
from gamekit.validate import whole_number

from .logic import market
from .logic.packs import PACKS
from .logic.board import SIZE
from .logic.match import Match


def position(data, key, label):
    return whole_number(data.get(key), label, 0, SIZE - 1, clamp=False)


def card_uid(data):
    return whole_number(data.get("uid"), "Card", 0)


def market_slot(data):
    return whole_number(data.get("slot"), "Slot", 0, market.MAX_SIZE - 1, clamp=False)  # Match checks the size


def market_settings():
    """The market type (one option per market.MARKETS entry) and each type's size."""
    types = market.MARKETS.values()
    settings = {"market": Choice("Market", default=market.DEFAULT, options={m.KEY: m.LABEL for m in types},
                                 hint=" · ".join(f"{m.LABEL}: {m.RULES}" for m in types))}
    for m in types:
        settings[m.SIZE_SETTING] = Int(f"{m.LABEL} size", default=m.DEFAULT_SIZE, low=1, high=m.MAX_SIZE,
                                       hint=f"Cards on offer in the {m.LABEL}")
    return settings


class Game(LobbyGame):
    MIN_PLAYERS = 2
    MAX_PLAYERS = 4
    SETTINGS = {
        "health": Int("Starting health", default=10, low=1, high=50),
        **market_settings(),
        "packs": MultiChoice("Card packs", default=list(PACKS), options={p["id"]: p["name"] for p in PACKS.values()},
                             low=min(1, len(PACKS)), hint=" · ".join(f"{p['name']}: {p['description']}" for p in PACKS.values())),
    }
    ACTIONS = {
        "place": "on_place",
        "patch": "on_patch",
        "buy": "on_buy",
        "market_remove": "on_market_remove",
        "aim": "on_aim",
        "end_turn": "on_end_turn",
        "remove": "on_remove_card",
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
        await self.dispatch(member, data)  # Match checks turns (some actions are allowed any time)
        self.check_over()  # any action that knocks someone out can end the game

    def on_place(self, member, data):
        rotation = whole_number(data.get("rotation"), "Rotation", 0, 3, clamp=False)
        board = data.get("player")  # goblin cards: the opponent whose board it goes on
        self.match.place(member.id, card_uid(data), rotation, position(data, "row", "Row"), position(data, "col", "Column"),
                         board if isinstance(board, str) else None)

    def on_patch(self, member, data):
        self.match.patch(member.id, card_uid(data), position(data, "row", "Row"), position(data, "col", "Column"))

    def on_buy(self, member, data):
        self.match.buy(member.id, market_slot(data))

    def on_market_remove(self, member, data):
        self.match.market_remove(member.id, market_slot(data))

    def on_aim(self, member, data):
        self.match.aim(member.id, data.get("player"))

    def on_remove_card(self, member, data):
        self.match.remove_card(member.id, card_uid(data))

    def on_end_turn(self, member, data):
        self.match.end_turn(member.id)

    def on_player_removed(self, member):
        self.match.leave(member.id)
        self.check_over()

    def check_over(self):
        if self.match.result is not None:
            self.finish(self.match.result)
