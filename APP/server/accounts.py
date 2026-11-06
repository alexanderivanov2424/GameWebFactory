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

One JSON file per account, <folder>/<lowercase name>.json, written atomically (temp file, then
rename): {"name", "password": {"salt", "hash", "iterations"}, "created", "displayName",
"games": {game_id: value}}. displayName is the display name (Settings -> User name, up to
MAX_DISPLAY_NAME characters) last used while logged in; it is restored when logging in.
The folder is <state dir>/accounts (see turtle.state_dir()), which survives deploys.

Passwords: PBKDF2-HMAC-SHA256 with a random salt (hash_password / check_password); slow on
purpose, so callers run them in a thread (asyncio.to_thread).

Hard limits (breaking one turtles the site, see turtle.py):
- MAX_ACCOUNTS accounts in total: creating one more, or finding more files at startup.
- MAX_DATA_BYTES of saved game data per account (all games together, as compact JSON): a save
  that would go over it, or an account file over it at startup.
"""

import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import time
from pathlib import Path

from server.turtle import turtle

log = logging.getLogger("accounts")

MAX_ACCOUNTS = 100
MAX_DATA_BYTES = 64 * 1024
NAME = re.compile(r"^[A-Za-z0-9_-]{3,20}$")
MAX_DISPLAY_NAME = 32  # same as the lobby and chat name limit
MAX_PASSWORD = 128  # no minimum: players are told not to use a real password
ITERATIONS = 200_000


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
