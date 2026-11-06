"""Game rooms.

A browser connects to /ws/game/<game-id>?room=<room-id>&client=<client-id>.
- room:   which room of the game to enter (default "main").
- client: a random UUID the browser keeps for the tab (see web/shared/settings.js).

Players are identified by their client id, not their connection:
- If the same client connects again while still connected (e.g. a duplicated tab),
  the old connection is dropped.
- If a player disconnects, they are kept in the room for RECONNECT_GRACE seconds.
  Reconnecting within that time (e.g. reloading the page) resumes the same player,
  so games don't see them leave and rejoin.

Each room has one instance of the game's Game class, which decides what joining
means and what to do with messages. Rooms are discarded once no players remain.

Sessions (server/sessions.py, `room.sessions`): a seat keeps its tab's session (guest or
logged-in account, plus guest data) alive from when it is created until it is removed, so
on_disconnect can still save a player's data. Rooms.is_playing(client_id) tells sessions
whether a tab is playing a game anywhere (BaseGame.busy), since logging in or out is refused then.
"""

import asyncio
import json
import logging
import re

from server.sessions import Sessions
from server.utils import CLIENT_ID

log = logging.getLogger("rooms")

ROOM_ID = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
RECONNECT_GRACE = 60  # seconds

CLOSE_INVALID = 1008
CLOSE_REPLACED = 4001  # Same client connected again (e.g. the page was opened in another tab).


class BaseGame:
    """Base class for a game's server logic. One instance per room. Override what you need.

    `player.id` is stable for a browser tab across reloads and reconnects.
    """

    def __init__(self, room):
        self.room = room

    async def on_connect(self, player):
        """A new player connected to the room."""

    async def on_reconnect(self, player):
        """A player came back within the grace period (e.g. reloaded the page).

        Their state in the game is unchanged. By default this does what on_connect does.
        """
        await self.on_connect(player)

    async def on_message(self, player, data):
        """A player sent a message (a JSON object)."""

    async def on_connection_lost(self, player):
        """A player's connection dropped. They may come back within the grace period."""

    async def on_disconnect(self, player):
        """A player left for good: disconnected and didn't come back within the grace period."""

    def busy(self, client_id):
        """True while this client is in the middle of a game here (logging in or out is refused)."""
        return False


class Player:
    def __init__(self, client_id):
        self.id = client_id
        self.ws = None  # Current connection, or None while disconnected.
        self.removal = None  # Pending removal task while disconnected.

    @property
    def connected(self):
        return self.ws is not None

    async def send(self, data):
        if self.ws is not None:
            await self.ws.send(json.dumps(data))


class Room:
    def __init__(self, game_id, room_id, game_class, sessions=None):
        self.game_id = game_id
        self.id = room_id
        self.players = {}  # player id -> Player (including recently disconnected ones)
        self.sessions = sessions if sessions is not None else Sessions()  # guest/account data
        self.game = game_class(self)

    async def broadcast(self, data, exclude=None):
        """Send to every connected player."""
        text = json.dumps(data)
        await asyncio.gather(
            *(p.ws.send(text) for p in list(self.players.values())
              if p.ws is not None and p is not exclude)
        )


class Rooms:
    def __init__(self, games, sessions=None):
        self.games = games  # game id -> Game class
        self.rooms = {}  # (game id, room id) -> Room
        self.sessions = sessions if sessions is not None else Sessions(is_playing=self.is_playing)

    def is_playing(self, client_id):
        """True if this client is in the middle of a game in any room."""
        for room in list(self.rooms.values()):
            try:
                if room.game.busy(client_id):
                    return True
            except Exception:
                log.exception("Error in game %s, room %s", room.game_id, room.id)
        return False

    async def handle(self, ws, game_id):
        room_id = ws.query.get("room", "main")
        client_id = ws.query.get("client", "")
        if not ROOM_ID.match(room_id) or not CLIENT_ID.match(client_id):
            await ws.close(CLOSE_INVALID)
            return

        key = (game_id, room_id)
        room = self.rooms.get(key)
        if room is None:
            room = self.rooms[key] = Room(game_id, room_id, self.games[game_id], self.sessions)

        player = room.players.get(client_id)
        if player is None:
            player = room.players[client_id] = Player(client_id)
            self.sessions.attach(client_id)
            player.ws = ws
            await self._call(room, room.game.on_connect, player)
        else:
            if player.removal:
                player.removal.cancel()
                player.removal = None
            if player.ws is not None:
                player.ws.abort(CLOSE_REPLACED)
            player.ws = ws
            await self._call(room, room.game.on_reconnect, player)

        try:
            while (raw := await ws.recv()) is not None:
                try:
                    data = json.loads(raw)
                except ValueError:
                    continue
                if isinstance(data, dict):
                    await self._call(room, room.game.on_message, player, data)
        finally:
            # Only clean up if this is still the player's current connection.
            if player.ws is ws:
                player.ws = None
                player.removal = asyncio.create_task(self._remove_later(key, room, player))
                await self._call(room, room.game.on_connection_lost, player)

    async def _remove_later(self, key, room, player):
        await asyncio.sleep(RECONNECT_GRACE)
        if player.ws is not None or room.players.get(player.id) is not player:
            return
        del room.players[player.id]
        try:
            await self._call(room, room.game.on_disconnect, player)
        finally:
            self.sessions.detach(player.id)
        if not room.players and self.rooms.get(key) is room:
            del self.rooms[key]

    @staticmethod
    async def _call(room, method, *args):
        """Run a game callback; log errors instead of dropping the connection."""
        try:
            await method(*args)
        except Exception:
            log.exception("Error in game %s, room %s", room.game_id, room.id)
