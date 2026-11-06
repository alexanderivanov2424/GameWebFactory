"""Shared lobby management for games.

Subclass LobbyGame (instead of BaseGame) to get:
- Members: everyone connected to the room. Each is a spectator or a player.
- Joining and leaving: explicit, and only before a game starts. Spectators can watch any time.
- Host: the first player to join. Only the host can change settings, pass hosting to
  another player, or return to the lobby after a game. If the host leaves, the next
  player (in join order) becomes host.
- Ready and start: players mark themselves ready. Once everyone is ready (and
  start_check passes), the host clicks Start ("start" message) to begin the game.
- Phases: "lobby" (before the game) -> "playing" -> "finished" -> (host) back to "lobby".
- Sessions: players keep their seat through reloads and short disconnects
  (see RECONNECT_GRACE in rooms.py) and are shown as offline meanwhile.
- State: after every change, each client gets one "state" message describing the room:
  the public part (game_state) plus a private part only they can see (private_state).
- Settings: declare them once in SETTINGS (see settings.py); default_settings/clean_settings
  come from it and clients get state.settingsSpec to draw the inputs.
- Game messages: list them in ACTIONS ({"move": "move", ...}: action name -> method name);
  the default on_game_message calls self.<method>(member, data). Unknown actions are rejected.
- Games played: self.game_number counts started games (sent as state.gameNumber), so
  clients can key per-game data (marks, animations) by it.
- Turn order: see turns.py (TurnQueue). Hidden simultaneous choices: see choices.py.
- Timers: self.schedule(seconds, callback) runs callback later (e.g. a pause to show a
  reveal) and then sends the state. Pending timers are cancelled when the game finishes,
  returns to the lobby, or starts again.
- Sync (what goes over the wire): SYNC picks a class from sync.py. The default FullState
  sends every member the whole state after every change (fine for turn-based games).
  PatchState sends only what changed; RealtimeGame (realtime.py) uses Snapshots, one delta
  per tick. The game code (game_state/private_state) is the same for all of them.

Other clients see members by a short public id ("p1", "p2", ...), never by their
client UUID, which acts as their key to the seat.

Games override the hooks in the "Game hooks" section. Client side: web/gamekit/lobby.js.
"""

import inspect
import itertools
import logging

from gamekit import settings as settings_schema
from gamekit.sync import FullState
from gamekit.validate import LobbyError, clean_text
from server.rooms import BaseGame

log = logging.getLogger("lobby")

LOBBY, PLAYING, FINISHED = "lobby", "playing", "finished"
MAX_NAME = 32


class Member:
    def __init__(self, client_id, public_id):
        self.client_id = client_id
        self.id = public_id
        self.name = "Anonymous"
        self.playing = False
        self.ready = False
        self.options = {}  # Per-player choices made in the lobby (e.g. a color).
        self.joined_at = 0
        # Used by RealtimeGame (realtime.py): latest input, its sequence number, reported ping (ms).
        self.input = {}
        self.input_seq = 0
        self.ping = None


