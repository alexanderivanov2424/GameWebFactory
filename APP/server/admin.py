"""Admin view: a read-only look at the site for the owner (Settings -> Settings -> Enable Admin Mode).

Not meant to be secure: one shared password (ADMIN_PASSWORD), checked here on the server so it
never appears in the page's JS. Everything is VIEW ONLY: nothing here changes accounts, feedback,
sessions or rooms. Client UUIDs are shown shortened (SHORT_ID characters), since a full UUID is
the key to a player's seat; password hashes are never sent.

/ws/admin?client=<uuid>   (web/shared/admin.js keeps one open while admin mode is on)
    client -> server  {"type": "auth", "password"}           must come first
                      {"type": "get", "what": "accounts"}     every account (name, created, display name, data size)
                      {"type": "get", "what": "account", "name"}            one account's saved data
                      {"type": "get", "what": "feedback"}     feedback files grouped by game
                      {"type": "get", "what": "feedbackFile", "game", "file"}   one file's text
                      {"type": "get", "what": "sessions"}     every session (guest/account, connections, rooms)
                      {"type": "get", "what": "session", "id"}   one session (by short id) with its guest data
                      {"type": "get", "what": "rooms"}        every room: game, phase, members
    server -> client  {"type": "auth", "ok": bool}
                      {"type": "data", "what", ...request fields, "data"}
                      {"type": "error", "what", ...request fields, "message"}

A wrong password is answered after WRONG_PASSWORD_DELAY seconds (slows guessing).
"""

import asyncio
import json
import logging
import re
from pathlib import Path

from server import accounts
from server.utils import CLIENT_ID

log = logging.getLogger("admin")

ADMIN_PASSWORD = "bustedeye"
WRONG_PASSWORD_DELAY = 1.0  # seconds
SHORT_ID = 8  # characters of a client UUID shown in the admin view
MAX_FEEDBACK_VIEW = 512 * 1024  # bytes of one feedback file sent at most
FEEDBACK_FILE = re.compile(r"^([0-9a-f-]{36})_([A-Za-z0-9_-]+)\.txt$")
FEEDBACK_GAME = re.compile(r"^[a-z0-9_-]+$")

CLOSE_INVALID = 1008


class AdminError(Exception):
    """A request couldn't be answered; the message is shown in the admin view."""


def short(client_id):
    return client_id[:SHORT_ID]


def _plain(value):
    """value as plain JSON data (anything odd becomes a string)."""
    return json.loads(json.dumps(value, default=str))


