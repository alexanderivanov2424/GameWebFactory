"""Bastion 2: a deck-building city-builder for 1-4 players. Each player grows their own city on a
shared, unbounded grid by drawing cards and spending the resources on them. Endless for now (no
enemies yet): the game goes on until the players vote to end it.

Setup (everyone at once): place your Castle (inside the shown map, at least 5 tiles from other
players' cities), then a House and a Farm next to your buildings. Setup buildings give their
population (the House: 2) but not their "when built" cards; the starting deck covers those.

Resources: temporary ones (wood, stone) are counters in your play area, cleared at the end of
every turn. Permanent ones: food (kept between turns, at most your food storage: the Castle's 5)
and population (each build takes some of it for the turn; shown as available / total).

Starting deck: 4 Wood, 3 Stone, 3 Wheat, 1 King; after your first hand of 5 is dealt, 2 Villagers
are shuffled into your draw pile.

Your turn (everyone at once, or one player at a time: the Turns setting):
- Play resource cards into your play area (Wood +1 wood, Wheat +1 food; Timber is worth 3...).
- King (1 action): draw 2 cards.
- Upkeep cards: Villager: pay 1 food or discard 2 other cards; Hunger: 2 food or discard 3 (then
  it leaves your deck); Starvation: 3 food (then it leaves). Discarding one unplayed (at the end
  of your turn, or to pay for another): Villager adds a Hunger to your deck, Hunger adds a
  Starvation, Starvation costs 1 population and a Villager card (and leaves).
- Structure cards: pay the cost (resources and population) and pick an empty tile next to one of
  your built structures; it's built at the end of your turn (take it back with right-click until
  then). When built it may add cards to your discard pile and give population.
- Structure actions, once each per turn: Storage Yard (1 action): bundle resource cards of one kind
  worth exactly 3 or 5 into one card of that value (the bundled cards leave your deck); Quarry /
  Lumber Mill (free): take a Stone / Wood card into your hand (gone once played or discarded).
- Buy from the market (1 action): Farm, Hut and House are always for sale; the shop shows 3
  cards from a shared shop deck (Storage Yard, Quarry, Lumber Mill), refilled when bought. Bought
  cards go to your discard pile.
- Actions: 1 per turn (the Castle).
- End turn: pick cards to keep in hand; the rest and your play area are discarded, temporary
  resources clear, population is free again, and you draw 5 new cards.

Content (one JSON file per item, documented in content/README.md): content/cards/,
content/structures/, content/resources.json, content/starting-deck.json.

Hidden: your hand, deck order and discard pile. Public: everything else.
Leaving mid-game: the player's built structures stay, their pending builds go; the turn moves on.

Player options:  none
Settings:        {"turns": "together" | "order"}
Game messages (x, y: whole numbers, any sign):
  {"action": "setup", "x", "y"}                     your next setup piece
  {"action": "play", "uid", "x"?, "y"?, "option"?: "pay" | "discard", "cards"?: [uid]}
                                                    a hand card (structures need x, y; upkeep
                                                    needs option, and cards for "discard")
  {"action": "unbuild", "x", "y"}                   take back a build you played this turn
  {"action": "choose", "x", "y", "index", "on"}     toggle an optional card of a pending build
  {"action": "use", "x", "y", "cards"?: [uid]}      a structure's action (Bundle: cards)
  {"action": "buy", "card"?: id, "slot"?: n}        an always-for-sale card, or a shop slot (0-based)
  {"action": "end", "keep"?: [uid]}                 end your turn, keeping those hand cards

Code: this file connects the game to the lobby and type-checks message fields. The rules live
in logic/ (see logic/__init__.py for its modules); Match checks who may act and when.
"""

from gamekit import Choice, LobbyGame, PatchState
from gamekit.validate import LobbyError, whole_number

from .logic import views
from .logic.board import LIMIT
from .logic.match import Match


def cell(data, required=True):
    if data.get("x") is None and data.get("y") is None and not required:
        return None
    return (whole_number(data.get("x"), "Column", -LIMIT, LIMIT, clamp=False),
            whole_number(data.get("y"), "Row", -LIMIT, LIMIT, clamp=False))


def uids(data, key):
    value = data.get(key, [])
    if not isinstance(value, list) or len(value) > 100 or any(type(v) is not int for v in value):
        raise LobbyError("Pick cards from your hand.")
    return value


def text(data, key, limit=40):
    value = data.get(key, "")
    if not isinstance(value, str) or len(value) > limit:
        raise LobbyError(f"Bad {key}.")
    return value


class Game(LobbyGame):
    MIN_PLAYERS = 1
    MAX_PLAYERS = 4
    SYNC = PatchState  # big state (catalog, board): send only what changes
    SETTINGS = {
        "turns": Choice("Turns", default="together", options={"together": "Everyone at once", "order": "One at a time"}),
    }
    ACTIONS = {
        "setup": "on_setup",
        "play": "on_play",
        "unbuild": "on_unbuild",
        "choose": "on_choose",
        "use": "on_use",
        "buy": "on_buy",
        "end": "on_end",
    }

    def __init__(self, room):
        super().__init__(room)
        self.reset_game()

    def reset_game(self):
        self.match = None

    def start_game(self):
        self.match = Match({p.id: p.name for p in self.players}, self.settings)

    def game_state(self):
        return views.public(self.match)

    def private_state(self, member):
        return views.private(self.match, member.id) if member.playing else None

    def on_setup(self, member, data):
        self.match.setup_place(member.id, cell(data))

    def on_play(self, member, data):
        self.match.play(member.id, whole_number(data.get("uid"), "Card", 0), cell(data, required=False),
                        text(data, "option"), uids(data, "cards"))

    def on_unbuild(self, member, data):
        self.match.unbuild(member.id, cell(data))

    def on_choose(self, member, data):
        on = data.get("on")
        if not isinstance(on, bool):
            raise LobbyError("on must be true or false.")
        self.match.choose(member.id, cell(data), whole_number(data.get("index"), "Choice", 0, 20, clamp=False), on)

    def on_use(self, member, data):
        self.match.use(member.id, cell(data), uids(data, "cards"))

    def on_buy(self, member, data):
        if data.get("card") is not None:
            self.match.buy(member.id, card=text(data, "card"))
        else:
            self.match.buy(member.id, slot=whole_number(data.get("slot"), "Slot", 0, 20, clamp=False))

    def on_end(self, member, data):
        self.match.end_turn(member.id, uids(data, "keep"))

    def on_player_removed(self, member):
        self.match.leave(member.id)
