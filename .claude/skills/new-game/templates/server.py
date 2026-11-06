"""{{GAME_NAME}}: TODO one-paragraph description of the rules.

Player options:  TODO e.g. {"color": "#rrggbb"}   (or none)
Settings:        TODO e.g. {"rounds": 3}           (see SETTINGS; or none)
Game messages:   TODO e.g. {"action": "move", ...}

Code: this file connects the game to the lobby (settings, player options, messages, phases,
timers). The rules themselves live in logic/ (see logic/__init__.py for its modules).
"""

from gamekit import Int, LobbyError, LobbyGame  # noqa: F401  (remove unused)
from gamekit.validate import cell, one_of, whole_number  # noqa: F401  (remove unused)

from .logic.match import Match
# Also available: `from gamekit import SecretChoices` (everyone picks in secret, reveal together),
# self.schedule(seconds, fn) (timed pauses; see gamekit/lobby.py) and gamekit.data (JSON content
# files such as cards; put the loader in logic/).


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

    # --- Game: glue between the lobby and logic.Match --------------------------------

    def reset_game(self):
        self.match = None

    def start_game(self):
        # self.players: players in join order. Refer to them by p.id (public id).
        # self.game_number was just increased (clients get it as state.gameNumber).
        self.match = Match({p.id: p.name for p in self.players}, self.settings)

    def game_state(self):
        """Public: everyone (players and spectators) sees this. Only called while playing/finished."""
        return self.match.public()

    def private_state(self, member):
        """Only `member` sees this (hidden hands, secret positions...). Called for spectators too."""
        return self.match.private(member.id) if member.playing else None

    async def on_game_message(self, member, data):
        # Checks shared by every action; then ACTIONS picks the method.
        if self.match.turn() != member.id:
            raise LobbyError("It's not your turn.")
        await self.dispatch(member, data)

    # Action methods: unpack and type-check the message, let Match apply the rules, then
    # finish the game if Match says it's over.

    def move(self, member, data):
        # TODO unpack data (gamekit.validate: whole_number, one_of, cell) and pass it on.
        self.match.move(member.id)
        self.check_over()

    def on_player_removed(self, member):
        self.match.remove(member.id)
        self.check_over()

    def check_over(self):
        if self.match.result is not None:
            self.finish(self.match.result)
