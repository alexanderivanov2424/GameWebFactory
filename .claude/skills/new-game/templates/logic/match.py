"""{{GAME_NAME}}: Match, one game from start to finish (no lobby, network or members).

    match = Match({"p1": "Ann", "p2": "Bob"}, settings)   # names fixed at the start
    match.turn()             # public id of the player to act, or None once over
    match.move(pid)          # TODO apply an action; raises LobbyError if it's not allowed
    match.remove(pid)        # pid left mid-game
    match.public()           # JSON-safe state for everyone (server.py's game_state)
    match.private(pid)       # pid's secrets, or None (server.py's private_state)
    match.result             # None while playing; then {"winner": pid or None, "reason": ...}
"""

import random

from gamekit import LobbyError, TurnQueue  # noqa: F401  (remove unused)


class Match:
    def __init__(self, names, settings, rng=random):
        self.names = dict(names)  # public id -> name, fixed at the start (the log stays readable)
        self.settings = dict(settings)
        order = list(self.names)
        rng.shuffle(order)
        self.queue = TurnQueue(order)  # cost 1 per action = round-robin
        self.result = None
        # TODO build the game state from self.settings

    def turn(self):
        return self.queue.current() if self.result is None else None

    # --- Actions (validated values in, rules applied; raise LobbyError to refuse) ----------

    def move(self, pid):
        # TODO check the move against the rules (raise LobbyError("...") to refuse), apply it,
        # and end the game with self.end(winner, reason) when it's over.
        if pid in self.queue:  # an action can remove its own player (e.g. a mine)
            self.queue.advance(pid)  # pass a cost for counter-based turns

    def remove(self, pid):
        if pid not in self.queue:
            return
        self.queue.remove(pid)
        if self.result is None and len(self.queue) == 1:
            self.end(self.queue.current(), "Everyone else left.")

    def end(self, winner, reason=None):
        self.result = {"winner": winner, "reason": reason}

    # --- What clients see ------------------------------------------------------------------

    def public(self):
        return {
            "names": self.names,
            "turnOrder": self.queue.order(),
            "turn": self.turn(),
            # TODO public game state (JSON-safe; public ids only; dicts keyed by id)
        }

    def private(self, pid):
        return None  # TODO hidden hands, secret positions...; delete if the game has none
