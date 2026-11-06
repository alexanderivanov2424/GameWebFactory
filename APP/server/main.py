"""App server: site-wide chat at /ws/chat and game rooms at /ws/game/<game-id>.

Run from the APP folder (the folder holding server/, gamekit/ and games/):

    python3 -m server.main

Each game is imported as the package `games.<game-id>` (so a game can split its code into
several modules and use relative imports, e.g. `from . import cards`); its server.py must
define a class `Game` (usually a subclass of gamekit.LobbyGame). A game that fails to import
is logged and skipped; run tools/run_tests.py to catch that before deploying.
"""

import asyncio
import importlib
import logging
import os
import re
from functools import partial
from pathlib import Path

from server import chat, websocket
from server.rooms import Rooms

HOST = "127.0.0.1"  # Only nginx connects directly; it forwards /ws/ here.
PORT = int(os.environ.get("PORT", "8765"))
GAMES_DIR = Path(__file__).resolve().parent.parent / "games"

GAME_ID = re.compile(r"^[a-z0-9_-]+$")
GAME_PATH = re.compile(r"^/ws/game/([a-z0-9_-]+)$")

log = logging.getLogger("main")


def load_game(game_id):
    """Import games/<game_id>/server.py as games.<game_id>.server and return its Game class."""
    return importlib.import_module(f"games.{game_id}.server").Game


def load_games():
    games = {}
    for server_file in sorted(GAMES_DIR.glob("*/server.py")):
        game_id = server_file.parent.name
        if not GAME_ID.match(game_id):
            log.warning("Skipping %s: folder name must be lowercase letters, digits, - or _", game_id)
            continue
        try:
            games[game_id] = load_game(game_id)
        except Exception:
            log.exception("Failed to load game %s", game_id)
    return games


async def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    games = load_games()
    rooms = Rooms(games)
    log.info("Loaded games: %s", ", ".join(games) or "none")

    def route(path):
        if path == "/ws/chat":
            return chat.handle
        match = GAME_PATH.match(path)
        if match and match.group(1) in games:
            return partial(rooms.handle, game_id=match.group(1))
        return None

    server = await websocket.serve(route, HOST, PORT)
    log.info("Listening on %s:%s", HOST, PORT)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
