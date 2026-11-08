"""Sessions: who each browser tab is (a guest or a logged-in account) and the data games save.

A session belongs to a client id (the tab's UUID, see web/shared/settings.js). Every tab starts
as a guest. It lasts while the tab is connected anywhere: a game room seat (rooms.py attaches
when the seat is created and detaches when it is finally removed) or the /ws/account socket that
settings.js keeps open on every page. SESSION_GRACE seconds after the last of those goes away,
the session ends: guest data is forgotten and the login with it.

Game data (games call LobbyGame.load_data/save_data, gamekit/lobby.py, which land here):
    sessions.load(client_id, game_id) -> saved value or None
    sessions.save(client_id, game_id, value)       # any plain JSON value
    sessions.account_name(client_id) -> name, or None for a guest
Guests' data lives in memory only; logged-in players' data is written to their account file
(server/accounts.py). Both have the same size limit (accounts.MAX_DATA_BYTES).

Login (only from the /ws/account socket, and never while the tab plays a game: is_playing):
- Logging in moves each game's guest data to the account if the account has nothing saved for
  that game; otherwise the account's data wins and the guest data is dropped. Guest data that
  doesn't fit in the account is dropped too (logged). Then the guest data is cleared.
- Creating an account logs in the same way. Logging out leaves a fresh, empty guest.
- Staying logged in: every status sent while logged in carries a fresh login token
  (accounts.AccountStore.login_token). The tab keeps it (sessionStorage) and sends it back as
  "resume" whenever its account socket connects, which logs the session back in if it had been
  forgotten (a server restart or deploy, or the tab gone longer than SESSION_GRACE). A session
  that is already logged in ignores it; so does a tab that is playing (no reply then).
- Display name: while logged in, the tab sends its display name ("name") whenever it changes,
  and it is saved to the account (each one counts as a save for the rate limits). The status
  sent after logging in carries the saved one (displayName), and the tab switches to it. A
  guest's display name stays in the browser (the server ignores "name" from guests).

Hard limits (turtle.py shuts the site down): data over MAX_DATA_BYTES, more than
MAX_SAVES_PER_SESSION saves by one session or MAX_SAVES_TOTAL saves site-wide within
SAVE_WINDOW seconds, and the account count (accounts.MAX_ACCOUNTS).

/ws/account?client=<uuid> messages:
    client -> server  {"type": "register" | "login", "name", "password"}, {"type": "logout"},
                      {"type": "resume", "token"}                 log back in with a saved token
                      {"type": "name", "name": display name}     (logged in only; no reply)
    server -> client  {"type": "account", "user": name | null, "displayName": text | null,
                       "token": login token | null}              on connect, after each change
                                                                 and in reply to "resume"
                      {"type": "error", "message"}               a request was refused
"""

import asyncio
import json
import logging
import time
from collections import deque

from server import accounts
from server.accounts import AccountError, AccountStore
from server.turtle import turtle
from server.utils import CLIENT_ID, clean_text

log = logging.getLogger("sessions")

SESSION_GRACE = 60  # seconds without any connection before a session ends
SAVE_WINDOW = 10.0  # seconds
MAX_SAVES_PER_SESSION = 20
MAX_SAVES_TOTAL = 200
FAILED_LOGIN_DELAY = 1.0  # seconds before answering a wrong password (slows guessing)

CLOSE_INVALID = 1008
_DUMMY_PASSWORD = accounts.hash_password("not a password")  # so unknown names take as long as known ones


class Session:
    def __init__(self, client_id):
        self.client_id = client_id
        self.account = None  # lowercase account name, or None for a guest
        self.guest = {}  # game id -> value (guests only)
        self.connections = 0
        self.expiry = None  # pending end-of-session task while nothing is connected
        self.saves = deque()  # times of recent saves