class Admin:
    def __init__(self, store, sessions, rooms, feedback_folder):
        self.store = store  # accounts.AccountStore
        self.sessions = sessions  # sessions.Sessions
        self.rooms = rooms  # rooms.Rooms
        self.feedback_folder = Path(feedback_folder)

    # --- Requests ---------------------------------------------------------------------

    def get(self, data):
        """Answer one "get" request (a dict); raises AdminError."""
        what = data.get("what")
        if what == "accounts":
            return self.accounts()
        if what == "account":
            return self.account(data.get("name"))
        if what == "feedback":
            return self.feedback()
        if what == "feedbackFile":
            return self.feedback_file(data.get("game"), data.get("file"))
        if what == "sessions":
            return self.session_list()
        if what == "session":
            return self.session(data.get("id"))
        if what == "rooms":
            return self.room_list()
        raise AdminError("Unknown request.")

    # --- Accounts ---------------------------------------------------------------------

    def accounts(self):
        logged_in = {}
        for session in list(self.sessions.sessions.values()):
            if session.account is not None:
                logged_in[session.account] = logged_in.get(session.account, 0) + 1
        return [
            {
                "name": record["name"],
                "displayName": record.get("displayName"),
                "created": record.get("created"),
                "games": sorted(record["games"]),
                "bytes": accounts.data_size(record["games"]),
                "sessions": logged_in.get(key, 0),
            }
            for key, record in sorted(self.store.accounts.items())
        ]

    def account(self, name):
        record = self.store.get(name)
        if record is None:
            raise AdminError("No such account.")
        return _plain({key: value for key, value in record.items() if key != "password"})

    # --- Feedback ---------------------------------------------------------------------

    def feedback(self):
        """{game: [{file, client, name, entries, bytes, modified}]}, newest first."""
        groups = {}
        if not self.feedback_folder.is_dir():
            return groups
        for folder in sorted(self.feedback_folder.iterdir()):
            if not folder.is_dir() or not FEEDBACK_GAME.match(folder.name):
                continue
            files = []
            for path in folder.glob("*.txt"):
                match = FEEDBACK_FILE.match(path.name)
                if not match:
                    continue
                try:
                    stat = path.stat()
                    with path.open(encoding="utf-8", errors="replace") as file:
                        entries = sum(1 for line in file if line.startswith("--- "))
                except OSError:
                    continue
                files.append({"file": path.name, "client": short(match.group(1)), "name": match.group(2),
                              "entries": entries, "bytes": stat.st_size, "modified": int(stat.st_mtime)})
            if files:
                groups[folder.name] = sorted(files, key=lambda f: -f["modified"])
        return groups

    def feedback_file(self, game, file):
        if not (isinstance(game, str) and FEEDBACK_GAME.match(game)
                and isinstance(file, str) and FEEDBACK_FILE.match(file)):
            raise AdminError("No such feedback file.")
        path = self.feedback_folder / game / file
        try:
            with path.open("rb") as handle:
                raw = handle.read(MAX_FEEDBACK_VIEW + 1)
        except OSError:
            raise AdminError("No such feedback file.") from None
        text = raw[:MAX_FEEDBACK_VIEW].decode("utf-8", errors="replace")
        if len(raw) > MAX_FEEDBACK_VIEW:
            text += "\n[... cut off: file too long to show]"
        return text

    # --- Sessions ---------------------------------------------------------------------

    def _seats(self):
        """client id -> list of "<game>/<room>" it has a seat in."""
        seats = {}
        for (game_id, room_id), room in list(self.rooms.rooms.items()):
            for client_id in list(room.players):
                seats.setdefault(client_id, []).append(f"{game_id}/{room_id}")
        return seats

    def _session_info(self, session, seats):
        client_id = session.client_id
        return {
            "id": short(client_id),
            "account": self.sessions.account_name(client_id),
            "connections": session.connections,
            "accountSockets": len(self.sessions._sockets.get(client_id, ())),
            "rooms": seats.get(client_id, []),
            "playing": bool(self.sessions.is_playing(client_id)),
            "guestGames": sorted(session.guest),
            "ending": session.connections == 0,
        }

    def session_list(self):
        seats = self._seats()
        return [self._session_info(s, seats) for s in list(self.sessions.sessions.values())]

    def session(self, short_id):
        if not isinstance(short_id, str) or len(short_id) != SHORT_ID:
            raise AdminError("No such session.")
        found = [s for s in list(self.sessions.sessions.values()) if short(s.client_id) == short_id]
        if len(found) != 1:
            raise AdminError("No such session." if not found else "Several sessions share that id.")
        session = found[0]
        info = self._session_info(session, self._seats())
        info["guestData"] = _plain(session.guest)
        info["savesRecently"] = len(session.saves)
        info["displayName"] = self.sessions.display_name(session.client_id)
        return info

    # --- Rooms ------------------------------------------------------------------------

    def room_list(self):
        result = []
        for (game_id, room_id), room in sorted(self.rooms.rooms.items()):
            try:
                info = dict(room.game.admin_info())
            except Exception:
                log.exception("admin_info failed in game %s, room %s", game_id, room_id)
                info = {}
            members = info.pop("members", None)
            if members is None:  # a game without a lobby: list the raw seats
                members = [{"client": c} for c in room.players]
            for member in members:
                client_id = member.pop("client", "")
                player = room.players.get(client_id)
                member["session"] = short(client_id)
                member["online"] = bool(player and player.connected)
                member["account"] = self.sessions.account_name(client_id)
            result.append({"game": game_id, "room": room_id, **_plain(info), "members": _plain(members)})
        return result

    # --- /ws/admin --------------------------------------------------------------------

    async def handle(self, ws):
        if not CLIENT_ID.match(ws.query.get("client", "")):
            await ws.close(CLOSE_INVALID)
            return
        authed = False
        while (raw := await ws.recv()) is not None:
            try:
                data = json.loads(raw)
            except ValueError:
                continue
            if not isinstance(data, dict):
                continue
            kind = data.get("type")
            if kind == "auth":
                authed = data.get("password") == ADMIN_PASSWORD
                if not authed:
                    await asyncio.sleep(WRONG_PASSWORD_DELAY)
                await ws.send(json.dumps({"type": "auth", "ok": authed}))
            elif kind == "get":
                request = {k: data[k] for k in ("what", "name", "game", "file", "id")
                           if isinstance(data.get(k), str)}
                try:
                    if not authed:
                        raise AdminError("Admin mode is off.")
                    reply = {"type": "data", **request, "data": self.get(data)}
                except AdminError as error:
                    reply = {"type": "error", **request, "message": str(error)}
                await ws.send(json.dumps(reply))
