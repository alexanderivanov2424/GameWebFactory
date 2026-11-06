"""Sim: drive a game's server code through the real lobby, without a network or a browser.

Messages go through LobbyGame.on_message exactly as they would from a browser (join, ready,
settings, start, game), and every player records the state messages sent to them, so you
test validation, hidden information (state.private) and errors the same way players see them.

Use it from a game's tests (APP/games/<id>/tests/test_*.py, run by tools/run_tests.py):

    import unittest
    from gamekit.sim import Sim

    class PlacingTests(unittest.TestCase):
        def test_mines_must_differ(self):
            sim = Sim("tanks", players=3, settings={"boardSize": 6, "wallChance": 0})
            sim.fails(0, {"action": "place", ...}, "different squares")

    sim.game                       # the Game instance: read or set internals freely
    sim.pid(0)                     # player 0's public id ("p1")
    sim.send(0, {"action": "place", ...})          # game message; returns the error text or None
    sim.ok(0, {...})                               # same, but raises if it was rejected
    sim.fails(1, {...}, "not your turn")           # raises unless rejected with that text
    sim.state(0)                   # last full state player 0 received (incl. "private")
    sim.lobby(0, {"type": "back_to_lobby"})        # any lobby message
    sim.spectator()                # connect a spectator; returns its index
    sim.leave(2)                   # player 2 leaves (on_player_removed runs mid-game)
    Sim("tanks", start=False)      # stay in the lobby (then sim.start())
    Sim(MyGameClass)               # a Game class instead of a game id (gamekit's own tests)

Timers (LobbyGame.schedule) don't wait in real time: they're queued and, by default, run
right after each message (auto_timers=True). With auto_timers=False, call sim.run_timers()
yourself to inspect the state between a reveal and what follows; sim.step() runs just the
next one (run_timers also runs what each callback queues). sim.pending_timers() lists the
queued callbacks.

Games are imported as games.<id>.server, the same way server/main.py loads them, so the
APP folder must be on sys.path (tools/run_tests.py does that).
"""

import asyncio
import json

from server.main import load_game
from server.rooms import Player, Room


class FakeSocket:
    def __init__(self):
        self.messages = []

    async def send(self, text):
        self.messages.append(json.loads(text))


class Sim:
    def __init__(self, game_id, players=2, settings=None, names=None, start=True, auto_timers=True):
        self.loop = asyncio.new_event_loop()
        game_class = load_game(game_id) if isinstance(game_id, str) else game_id
        self.room = Room(game_id if isinstance(game_id, str) else game_class.__name__, "sim", game_class)
        self.game = self.room.game
        self.auto_timers = auto_timers
        self._timers = []
        self._patch_timers()
        self.clients = []  # rooms.Player per index
        for i in range(players):
            index = self._connect()
            self.lobby(index, {"type": "name", "name": names[i] if names else f"Player{i + 1}"})
            self.lobby(index, {"type": "join"})
        if settings:
            merged = {**self.game.settings, **settings}
            self._expect_ok(self.lobby(0, {"type": "settings", "settings": merged}))
        if start:
            self.start()

    # --- Connections ------------------------------------------------------------------

    def _connect(self):
        player = Player(f"00000000-0000-4000-8000-{len(self.clients):012d}")
        player.ws = FakeSocket()
        self.room.players[player.id] = player
        self.clients.append(player)
        self._run(self.game.on_connect(player))
        return len(self.clients) - 1

    def spectator(self, name="Watcher"):
        index = self._connect()
        self.lobby(index, {"type": "name", "name": name})
        return index

    def member(self, index):
        return self.game.members[self.clients[index].id]

    def pid(self, index):
        return self.member(index).id

    def index_of(self, pid):
        return next(i for i in range(len(self.clients)) if self.pid(i) == pid)

    # --- Messages ---------------------------------------------------------------------

    def lobby(self, index, data):
        """Send any message; returns the error text the player got, or None."""
        socket = self.clients[index].ws
        before = len(socket.messages)
        self._run(self.game.on_message(self.clients[index], data))
        if self.auto_timers:
            self.run_timers()
        errors = [m["message"] for m in socket.messages[before:] if m.get("type") == "error"]
        return errors[0] if errors else None

    def send(self, index, data):
        """Send a game message ({"type": "game", **data}); returns the error text or None."""
        return self.lobby(index, {"type": "game", **data})

    def ok(self, index, data):
        return self._expect_ok(self.send(index, data))

    def fails(self, index, data, text=""):
        error = self.send(index, data)
        if error is None:
            raise AssertionError(f"expected an error containing {text!r} for {data}")
        if text.lower() not in error.lower():
            raise AssertionError(f"expected an error containing {text!r}, got {error!r}")
        return error

    def start(self):
        for i, client in enumerate(self.clients):
            if self.member(i).playing:
                self._expect_ok(self.lobby(i, {"type": "ready", "ready": True}))
        host = next(i for i in range(len(self.clients)) if self.pid(i) == self.game.host_id)
        self._expect_ok(self.lobby(host, {"type": "start"}))

    def leave(self, index):
        return self.lobby(index, {"type": "leave"})

    def state(self, index):
        states = [m for m in self.clients[index].ws.messages if m.get("type") == "state"]
        return states[-1] if states else None

    # --- Timers -------------------------------------------------------------------------

    def _patch_timers(self):
        game = self.game

        def schedule(delay, callback):
            self._timers.append((delay, callback))

        def cancel_timers():
            self._timers.clear()

        game.schedule = schedule
        game.cancel_timers = cancel_timers

    def pending_timers(self):
        return [(delay, getattr(cb, "__name__", repr(cb))) for delay, cb in self._timers]

    def step(self):
        """Run only the next queued schedule() callback (not what it queues), then send the state.

        Returns False if nothing was queued. Use it to stop between stages, e.g. after a reveal.
        """
        if not self._timers:
            return False
        _, callback = self._timers.pop(0)
        callback()
        self._run(self.game.update())
        return True

    def run_timers(self, limit=1000):
        """Run queued schedule() callbacks (and any they queue) in order, sending state after each."""
        for _ in range(limit):
            if not self._timers:
                return
            _, callback = self._timers.pop(0)
            callback()
            self._run(self.game.update())
        raise RuntimeError("Timers kept scheduling more timers; is the game looping?")

    # --- Internals ------------------------------------------------------------------------

    def __del__(self):
        loop = getattr(self, "loop", None)
        if loop is not None and not loop.is_closed():
            loop.close()

    def _run(self, coroutine):
        return self.loop.run_until_complete(coroutine)

    @staticmethod
    def _expect_ok(error):
        if error is not None:
            raise AssertionError(f"rejected: {error}")
        return None
