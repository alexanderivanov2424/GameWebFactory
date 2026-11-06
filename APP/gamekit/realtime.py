"""RealtimeGame: a LobbyGame that runs on a fixed tick instead of turns.

Subclass it instead of LobbyGame for games where things move continuously:

    from gamekit import RealtimeGame

    class Game(RealtimeGame):
        TICK_RATE = 20                       # ticks per second

        def on_input(self, member, data):    # latest input wins; raise LobbyError to reject
            member.input = {"keys": ...}     # validate, then store

        def tick(self, dt):                  # dt = 1 / TICK_RATE (fixed)
            for player in self.players:
                ... move things using player.input ...

        def game_state(self): ...            # as for any LobbyGame
        def private_state(self, member): ...

Everything from LobbyGame still applies (lobby, SETTINGS, ACTIONS, schedule, finish...).
What's different:
- Ticks: while playing, tick(dt) runs TICK_RATE times a second, then every client gets the
  changes (SYNC = Snapshots, see sync.py). The loop stops when the game finishes or goes back
  to the lobby. self.tick_number counts ticks in the current game. A tick that raises is
  logged and the game goes on.
- Inputs: the client sends {"type": "input", "seq": n, ...} (lobby.sendInput) whenever its
  controls change. Inputs are *state* (keys held, aim), not events: on_input(member, data)
  gets the message without type/seq and by default stores it as member.input. Inputs from
  spectators or outside play are ignored. Inputs never send anything by themselves; the next
  tick does. member.input_seq is the last applied seq (sent back as snap.ack, for client-side
  prediction later).
- ACTIONS still work for one-off events (buy, use item): they're applied at once and their
  effect goes out with the next tick. A rejection (LobbyError) is still sent at once.
- Ping: clients send {"type": "ping", "t": ..., "rtt": ms} every few seconds (realtime.js does
  this); the server answers {"type": "pong", "t": ...} to that client only, and keeps the
  reported round trip as member.ping (ms, None until known). Show it via game_state.
- state.tickRate tells the client the tick rate (realtime.js uses it for interpolation).

Tests: gamekit.sim.Sim never ticks on its own; call sim.tick(n), sim.input(i, {...}) and
sim.ping(i, rtt). Client side: web/gamekit/realtime.js.
"""

import asyncio
import logging

from gamekit.lobby import PLAYING, LobbyGame
from gamekit.sync import Snapshots
from gamekit.validate import LobbyError

log = logging.getLogger("realtime")

MAX_PING = 60_000


class RealtimeGame(LobbyGame):
    TICK_RATE = 20
    SYNC = Snapshots

    def __init__(self, room):
        super().__init__(room)
        self.tick_number = 0
        self._ticker = None  # (game_number, task) of the running tick loop

    # --- Game hooks ------------------------------------------------------------------

    def tick(self, dt):
        """Advance the game by dt seconds (always 1 / TICK_RATE)."""

    def on_input(self, member, data):
        """A player's latest input (the message without type/seq). Validate it; raise
        LobbyError to reject. Default: store it as member.input."""
        member.input = data

    # --- Room callbacks -----------------------------------------------------------------

    async def on_message(self, player, data):
        kind = data.get("type")
        if kind == "input":
            await self._on_input(player, data)
        elif kind == "ping":
            await self._on_ping(player, data)
        else:
            await super().on_message(player, data)
            self._ensure_ticker()

    async def _on_input(self, player, data):
        member = self.members.get(player.id)
        if member is None or not member.playing or self.phase != PLAYING:
            return
        seq = data.get("seq")
        try:
            self.on_input(member, {k: v for k, v in data.items() if k not in ("type", "seq")})
        except LobbyError as error:
            await player.send({"type": "error", "message": str(error)})
            return
        if type(seq) is int:
            member.input_seq = seq

    async def _on_ping(self, player, data):
        member = self.members.get(player.id)
        if member is None:
            return
        rtt = data.get("rtt")
        if type(rtt) in (int, float) and 0 <= rtt <= MAX_PING:
            member.ping = round(rtt)
        t = data.get("t")
        await player.send({"type": "pong", "t": t if type(t) in (int, float) else None})

    # --- Ticks ------------------------------------------------------------------------

    def lobby_state(self):
        return {**super().lobby_state(), "tickRate": self.TICK_RATE}

    def step(self):
        """Run one tick and queue the snapshots (the tick loop calls this; tests use sim.tick)."""
        self.tick_number += 1
        try:
            self.tick(1 / self.TICK_RATE)
        except Exception:
            log.exception("Tick failed")
        time_ms = round(asyncio.get_running_loop().time() * 1000)
        self.sync.send_tick(self, self.tick_number, time_ms)

    def _ensure_ticker(self):
        """Start the tick loop for the current game if it's playing and not ticking yet."""
        if self.phase != PLAYING:
            return
        if self._ticker and self._ticker[0] == self.game_number and not self._ticker[1].done():
            return
        if self._ticker:
            self._ticker[1].cancel()
        self.tick_number = 0
        task = asyncio.get_running_loop().create_task(self._run_ticks(self.game_number))
        self._ticker = (self.game_number, task)

    async def _run_ticks(self, number):
        loop = asyncio.get_running_loop()
        interval = 1 / self.TICK_RATE
        next_time = loop.time() + interval

        def running():
            return self.phase == PLAYING and self.game_number == number

        while running():
            await asyncio.sleep(max(0.0, next_time - loop.time()))
            if not running():
                break
            self.step()
            next_time += interval
            if next_time < loop.time() - interval:  # fell far behind (e.g. a slow tick): don't burst
                next_time = loop.time() + interval
        # The game finished, went back to the lobby or restarted: send the final state.
        if self.game_number == number:
            await self.update()
