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
    sim.state(0)                   # player 0's current state (incl. "private"), as their browser has it
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

State sync (gamekit/sync.py): with PatchState or Snapshots, sim.state(i) applies the patches
and snaps to the last full state, exactly as lobby.js does, and raises if one doesn't follow
the previous message (a sync bug). sim.messages(i, "snap") lists the raw messages of a type.

Saved player data (LobbyGame.load_data/save_data): each Sim has its own in-memory sessions
(server/sessions.py), so nothing touches the disk. Players start as guests.
    sim.login(0, "alice")           # player 0 logs in (account created if new; guest data moves over)
    sim.logout(0)
    sim.sessions                    # the Sessions object: sim.sessions.load(sim.clients[0].id, game_id)
A limit that would turtle the site raises server.turtle.Turtled instead (test mode).

Real-time games (gamekit/realtime.py) never tick on their own in tests:
    sim.input(0, {"keys": ["up"]})  # {"type": "input", "seq": n, ...}; returns error text or None
    sim.tick(5)                     # run 5 ticks, delivering each tick's snaps
    sim.ping(0, 42)                 # report a 42 ms round trip (member.ping)

Games are imported as games.<id>.server, the same way server/main.py loads them, so the
APP folder must be on sys.path (tools/run_tests.py does that).
"""

import asyncio
import json

from gamekit.sync import merge_apply
from server import turtle
from server.main import load_game
from server.rooms import Player, Room
from server.sessions import Sessions


class FakeSocket:
    def __init__(self):
        self.messages = []

    async def send(self, text):
        self.messages.append(json.loads(text))


class Sim:
    def __init__(self, game_id, players=2, settings=None, names=None, start=True, auto_timers=True):
        turtle.install_test_handler()  # a broken limit raises Turtled instead of exiting
        self.loop = asyncio.new_event_loop()
        game_class = load_game(game_id) if isinstance(game_id, str) else game_id
        self.sessions = Sessions(is_playing=lambda client_id: self.game.busy(client_id))
        self.room = Room(game_id if isinstance(game_id, str) else game_class.__name__, "sim", game_class,
                         self.sessions)
        self.game = self.room.game
        self.auto_timers = auto_timers
        self._timers = []
        self._input_seq = 0
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
        self.sessions.attach(player.id)
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
        self._run(self._deliver(self.game.on_message(self.clients[index], data)))
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

    # --- Accounts -----------------------------------------------------------------------

    def login(self, index, name):
        """Log player `index` in as `name` (no password; the account is created if new)."""
        self.sessions.bind(self.clients[index].id, name)

    def logout(self, index):
        self.sessions.logout(self.clients[index].id)

    def state(self, index):
        """The state as the client has it: the last full state with later patches/snaps applied."""
        state = None
        for message in self.clients[index].ws.messages:
            kind = message.get("type")
            if kind == "state":
                state = dict(message)
            elif kind in ("patch", "snap") and state is not None:
                if message["base"] != state.get("seq"):
                    raise AssertionError(f"{kind} base {message['base']} doesn't follow seq {state.get('seq')}")
                if "g" in message:
                    state["game"] = merge_apply(state["game"], message["g"])
                if "p" in message:
                    state["private"] = merge_apply(state["private"], message["p"])
                state["seq"] = message["seq"]
        return state

    def messages(self, index, kind=None):
        """Raw messages client `index` received (only those of type `kind` if given)."""
        return [m for m in self.clients[index].ws.messages if kind is None or m.get("type") == kind]

    # --- Real-time games ------------------------------------------------------------------

    def input(self, index, data):
        """Send an input message (seq added); returns the error text or None."""
        self._input_seq += 1
        return self.lobby(index, {"type": "input", "seq": self._input_seq, **data})

    def ping(self, index, rtt):
        return self.lobby(index, {"type": "ping", "t": 0, "rtt": rtt})

    def tick(self, n=1):
        """Run n ticks of a RealtimeGame, delivering each tick's messages before the next."""
        for _ in range(n):
            self._run(self._tick_once())
            if self.auto_timers:
                self.run_timers()

    async def _tick_once(self):
        self.game.step()
        await self.game.sync.drain()

    # --- Timers -------------------------------------------------------------------------

    def _patch_timers(self):
        game = self.game

        def schedule(delay, callback):
            self._timers.append((delay, callback))

        def cancel_timers():
            self._timers.clear()

        game.schedule = schedule
        game.cancel_timers = cancel_timers
        if hasattr(game, "_ensure_ticker"):
            game._ensure_ticker = lambda: None  # no real-time tick loop: tests call sim.tick()

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

    async def _deliver(self, coroutine):
        """Run a coroutine, then wait for any messages a sync strategy queued."""
        await coroutine
        drain = getattr(self.game.sync, "drain", None)
        if drain:
            await drain()

    def _run(self, coroutine):
        return self.loop.run_until_complete(coroutine)

    @staticmethod
    def _expect_ok(error):
        if error is not None:
            raise AssertionError(f"rejected: {error}")
        return None
