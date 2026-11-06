"""TODO Game name: one-paragraph description of the rules.

Player options:  TODO e.g. {"color": "#rrggbb"}   (or none)
Settings:        TODO e.g. {"rounds": 3}           (see SETTINGS; or none)
Game messages:   TODO e.g. {"action": "move", ...}
"""

import random

from gamekit import PLAYING, Int, LobbyError, LobbyGame, TurnQueue  # noqa: F401
from gamekit.validate import cell, one_of, whole_number  # noqa: F401  (remove unused)
# Also available: `from gamekit import SecretChoices` (everyone picks in secret, reveal together),
# self.schedule(seconds, fn) (timed pauses; see gamekit/lobby.py), gamekit.data (JSON content
# files such as cards), and modules of your own next to this file (`from . import rules`).


class Game(LobbyGame):
    MIN_PLAYERS = 2
    MAX_PLAYERS = 8
    # Host settings: validated on the server and drawn by AppLobbyUI.settingsForm on the client.
    SETTINGS = {
        "rounds": Int("Rounds", default=3, low=1, high=10),  # TODO
    }
    # Game messages: {"action": name} -> method(member, data). Unknown actions are rejected.
    ACTIONS = {
        "move": "move",  # TODO
    }

    def __init__(self, room):
        super().__init__(room)
        self.reset_game()

    # --- Lobby (delete hooks you don't need) -----------------------------------------

    def default_options(self, member):
        return {}  # TODO

    def clean_options(self, member, options):
        # TODO validate player input; raise LobbyError (e.g. "already taken").
        return dict(member.options)

    def start_check(self):
        return None  # TODO return a reason string if the game can't start

    # --- Game ------------------------------------------------------------------

    def reset_game(self):
        self.names = {}  # public id -> name, fixed at the start
        self.queue = TurnQueue()
        # TODO other game state

    def start_game(self):
        # self.players: players in join order. Refer to them by p.id (public id).
        # self.game_number was just increased (clients get it as state.gameNumber).
        self.names = {p.id: p.name for p in self.players}
        order = list(self.names)
        random.shuffle(order)
        self.queue = TurnQueue(order)  # cost 1 per action = round-robin
        # TODO build the game state from self.settings

    def game_state(self):
        """Public: everyone (players and spectators) sees this."""
        return {
            "names": self.names,
            "turnOrder": self.queue.order(),
            "turn": self.queue.current() if self.phase == PLAYING else None,
            # TODO public game state (JSON-safe; public ids only)
        }

    def private_state(self, member):
        """Only `member` sees this (hidden hands, secret positions...). Delete if unused."""
        return None

    async def on_game_message(self, member, data):
        # Checks shared by every action; then ACTIONS picks the method.
        if self.queue.current() != member.id:
            raise LobbyError("It's not your turn.")
        await self.dispatch(member, data)

    def move(self, member, data):
        # TODO validate (type(x) is int, ranges; see gamekit.validate), then apply.
        # When the game ends: self.finish({"winner": member.id, "reason": None})
        self.queue.advance(member.id)  # pass a cost for counter-based turns

    def on_player_removed(self, member):
        if member.id not in self.queue:
            return
        self.queue.remove(member.id)
        if len(self.queue) == 1:
            self.finish({"winner": self.queue.current(), "reason": "Everyone else left."})