class LobbyGame(BaseGame):
    MIN_PLAYERS = 1
    MAX_PLAYERS = 16
    SETTINGS = {}  # key -> settings.Int(...): host settings, see settings.py
    ACTIONS = {}  # game message "action" -> name of the method handling it: method(member, data)
    SYNC = FullState  # how state reaches clients: FullState, PatchState or Snapshots (sync.py)

    def __init__(self, room):
        super().__init__(room)
        self.members = {}  # client id -> Member
        self.phase = LOBBY
        self.host_id = None  # public id of the host
        self.settings = self.default_settings()
        self.result = None
        self.game_number = 0  # games started in this room; +1 just before start_game()
        self._public_ids = itertools.count(1)
        self._join_order = itertools.count()
        self._timers = set()
        self.sync = self.SYNC()

    # --- Game hooks ------------------------------------------------------------

    def default_settings(self):
        """Initial game settings (a JSON-friendly dict). Default: from SETTINGS."""
        return settings_schema.defaults(self.SETTINGS)

    def clean_settings(self, settings):
        """Validate settings sent by the host. Return the new settings or raise LobbyError.

        Default: checks them against SETTINGS (missing keys keep their current value).
        """
        return settings_schema.clean(self.SETTINGS, settings, self.settings)

    def default_options(self, member):
        """Initial options for a player who just joined."""
        return {}

    def clean_options(self, member, options):
        """Validate options sent by a player. Return the new options or raise LobbyError."""
        return dict(member.options)

    def start_check(self):
        """Return a reason the game can't start yet, or None. Checked once everyone is ready and again when the host starts."""
        return None

    def start_game(self):
        """Set up a new game. self.players are the players; the phase is already "playing"."""

    async def on_game_message(self, member, data):
        """A player sent a game message during play. Raise LobbyError to reject it.

        Default: dispatch on data["action"] through ACTIONS. Override to add checks that
        apply to every action (e.g. whose turn it is), then call self.dispatch(member, data).
        """
        await self.dispatch(member, data)

    def on_player_removed(self, member):
        """A player left during play. Call self.finish(...) if the game can't go on."""

    def game_state(self):
        """Public game state sent to everyone while playing or finished."""
        return None

    def private_state(self, member):
        """State only this member may see (e.g. their hidden location), or None.

        Sent as state.private while playing or finished. `member` may be a spectator.
        """
        return None

    def reset_game(self):
        """Clear game state when returning to the lobby."""

    # --- Helpers for games ---------------------------------------------------------

    async def dispatch(self, member, data):
        """Call the ACTIONS method for data["action"] with (member, data). It may be sync or async."""
        name = self.ACTIONS.get(data.get("action"))
        if name is None:
            raise LobbyError("Unknown action.")
        result = getattr(self, name)(member, data)
        if inspect.isawaitable(result):
            await result

    @property
    def players(self):
        """Players (not spectators), in join order."""
        return sorted((m for m in self.members.values() if m.playing), key=lambda m: m.joined_at)

    def member_by_id(self, public_id):
        return next((m for m in self.members.values() if m.id == public_id), None)

    def finish(self, result=None):
        """End the game. `result` is sent to everyone as state.result. Cancels pending timers."""
        self.phase = FINISHED
        self.result = result
        self.cancel_timers()

    def schedule(self, delay, callback):
        """Call callback() (a plain function) after `delay` seconds, then send the state.

        Use it for pauses during play, e.g. to let everyone see a reveal before the game
        moves on. Timers are cancelled by finish(), by returning to the lobby and by a new
        start, so a callback only ever runs during the game that scheduled it.
        """

        async def run():
            await asyncio.sleep(delay)
            self._timers.discard(task)
            try:
                callback()
            except Exception:
                log.exception("Timer callback failed")
            await self.update()

        task = asyncio.get_running_loop().create_task(run())
        self._timers.add(task)
        return task

    def cancel_timers(self):
        """Cancel every pending schedule() callback."""
        for task in self._timers:
            task.cancel()
        self._timers.clear()

    # --- Room callbacks ------------------------------------------------------------

    async def on_connect(self, player):
        self.members[player.id] = Member(player.id, f"p{next(self._public_ids)}")
        self.sync.reset(player.id)
        await self.update()

    async def on_reconnect(self, player):
        self.sync.reset(player.id)
        await self.update()

    async def on_connection_lost(self, player):
        await self.update()

    async def on_disconnect(self, player):
        self.sync.reset(player.id)
        member = self.members.pop(player.id, None)
        if member and member.playing:
            self._remove_player(member)
        await self.update()

    async def on_message(self, player, data):
        member = self.members.get(player.id)
        handler = self._handlers.get(data.get("type"))
        if member is None or handler is None:
            return
        try:
            await handler(self, member, data)
        except LobbyError as error:
            await player.send({"type": "error", "message": str(error)})
        await self.update()

    # --- Requests from clients ---------------------------------------------------------

    async def _on_name(self, member, data):
        member.name = clean_text(data.get("name"), MAX_NAME) or "Anonymous"

    async def _on_join(self, member, data):
        if member.playing:
            return
        if self.phase != LOBBY:
            raise LobbyError("A game is in progress. You can join when it ends.")
        if len(self.players) >= self.MAX_PLAYERS:
            raise LobbyError("The game is full.")
        member.playing = True
        member.ready = False
        member.joined_at = next(self._join_order)
        member.options = self.default_options(member)
        if self.host_id is None:
            self.host_id = member.id

    async def _on_leave(self, member, data):
        if member.playing:
            self._remove_player(member)

    async def _on_ready(self, member, data):
        self._require_lobby_player(member)
        member.ready = bool(data.get("ready"))

    async def _on_options(self, member, data):
        self._require_lobby_player(member)
        options = data.get("options")
        if not isinstance(options, dict):
            raise LobbyError("Invalid options.")
        member.options = self.clean_options(member, options)

    async def _on_settings(self, member, data):
        self._require_host(member)
        if self.phase != LOBBY:
            raise LobbyError("Settings can only change before the game starts.")
        settings = data.get("settings")
        if not isinstance(settings, dict):
            raise LobbyError("Invalid settings.")
        self.settings = self.clean_settings(settings)

    async def _on_make_host(self, member, data):
        self._require_host(member)
        target = self.member_by_id(data.get("playerId"))
        if target is None or not target.playing:
            raise LobbyError("That player isn't in the game.")
        self.host_id = target.id

    async def _on_back_to_lobby(self, member, data):
        self._require_host(member)
        if self.phase == FINISHED:
            self._return_to_lobby()

    async def _on_start(self, member, data):
        self._require_host(member)
        if self.phase != LOBBY:
            raise LobbyError("The game has already started.")
        blocker = self._start_blocker()
        if blocker:
            raise LobbyError(blocker)
        self.cancel_timers()
        self.phase = PLAYING
        self.result = None
        self.game_number += 1
        self.start_game()

    async def _on_resync(self, member, data):
        self.sync.reset(member.client_id)  # the client lost track of patches: next message is a full state

    async def _on_game(self, member, data):
        if self.phase != PLAYING or not member.playing:
            raise LobbyError("You're not playing right now.")
        await self.on_game_message(member, data)

    _handlers = {
        "name": _on_name,
        "join": _on_join,
        "leave": _on_leave,
        "ready": _on_ready,
        "options": _on_options,
        "settings": _on_settings,
        "make_host": _on_make_host,
        "start": _on_start,
        "back_to_lobby": _on_back_to_lobby,
        "game": _on_game,
        "resync": _on_resync,
    }

    # --- Internals ----------------------------------------------------------------

    def _require_host(self, member):
        if member.id != self.host_id:
            raise LobbyError("Only the host can do that.")

    def _require_lobby_player(self, member):
        if not member.playing:
            raise LobbyError("Join the game first.")
        if self.phase != LOBBY:
            raise LobbyError("The game has already started.")

    def _remove_player(self, member):
        member.playing = False
        member.ready = False
        member.options = {}
        if self.host_id == member.id:
            remaining = self.players
            self.host_id = remaining[0].id if remaining else None
        if self.phase == PLAYING:
            self.on_player_removed(member)
        if self.phase != LOBBY and not self.players:
            self._return_to_lobby()

    def _return_to_lobby(self):
        self.cancel_timers()
        self.phase = LOBBY
        self.result = None
        for player in self.players:
            player.ready = False
        self.reset_game()

    def _start_blocker(self):
        players = self.players
        minimum = max(1, self.MIN_PLAYERS)
        if len(players) < minimum:
            return f"Need at least {minimum} player{'s' if minimum > 1 else ''}."
        if not all(p.ready for p in players):
            return "Waiting for everyone to be ready."
        return self.start_check()

    async def update(self):
        """Send the state to everyone."""
        await self.send_state()

    def lobby_state(self):
        """The room part of the state (everything except game, private and you)."""
        def info(m):
            connection = self.room.players.get(m.client_id)
            return {"id": m.id, "name": m.name, "connected": bool(connection and connection.connected)}

        return {
            "type": "state",
            "phase": self.phase,
            "hostId": self.host_id,
            "settings": self.settings,
            "settingsSpec": settings_schema.spec(self.SETTINGS),
            "gameNumber": self.game_number,
            "minPlayers": self.MIN_PLAYERS,
            "maxPlayers": self.MAX_PLAYERS,
            "startBlocker": self._start_blocker() if self.phase == LOBBY else None,
            "players": [{**info(m), "ready": m.ready, "options": m.options} for m in self.players],
            "spectators": [info(m) for m in self.members.values() if not m.playing],
            "result": self.result,
        }

    def public_game(self):
        """game_state() while playing or finished, None in the lobby."""
        return self.game_state() if self.phase != LOBBY else None

    def private_game(self, member):
        """private_state(member) while playing or finished, None in the lobby."""
        return self.private_state(member) if self.phase != LOBBY else None

    def state(self):
        """The full state message (without you/private): lobby_state() plus game."""
        state = self.lobby_state()
        result = state.pop("result")
        return {**state, "game": self.public_game(), "result": result}

    def recipients(self):
        """(connection, member) for every connected member."""
        for client_id, connection in list(self.room.players.items()):
            member = self.members.get(client_id)
            if member and connection.connected:
                yield connection, member

    async def send_state(self):
        await self.sync.send(self)
