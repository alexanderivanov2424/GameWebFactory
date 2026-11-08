"""User accounts on disk: names, password hashes and the data games save for each account.

Games never use this directly: they call LobbyGame.load_data/save_data (gamekit/lobby.py),
which go through server/sessions.py (guests vs. logged-in players, rate limits).

    store = AccountStore(folder)   # folder=None keeps everything in memory (tests)
    store.create(name, password_record)   # raises AccountError if the name is taken
    store.get(name) -> record or None     # names are case-insensitive
    store.load(name, game_id) -> a copy of the saved value, or None
    store.save(name, game_id, value)      # writes the account file
    store.fits(name, game_id, value) -> True if saving it would stay within MAX_DATA_BYTES
    store.display_name(name) / store.set_display_name(name, text)   # the player's display name
    store.login_token(name) -> signed token that logs this account back in (see below)
    store.check_login_token(token) -> lowercase account name, or None if it isn't valid

Login tokens (so a tab stays logged in across reloads, long disconnects and server restarts):
"<base64 of {"n": lowercase name, "c": account created time, "e": expiry}>.<HMAC-SHA256>", signed
with a key kept in <folder>/LOGIN_KEY_FILE (made once, mode 600; tests without a folder use a
random key per store). Nothing is stored per token: a token stops working when it expires
(LOGIN_TOKEN_DAYS), when the key file is deleted (logs every tab out), or when its account is
deleted (a new account with the same name has a different created time).

One JSON file per account, <folder>/<lowercase name>.json, written atomically (temp file, then
rename): {"name", "password": {"salt", "hash", "iterations"}, "created", "displayName",
"games": {game_id: value}}. displayName is the display name (Settings -> User name, up to
MAX_DISPLAY_NAME characters) last used while logged in; it is restored when logging in.
The folder (accounts_dir()) is $ACCOUNTS_DIRECTORY, else <state dir>/accounts (turtle.state_dir()).
On the host deploy.sh sets ACCOUNTS_DIRECTORY to the Accounts/ folder next to APP (the Dev folder,
git-ignored), so accounts survive deploys and belong to the folder's owner, who runs the server.

Passwords: PBKDF2-HMAC-SHA256 with a random salt (hash_password / check_password); slow on
purpose, so callers run them in a thread (asyncio.to_thread).

Hard limits (breaking one turtles the site, see turtle.py):
- MAX_ACCOUNTS accounts in total: creating one more, or finding more files at startup.
- MAX_DATA_BYTES of saved game data per account (all games together, as compact JSON): a save
  that would go over it, or an account file over it at startup.
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import time
from pathlib import Path

from server.turtle import state_dir, turtle

log = logging.getLogger("accounts")

MAX_ACCOUNTS = 100
MAX_DATA_BYTES = 64 * 1024
NAME = re.compile(r"^[A-Za-z0-9_-]{3,20}$")
MAX_DISPLAY_NAME = 32  # same as the lobby and chat name limit
MAX_PASSWORD = 128  # no minimum: players are told not to use a real password
ITERATIONS = 200_000
LOGIN_TOKEN_DAYS = 30
LOGIN_KEY_FILE = ".login-key"  # not *.json, so it is never read as an account
MAX_TOKEN = 512  # characters


def accounts_dir():
    """Folder holding the account files: $ACCOUNTS_DIRECTORY, else <state dir>/accounts."""
    return Path(os.environ.get("ACCOUNTS_DIRECTORY") or state_dir() / "accounts")


class AccountError(Exception):
    """A request about accounts was refused; the message is shown to the user."""


def check_name(name):
    if not isinstance(name, str) or not NAME.match(name):
        raise AccountError("Names are 3-20 letters, digits, - or _.")
    return name


def check_new_password(password):
    if not isinstance(password, str) or len(password) > MAX_PASSWORD:
        raise AccountError(f"Passwords are at most {MAX_PASSWORD} characters.")
    return password


def hash_password(password, salt=None, iterations=None):
    salt = salt or secrets.token_bytes(16)
    iterations = iterations or ITERATIONS
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return {"salt": salt.hex(), "hash": digest.hex(), "iterations": iterations}


def check_password(password, record):
    """True if `password` matches a hash_password() record."""
    try:
        salt = bytes.fromhex(record["salt"])
        iterations = int(record["iterations"])
        expected = bytes.fromhex(record["hash"])
    except (KeyError, TypeError, ValueError):
        return False
    if not isinstance(password, str) or not 1 <= iterations <= 10_000_000:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return hmac.compare_digest(digest, expected)


def to_json(value):
    """Compact JSON text of a value; raises ValueError if it isn't plain JSON data."""
    try:
        return json.dumps(value, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as error:
        raise ValueError(f"Saved data must be plain JSON data: {error}") from None


def data_size(games):
    return len(to_json(games).encode())


class AccountStore:
    def __init__(self, folder=None):
        self.folder = Path(folder) if folder is not None else None
        self.accounts = {}  # lowercase name -> record
        self._unreadable = set()  # lowercase names whose file couldn't be read: still taken
        self._login_key = None
        if self.folder is not None:
            self.folder.mkdir(parents=True, exist_ok=True)
            self._load_all()

    def _load_all(self):
        files = sorted(self.folder.glob("*.json"))
        if len(files) > MAX_ACCOUNTS:
            turtle(f"{len(files)} account files found, more than MAX_ACCOUNTS ({MAX_ACCOUNTS})")
        for path in files:
            key = path.stem
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
                if not (isinstance(record, dict) and isinstance(record.get("name"), str)
                        and record["name"].lower() == key and isinstance(record.get("games"), dict)):
                    raise ValueError("not an account record")
            except (OSError, ValueError) as error:
                log.error("Skipping account file %s: %s", path.name, error)
                self._unreadable.add(key)
                continue
            if data_size(record["games"]) > MAX_DATA_BYTES:
                turtle(f"Account file {path.name} holds more than MAX_DATA_BYTES ({MAX_DATA_BYTES})")
            display = record.get("displayName")
            if display is not None and not (isinstance(display, str) and 0 < len(display) <= MAX_DISPLAY_NAME):
                log.error("Account file %s: bad displayName dropped", path.name)
                record.pop("displayName")
            self.accounts[key] = record

    def count(self):
        return len(self.accounts) + len(self._unreadable)

    def get(self, name):
        return self.accounts.get(name.lower()) if isinstance(name, str) else None

    def create(self, name, password_record):
        """Add an account. Raises AccountError if the name is taken; turtles past MAX_ACCOUNTS."""
        check_name(name)
        key = name.lower()
        if key in self.accounts or key in self._unreadable:
            raise AccountError("That name is taken.")
        if self.count() >= MAX_ACCOUNTS:
            turtle(f"Account limit reached: MAX_ACCOUNTS ({MAX_ACCOUNTS}) accounts exist and one more was requested")
        record = {"name": name, "password": password_record, "created": int(time.time()), "games": {}}
        self._write(key, record)
        self.accounts[key] = record
        log.info("Account created: %s (%d in total)", name, self.count())
        return record

    def load(self, name, game_id):
        record = self.get(name)
        if record is None or game_id not in record["games"]:
            return None
        return json.loads(to_json(record["games"][game_id]))  # a copy: changing it changes nothing saved

    def display_name(self, name):
        record = self.get(name)
        return record.get("displayName") if record else None

    def set_display_name(self, name, text):
        """Save the display name for an account (it must exist); text is already cleaned."""
        record = self.get(name)
        if record is None:
            raise KeyError(name)
        if not isinstance(text, str) or not 0 < len(text) <= MAX_DISPLAY_NAME:
            raise ValueError("bad display name")
        if record.get("displayName") == text:
            return
        self._write(name.lower(), {**record, "displayName": text})
        record["displayName"] = text

    # --- Login tokens -------------------------------------------------------------------

    def _key(self):
        if self._login_key is None:
            if self.folder is None:
                self._login_key = secrets.token_bytes(32)
            else:
                path = self.folder / LOGIN_KEY_FILE
                try:
                    self._login_key = bytes.fromhex(path.read_text(encoding="ascii").strip())
                except (OSError, ValueError):
                    self._login_key = b""
                if len(self._login_key) < 32:
                    self._login_key = secrets.token_bytes(32)
                    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                    with os.fdopen(fd, "w", encoding="ascii") as file:
                        file.write(self._login_key.hex())
        return self._login_key

    def _sign(self, body):
        return hmac.new(self._key(), body.encode("ascii"), hashlib.sha256).hexdigest()

    def login_token(self, name):
        record = self.get(name)
        if record is None:
            return None
        payload = {"n": record["name"].lower(), "c": record.get("created"),
                   "e": int(time.time()) + LOGIN_TOKEN_DAYS * 86400}
        body = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode("ascii")
        return f"{body}.{self._sign(body)}"

    def check_login_token(self, token):
        if not isinstance(token, str) or len(token) > MAX_TOKEN or token.count(".") != 1:
            return None
        body, signature = token.split(".")
        try:
            if not hmac.compare_digest(signature, self._sign(body)):
                return None
            payload = json.loads(base64.urlsafe_b64decode(body.encode("ascii")))
            name, created, expiry = payload["n"], payload["c"], payload["e"]
        except (ValueError, TypeError, KeyError, UnicodeError):
            return None
        record = self.get(name) if isinstance(name, str) else None
        if record is None or record.get("created") != created:
            return None
        if not isinstance(expiry, int) or expiry < time.time():
            return None
        return name

    def has(self, name, game_id):
        record = self.get(name)
        return record is not None and game_id in record["games"]

    def fits(self, name, game_id, value):
        record = self.get(name)
        return record is not None and data_size({**record["games"], game_id: value}) <= MAX_DATA_BYTES

    def save(self, name, game_id, value):
        """Save a game's value for an account (it must exist). Turtles past MAX_DATA_BYTES."""
        record = self.get(name)
        if record is None:
            raise KeyError(name)
        games = {**record["games"], game_id: json.loads(to_json(value))}
        size = data_size(games)
        if size > MAX_DATA_BYTES:
            turtle(f"Saved data for account {record['name']} would be {size} bytes, "
                   f"more than MAX_DATA_BYTES ({MAX_DATA_BYTES}) (game {game_id})")
        self._write(name.lower(), {**record, "games": games})
        record["games"] = games

    def _write(self, key, record):
        if self.folder is None:
            return
        path = self.folder / f"{key}.json"
        tmp = self.folder / f".{key}.tmp"
        tmp.write_text(json.dumps(record, separators=(",", ":")), encoding="utf-8")
        os.replace(tmp, path)
