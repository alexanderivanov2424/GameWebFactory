"""Gilded Trail: a deck-building race through the jungle to the golden city (2-4 players).

Board: a chain of hex tiles (logic/board.py), a preset map (maps/*.json) or a random one.
Spaces: jungle (machetes), water (paddles), village (coins), each with a value; rubble
(discard that many cards), base camp (remove that many cards from the game), mountains
(impassable). Start spaces on the first tile, golden city spaces past the last. A blockade
sits on each tile border.

Setup: seats in random order. Everyone starts with 3 Porter (1 machete), 4 Trader (1 coin)
and 1 Boatman (1 paddle), shuffled, and draws 4. One explorer each on a start space; with 2
players, two explorers each (both must arrive). The market shows 6 card types, 3 copies each;
the other types wait in the reserve. Cards: cards/*.json.

Turn (any order):
- Move: play a movement card to step an explorer onto adjacent spaces of its kind while its
  value lasts (a joker acts as any one kind). Starting a new card drops the rest of the old
  one; cards are never combined and a card moves only one explorer. Rubble and base camps
  are paid with cards from hand. No two explorers share a space.
- Blockade: pay it like a space (or discard cards for a rubble one) to take it; the border
  opens for everyone, the explorer doesn't move, and the card may go on with what's left.
- Buy at most one card: coin cards and jokers pay their value, any other card 1/2. Reserve
  cards only while a market slot is empty (the bought card then fills it).
- Play action cards: draw cards, remove cards from the game, take a free card, or step
  ignoring a space's requirement (details in logic/actions.py).
- End turn: played cards and any cards picked from hand are discarded; draw back up to 4.
Single-use cards leave the game once used for their value or effect.
End: when a player's explorers have all arrived, the round finishes. Among arrived players,
most blockades wins, then the highest blockade, then the first to arrive. A player who leaves
is out (their explorers leave the board); the last one left wins.

Player options:  none (colors by seat)
Settings:        {"map": map id or "random", "tiles": 3-9 (random map length),
                  "seed": 0-999999 (random map; 0 = new map each game)}
Game messages:   (only from the player whose turn it is; card uids are numbers, hexes "q,r")
    {"action": "move", "explorer": i, "to": hex, "card"?: uid}   (no card: keep using the current one)
    {"action": "pay", "explorer": i, "to": hex, "cards": [uid...]}   rubble / base camp / rubble blockade
    {"action": "buy", "card": card id, "cards": [uid...]}
    {"action": "play", "card": uid}                                  an action card
    {"action": "trash", "cards": [uid...]}                           after Naturalist / Field Journal
    {"action": "take", "card": card id or null}                      after Courier
    {"action": "guide", "explorer": i, "to": hex or null}            after Local Guide
    {"action": "endTurn", "discard": [uid...]}

Code: this file connects the game to the lobby; the rules live in logic/ (see
logic/__init__.py). State goes out as patches (SYNC = PatchState): the board is big and static.
"""

from gamekit import Choice, Int, LobbyError, LobbyGame, PatchState

from .logic.content import MAPS
from .logic.match import Match

MAX_CARDS = 40  # longest list of uids a message may carry


def uid_list(data, key):
    value = data.get(key, [])
    if type(value) is not list or len(value) > MAX_CARDS or any(type(v) is not int for v in value):
        raise LobbyError("Bad card list.")
    return value


def text_field(data, key, required=True):
    value = data.get(key)
    if value is None and not required:
        return None
    if type(value) is not str or len(value) > 40:
        raise LobbyError(f"Missing or bad {key}.")
    return value


def explorer(data):
    value = data.get("explorer")
    if type(value) is not int:
        raise LobbyError("Pick one of your explorers.")
    return value


class Game(LobbyGame):
    MIN_PLAYERS = 2
    MAX_PLAYERS = 4
    SYNC = PatchState
    SETTINGS = {
        "map": Choice("Map", default=next(iter(MAPS), "random"),
                      options={**{mid: m["name"] for mid, m in MAPS.items()}, "random": "Random"}),
        "tiles": Int("Random map length", default=6, low=3, high=9, suffix=" tiles",
                     hint="Only for the random map."),
        "seed": Int("Random map seed", default=0, low=0, high=999999,
                    hint="Only for the random map. 0 = a new map every game; reuse a seed to replay a map."),
    }
    ACTIONS = {
        "move": "on_move",
        "pay": "on_pay",
        "buy": "on_buy",
        "play": "on_play",
        "trash": "on_trash",
        "take": "on_take",
        "guide": "on_guide",
        "endTurn": "on_end_turn",
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
        if self.match.turn() != member.id:
            raise LobbyError("It's not your turn.")
        await self.dispatch(member, data)

    # Thin wrappers: unpack and type-check, let Match apply the rules, finish if it's over.

    def on_move(self, member, data):
        card = data.get("card")
        if card is not None and type(card) is not int:
            raise LobbyError("Pick a card.")
        self.match.move(member.id, explorer(data), text_field(data, "to"), card)

    def on_pay(self, member, data):
        self.match.pay(member.id, explorer(data), text_field(data, "to"), uid_list(data, "cards"))

    def on_buy(self, member, data):
        self.match.buy(member.id, text_field(data, "card"), uid_list(data, "cards"))

    def on_play(self, member, data):
        card = data.get("card")
        if type(card) is not int:
            raise LobbyError("Pick a card.")
        self.match.play(member.id, card)

    def on_trash(self, member, data):
        self.match.trash(member.id, uid_list(data, "cards"))

    def on_take(self, member, data):
        self.match.take(member.id, text_field(data, "card", required=False))

    def on_guide(self, member, data):
        to = text_field(data, "to", required=False)
        self.match.guide(member.id, explorer(data) if to is not None else 0, to)

    def on_end_turn(self, member, data):
        self.match.end_turn(member.id, uid_list(data, "discard"))
        self.check_over()

    def on_player_removed(self, member):
        self.match.remove(member.id)
        self.check_over()

    def check_over(self):
        if self.match.result is not None:
            self.finish(self.match.result)
