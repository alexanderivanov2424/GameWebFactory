"""Arena: a small real-time demo. Each player is a colored circle in a fixed 800x500 arena,
moved with WASD or the arrow keys. Circles may overlap. Each circle shows its player's name
and ping. The host ends the round whenever they like. 1-16 players, 20 ticks per second.

Player options:  none
Settings:        none
Input messages:  {"type": "input", "keys": ["up", "left", ...]}  (keys held: at most 4
                 distinct strings of "up", "down", "left", "right"; sent by realtime.js)
Game messages:   {"action": "end"}   host only: finishes the round
Public state:    {"arena": {"w", "h", "r"}, "dots": {public id: {"x", "y", "name", "color", "ping"?}}}
Result:          {"reason": "The host ended the round."}
"""

import math

from gamekit import LobbyError, RealtimeGame
from gamekit.sync import quantize

ARENA_W = 800
ARENA_H = 500
RADIUS = 18
SPEED = 220  # units per second
PALETTE = [
    "#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4", "#42d4f4", "#f032e6", "#bfef45",
    "#fabed4", "#469990", "#dcbeff", "#9a6324", "#fffac8", "#800000", "#aaffc3", "#808000",
]
DIRECTIONS = ("up", "down", "left", "right")


class Game(RealtimeGame):
    MIN_PLAYERS = 1
    MAX_PLAYERS = 16
    TICK_RATE = 20
    SETTINGS = {}
    ACTIONS = {"end": "end_round"}

    def __init__(self, room):
        super().__init__(room)
        self.reset_game()

    def reset_game(self):
        self.pos = {}  # public id -> [x, y]
        self.names = {}  # public id -> name, fixed at the start
        self.colors = {}  # public id -> color, fixed at the start

    def start_game(self):
        players = self.players
        self.names = {p.id: p.name for p in players}
        self.colors = {p.id: PALETTE[i % len(PALETTE)] for i, p in enumerate(players)}
        # Spread evenly on an ellipse (a single player starts in the middle).
        n = len(players)
        self.pos = {}
        for i, p in enumerate(players):
            p.input = {}
            if n == 1:
                self.pos[p.id] = [ARENA_W / 2, ARENA_H / 2]
                continue
            angle = 2 * math.pi * i / n - math.pi / 2
            self.pos[p.id] = [
                ARENA_W / 2 + (ARENA_W / 2 - 3 * RADIUS) * math.cos(angle),
                ARENA_H / 2 + (ARENA_H / 2 - 3 * RADIUS) * math.sin(angle),
            ]

    def on_input(self, member, data):
        keys = data.get("keys")
        if (
            type(keys) is not list
            or len(keys) > 4
            or len(set(k for k in keys if type(k) is str)) != len(keys)
            or any(k not in DIRECTIONS for k in keys)
        ):
            raise LobbyError("Bad input.")
        member.input = {"keys": set(keys)}

    def tick(self, dt):
        for p in self.players:
            if p.id not in self.pos:
                continue
            keys = p.input.get("keys", ())
            dx = ("right" in keys) - ("left" in keys)
            dy = ("down" in keys) - ("up" in keys)
            if not dx and not dy:
                continue
            length = math.hypot(dx, dy)
            pos = self.pos[p.id]
            pos[0] = min(ARENA_W - RADIUS, max(RADIUS, pos[0] + dx / length * SPEED * dt))
            pos[1] = min(ARENA_H - RADIUS, max(RADIUS, pos[1] + dy / length * SPEED * dt))

    def game_state(self):
        dots = {}
        for p in self.players:
            if p.id not in self.pos:
                continue
            x, y = self.pos[p.id]
            dot = {
                "x": quantize(x, 0.1), "y": quantize(y, 0.1),
                "name": self.names[p.id], "color": self.colors[p.id],
            }
            if p.ping is not None:
                dot["ping"] = p.ping
            dots[p.id] = dot
        return {"arena": {"w": ARENA_W, "h": ARENA_H, "r": RADIUS}, "dots": dots}

    def end_round(self, member, data):
        if member.id != self.host_id:
            raise LobbyError("Only the host can end the round.")
        self.finish({"reason": "The host ended the round."})

    def on_player_removed(self, member):
        self.pos.pop(member.id, None)
