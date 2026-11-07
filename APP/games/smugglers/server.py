"""Smugglers: one player is Interpol, everyone else smuggles goods between planets.

Board: planets joined by routes; a route of length L has L-1 dots, and ships may stop on
dots. Nodes are planets and dots; one step = one route segment. Boards are swappable JSON
files (content/boards/); planets are a name and art (a distinct color for now).

Setup: Interpol is picked at random. Each smuggler gets 5 goods cards in hand, 0 credits and
2 ship tiles (name + speed) dealt from the ship tiles, on the board's start planets. Contracts
are generated from the board (`contractsEach` per smuggler); 5 are face up, each with its cargo token on
its source planet. Interpol starts with Funding x3, Patrol, Barrier (one patrol ship at
Interpol's home planet, one barrier off the board) and draws 3.

Turns: the smugglers in random order, then Interpol; a round ends after Interpol's turn.
- Smuggler turn: each ship gets one action:
  - move: up to its speed. Ships can't enter or pass barriers. A loaded ship that enters a
    patrol's or a checkpoint's spot stops there and is inspected (see Inspection).
  - pick up: at a planet with a cargo token, with an empty ship: draw 5 goods, then load:
    put 1+ cards from hand on the ship face down, declare a legal good type (public), and
    discard down to 5 in hand. The cargo token moves to the ship.
  Delivering is free: a ship carrying a contract's token at that contract's destination
  completes it for credits = (cards in its largest set of one legal good) x (that good's value)
  + the contract's bonus if that good is the contract's good + each illegal good's value.
  The cargo is discarded and a new contract is revealed. The turn ends with End turn, or by
  itself once no ship can act or deliver.
- Interpol turn (deck-building): 1 action, 1 buy, budget 0. Play cards from the hand of 3
  (action cards cost an action, funding cards don't), buy one card from the market with the
  budget, then End turn: everything is discarded and 3 new cards drawn (the discard pile is
  reshuffled when the deck runs out). Cards: content/interpol/*.json; effects in
  logic/interpol.py (draw, +actions, +budget, Repeat, and pieces: barrier, checkpoint,
  patrol). Each piece card owned is one piece on the board.
Inspection: whenever a loaded ship is on a spot with a patrol or checkpoint (it flew in,
loaded cargo there, or Interpol moved or placed the piece onto it; several ships are inspected
one after another; empty ships never are): the owner offers a bribe
(0..credits), then Interpol lets the ship pass (taking the bribe) or inspects it. Every card
that isn't the declared good is seized; the owner pays `legalFine` per seized legal good plus
each seized illegal good's penalty (not below 0 credits). Interpol scores bribes, fines and
the value of seized goods. A ship left empty returns its cargo token to the source planet.

End: when every contract is delivered, or after `roundLimit` rounds. The richest smuggler
wins (ties share the win), unless Interpol's score is higher. If Interpol leaves, the richest
smuggler wins; if every smuggler leaves, Interpol wins. A smuggler who leaves loses their
ships (cargo tokens go back to their planets).

Player options:  none (smuggler colors are given by seat)
Settings:        {"contractsEach": 2-12 (total contracts = this x smugglers), "legalFine": 0-5,
                 "roundLimit": 5-80}
Game messages:   (only from match.actor(); ship ids "s1".., card uids are numbers)
    {"action": "move", "ship": id, "to": node}
    {"action": "pickup", "ship": id, "contract": "c3"}
    {"action": "load", "load": [uid...], "discard": [uid...], "declare": good id}
    {"action": "deliver", "ship": id}
    {"action": "endTurn"}
    {"action": "play", "card": uid, "copy"?: uid, "piece"?: id, "to"?: node}
    {"action": "buy", "card": card id}
    {"action": "bribe", "amount": n}
    {"action": "decide", "inspect": true|false}

Code: this file connects the game to the lobby; the rules live in logic/ (see
logic/__init__.py). State goes out as patches (SYNC = PatchState): the board is big and static.
"""

from gamekit import Int, LobbyError, LobbyGame, PatchState
from gamekit.validate import whole_number

from .logic.match import Match

MAX_CARDS = 30  # longest list of uids a message may carry


def text_field(data, key, required=True):
    value = data.get(key)
    if value is None and not required:
        return None
    if type(value) is not str or len(value) > 40:
        raise LobbyError(f"Missing or bad {key}.")
    return value


def uid_list(data, key):
    value = data.get(key, [])
    if type(value) is not list or len(value) > MAX_CARDS or any(type(v) is not int for v in value):
        raise LobbyError(f"Bad {key} list.")
    return value


class Game(LobbyGame):
    MIN_PLAYERS = 2
    MAX_PLAYERS = 6
    SYNC = PatchState
    SETTINGS = {
        "contractsEach": Int("Contracts per smuggler", default=5, low=2, high=12,
                             hint="Total contracts = this × the number of smugglers."),
        "legalFine": Int("Fine per seized legal good", default=1, low=0, high=5, suffix=" credits"),
        "roundLimit": Int("Round limit", default=40, low=5, high=80,
                          hint="Ends the game if the contracts take too long."),
    }
    ACTIONS = {
        "move": "on_move",
        "pickup": "on_pickup",
        "load": "on_load",
        "deliver": "on_deliver",
        "endTurn": "on_end_turn",
        "play": "on_play",
        "buy": "on_buy",
        "bribe": "on_bribe",
        "decide": "on_decide",
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
        if self.match.actor() != member.id:
            raise LobbyError("It's not your turn.")
        await self.dispatch(member, data)

    # Thin wrappers: unpack and type-check, let Match apply the rules, finish if it's over.

    def on_move(self, member, data):
        self.match.move(member.id, text_field(data, "ship"), text_field(data, "to"))
        self.check_over()

    def on_pickup(self, member, data):
        self.match.pickup(member.id, text_field(data, "ship"), text_field(data, "contract"))

    def on_load(self, member, data):
        self.match.load(member.id, uid_list(data, "load"), uid_list(data, "discard"), text_field(data, "declare"))
        self.check_over()

    def on_deliver(self, member, data):
        self.match.deliver(member.id, text_field(data, "ship"))
        self.check_over()

    def on_end_turn(self, member, data):
        self.match.end_turn(member.id)
        self.check_over()

    def on_play(self, member, data):
        uid = data.get("card")
        if type(uid) is not int:
            raise LobbyError("Pick a card.")
        copy = data.get("copy")
        if copy is not None and type(copy) is not int:
            raise LobbyError("Pick a card to repeat.")
        targets = {
            "copy": copy,
            "piece": text_field(data, "piece", required=False),
            "to": text_field(data, "to", required=False),
        }
        self.match.play(member.id, uid, targets)
        self.check_over()

    def on_buy(self, member, data):
        self.match.buy(member.id, text_field(data, "card"))

    def on_bribe(self, member, data):
        self.match.bribe(member.id, whole_number(data.get("amount"), "The bribe", clamp=False, low=0))

    def on_decide(self, member, data):
        search = data.get("inspect")
        if type(search) is not bool:
            raise LobbyError("Inspect or let it pass?")
        self.match.decide(member.id, search)
        self.check_over()

    def on_player_removed(self, member):
        self.match.remove(member.id)
        self.check_over()

    def check_over(self):
        if self.match.result is not None:
            self.finish(self.match.result)
