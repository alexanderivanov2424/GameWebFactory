"""Feedback: players write free-text feedback in Settings -> Feedback (web/shared/settings.js)
and it is saved as plain text files for the owner (and the `feedback` skill) to read.

    <folder>/<game id or "site">/<client uuid>_<display name>.txt

Each submission is appended to that file under a "--- <date time>" line. The folder
(feedback_dir()) is $FEEDBACK_DIRECTORY, else <state dir>/feedback (turtle.state_dir()); on the
host deploy.sh sets it to Feedback/ next to APP (git-ignored).

/ws/feedback?client=<uuid>   one request per connection; the server answers, then closes it
    client -> server  {"type": "feedback", "game": game id or "site", "name": display name, "text"}
    server -> client  {"type": "feedback", "ok": true}  or  {"type": "error", "message"}

Hard limits (turtle.py shuts the site down; the page checks the size first, so only a
hand-made request can break it): text over MAX_BYTES, more than MAX_PER_TAB submissions from
one tab or MAX_TOTAL site-wide within WINDOW seconds, or the folder growing past MAX_FOLDER_BYTES.
"""

import json
import os
import re
import time
from collections import deque
from pathlib import Path

from server.turtle import state_dir, turtle
from server.utils import CLIENT_ID, clean_text

MAX_BYTES = 50 * 1024  # per submission (UTF-8); same limit in web/shared/settings.js
MAX_FOLDER_BYTES = 100 * 1024 * 1024
WINDOW = 60.0  # seconds
MAX_PER_TAB = 10
MAX_TOTAL = 30
SITE = "site"  # "game" for feedback sent from a page that isn't a game

CLOSE_INVALID = 1008


def feedback_dir():
    """Folder holding the feedback files: $FEEDBACK_DIRECTORY, else <state dir>/feedback."""
    return Path(os.environ.get("FEEDBACK_DIRECTORY") or state_dir() / "feedback")


class FeedbackError(Exception):
    """A harmless request was refused; the message is shown to the player."""


def folder_size(folder):
    return sum(p.stat().st_size for p in Path(folder).rglob("*") if p.is_file())


def file_name(client_id, name):
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", clean_text(name, 32)).strip("_") or "guest"
    return f"{client_id}_{safe}.txt"


class Feedback:
    def __init__(self, folder, games):
        self.folder = Path(folder)
        self.topics = set(games) | {SITE}  # valid "game" values
        self.recent = {}  # client id -> deque of submission times
        self.all = deque()  # submission times, site-wide

    def submit(self, client_id, game, name, text):
        """Append one submission to its file and return the path. Turtles on abuse."""
        self._count(client_id)
        if game not in self.topics:
            raise FeedbackError("Unknown game.")
        text = text.replace("\r\n", "\n").strip() if isinstance(text, str) else ""
        if not text:
            raise FeedbackError("Write something first.")
        size = len(text.encode("utf-8"))
        if size > MAX_BYTES:
            turtle(f"Feedback of {size} bytes, more than MAX_BYTES ({MAX_BYTES}) (game {game})")
        if folder_size(self.folder) + size > MAX_FOLDER_BYTES:
            turtle(f"Feedback folder {self.folder} would grow past {MAX_FOLDER_BYTES} bytes")
        path = self.folder / game / file_name(client_id, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as file:
            file.write(f"--- {time.strftime('%Y-%m-%d %H:%M:%S')}\n{text}\n\n")
        return path

    def _count(self, client_id):
        now = time.monotonic()
        self.recent = {c: t for c, t in self.recent.items() if now - t[-1] <= WINDOW}
        mine = self.recent.setdefault(client_id, deque())
        for times in (mine, self.all):
            while times and now - times[0] > WINDOW:
                times.popleft()
        if len(mine) >= MAX_PER_TAB:
            turtle(f"Too much feedback: one tab sent more than {MAX_PER_TAB} in {WINDOW:g} s")
        if len(self.all) >= MAX_TOTAL:
            turtle(f"Too much feedback: more than {MAX_TOTAL} site-wide in {WINDOW:g} s")
        mine.append(now)
        self.all.append(now)

    async def handle(self, ws):
        client_id = ws.query.get("client", "")
        raw = await ws.recv() if CLIENT_ID.match(client_id) else None
        try:
            data = json.loads(raw) if raw is not None else None
        except ValueError:
            data = None
        if not isinstance(data, dict) or data.get("type") != "feedback":
            await ws.close(CLOSE_INVALID)
            return
        try:
            self.submit(client_id, data.get("game"), data.get("name"), data.get("text"))
            reply = {"type": "feedback", "ok": True}
        except FeedbackError as error:
            reply = {"type": "error", "message": str(error)}
        await ws.send(json.dumps(reply))
        await ws.close()