class Sessions:
    def __init__(self, store=None, is_playing=None):
        self.store = store if store is not None else AccountStore(None)
        self.is_playing = is_playing or (lambda client_id: False)  # set by main.py to Rooms.is_playing
        self.sessions = {}  # client id -> Session
        self._saves = deque()  # times of recent saves, site-wide
        self._sockets = {}  # client id -> set of open /ws/account sockets

    # --- Lifetime ---------------------------------------------------------------------

    def attach(self, client_id):
        """Something of this tab connected (a room seat or the account socket)."""
        session = self._session(client_id)
        session.connections += 1
        if session.expiry:
            session.expiry.cancel()
            session.expiry = None
        return session

    def detach(self, client_id):
        session = self.sessions.get(client_id)
        if session is None:
            return
        session.connections = max(0, session.connections - 1)
        if session.connections == 0:
            self._expire_later(session)

    def _session(self, client_id):
        session = self.sessions.get(client_id)
        if session is None:
            session = self.sessions[client_id] = Session(client_id)
            self._expire_later(session)  # cancelled by attach(); ends stray sessions otherwise
        return session

    def _expire_later(self, session):
        if session.expiry:
            session.expiry.cancel()
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return  # no event loop (plain unit tests): sessions end only through end()
        session.expiry = loop.create_task(self._expire(session))

    async def _expire(self, session):
        await asyncio.sleep(SESSION_GRACE)
        if session.connections == 0 and self.sessions.get(session.client_id) is session:
            self.end(session.client_id)

    def end(self, client_id):
        """End a session now: guest data and the login are forgotten."""
        session = self.sessions.pop(client_id, None)
        if session and session.expiry and session.expiry is not _current_task():
            session.expiry.cancel()

    # --- Game data --------------------------------------------------------------------

    def account_name(self, client_id):
        session = self.sessions.get(client_id)
        if session is None or session.account is None:
            return None
        record = self.store.get(session.account)
        return record["name"] if record else None

    def display_name(self, client_id):
        """The display name saved to the tab's account, or None (guest, or nothing saved yet)."""
        session = self.sessions.get(client_id)
        if session is None or session.account is None:
            return None
        return self.store.display_name(session.account)

    def set_display_name(self, client_id, text):
        """Save the tab's display name to its account. Guests: ignored (it stays in the browser)."""
        session = self.sessions.get(client_id)
        text = clean_text(text, accounts.MAX_DISPLAY_NAME)
        if session is None or session.account is None or not text:
            return
        if text == self.store.display_name(session.account):
            return
        self._count_save(session, "display name")
        self.store.set_display_name(session.account, text)

    def load(self, client_id, game_id):
        session = self._session(client_id)
        if session.account is not None:
            return self.store.load(session.account, game_id)
        if game_id not in session.guest:
            return None
        return json.loads(accounts.to_json(session.guest[game_id]))

    def save(self, client_id, game_id, value):
        session = self._session(client_id)
        text = accounts.to_json(value)  # ValueError for non-JSON data (a game bug, not an attack)
        self._count_save(session, game_id)
        if session.account is not None:
            self.store.save(session.account, game_id, value)
            return
        guest = {**session.guest, game_id: json.loads(text)}
        size = accounts.data_size(guest)
        if size > accounts.MAX_DATA_BYTES:
            turtle(f"Guest saved data would be {size} bytes, more than MAX_DATA_BYTES "
                   f"({accounts.MAX_DATA_BYTES}) (game {game_id})")
        session.guest = guest

    def _count_save(self, session, game_id):
        now = time.monotonic()
        for times in (session.saves, self._saves):
            while times and now - times[0] > SAVE_WINDOW:
                times.popleft()
        if len(session.saves) >= MAX_SAVES_PER_SESSION:
            turtle(f"Too many saves: one session saved more than {MAX_SAVES_PER_SESSION} times "
                   f"in {SAVE_WINDOW:g} s (game {game_id})")
        if len(self._saves) >= MAX_SAVES_TOTAL:
            turtle(f"Too many saves: more than {MAX_SAVES_TOTAL} site-wide in {SAVE_WINDOW:g} s (game {game_id})")
        session.saves.append(now)
        self._saves.append(now)

    # --- Login ------------------------------------------------------------------------

    def _check_not_playing(self, client_id):
        if self.is_playing(client_id):
            raise AccountError("You can't log in or out during a game.")

    async def register(self, client_id, name, password):
        self._check_not_playing(client_id)
        accounts.check_name(name)
        accounts.check_new_password(password)
        if self.store.get(name) is not None:
            raise AccountError("That name is taken.")
        record = await asyncio.to_thread(accounts.hash_password, password)
        self._check_not_playing(client_id)  # may have changed while hashing
        self.store.create(name, record)
        self._log_in(self._session(client_id), name.lower())

    async def login(self, client_id, name, password):
        self._check_not_playing(client_id)
        record = self.store.get(name) if isinstance(name, str) else None
        stored = record["password"] if record else _DUMMY_PASSWORD
        ok = isinstance(password, str) and len(password) <= accounts.MAX_PASSWORD
        ok = await asyncio.to_thread(accounts.check_password, password if ok else "", stored) and ok
        if not ok or record is None:
            await asyncio.sleep(FAILED_LOGIN_DELAY)
            raise AccountError("Wrong name or password.")
        self._check_not_playing(client_id)
        self._log_in(self._session(client_id), name.lower())

    def resume(self, client_id, token):
        """Log a forgotten session back in from a login token. Returns False if nothing should be
        answered (the tab is playing); a bad token just leaves it a guest."""
        session = self._session(client_id)
        if session.account is not None:
            return True
        if self.is_playing(client_id):
            return False
        key = self.store.check_login_token(token)
        if key is not None:
            self._log_in(session, key)
        return True

    def logout(self, client_id):
        self._check_not_playing(client_id)
        session = self._session(client_id)
        session.account = None
        session.guest = {}

    def bind(self, client_id, name):
        """Log a tab in without a password, creating the account if needed (tests and tools only)."""
        if self.store.get(name) is None:
            self.store.create(name, accounts.hash_password("", iterations=1))
        self._log_in(self._session(client_id), name.lower())

    def _log_in(self, session, key):
        for game_id, value in session.guest.items():
            if self.store.has(key, game_id):
                continue  # the account's own data wins
            if self.store.fits(key, game_id, value):
                self.store.save(key, game_id, value)
            else:
                log.warning("Guest data for %s didn't fit in account %s; dropped", game_id, key)
        session.guest = {}
        session.account = key

    # --- /ws/account ------------------------------------------------------------------

    async def handle(self, ws):
        client_id = ws.query.get("client", "")
        if not CLIENT_ID.match(client_id):
            await ws.close(CLOSE_INVALID)
            return
        self.attach(client_id)
        sockets = self._sockets.setdefault(client_id, set())
        sockets.add(ws)
        try:
            await self._send_status(client_id, [ws])
            while (raw := await ws.recv()) is not None:
                try:
                    data = json.loads(raw)
                except ValueError:
                    continue
                if not isinstance(data, dict):
                    continue
                kind = data.get("type")
                try:
                    if kind == "register":
                        await self.register(client_id, data.get("name"), data.get("password"))
                    elif kind == "login":
                        await self.login(client_id, data.get("name"), data.get("password"))
                    elif kind == "logout":
                        self.logout(client_id)
                    elif kind == "resume":
                        if not self.resume(client_id, data.get("token")):
                            continue
                    elif kind == "name":
                        self.set_display_name(client_id, data.get("name"))
                        continue  # no reply: nothing the tab doesn't already know
                    else:
                        continue
                except AccountError as error:
                    await ws.send(json.dumps({"type": "error", "message": str(error)}))
                    continue
                await self._send_status(client_id, list(sockets))
        finally:
            sockets.discard(ws)
            if not sockets:
                self._sockets.pop(client_id, None)
            self.detach(client_id)

    async def _send_status(self, client_id, sockets):
        user = self.account_name(client_id)
        text = json.dumps({"type": "account", "user": user, "displayName": self.display_name(client_id),
                           "token": self.store.login_token(user) if user else None})
        await asyncio.gather(*(ws.send(text) for ws in sockets))


def _current_task():
    try:
        return asyncio.current_task()
    except RuntimeError:
        return None
