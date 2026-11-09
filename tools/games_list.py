"""Build the home page's game list (games.json) from APP/games. deploy.sh runs this.

    python3 -I tools/games_list.py APP/games > games.json

Each entry: {"id", "name", "description", "players"?}. name/description come from the game's
game.json; "players" is a short label from the Game class's MIN_PLAYERS / MAX_PLAYERS (read by
importing games.<id>.server, as the server does), shown as a badge on the home page:
"2" (min == max), "1+" (max is the lobby default, i.e. no real cap) or "2–4". A game that
fails to import is still listed, without the label. Sorted by name.

Paths: reads only the games folder given (and imports from its parent, APP); writes stdout.
"""

import importlib
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # never leave __pycache__ folders in APP (deploy copies it)

NO_CAP = 16  # LobbyGame.MAX_PLAYERS default: a game that keeps it has no real cap


def players_label(low, high):
    """Badge text for a player range."""
    low = max(1, low)
    if high >= NO_CAP:
        return f"{low}+"
    if high <= low:
        return str(low)
    return f"{low}–{high}"


def game_label(game_id):
    """The players label for a game, or None if its server can't be imported."""
    try:
        game = importlib.import_module(f"games.{game_id}.server").Game
        return players_label(int(game.MIN_PLAYERS), int(game.MAX_PLAYERS))
    except Exception as error:  # a broken game must not break the list
        print(f"games_list: no player count for {game_id}: {error}", file=sys.stderr)
        return None


def build(games_dir):
    games_dir = Path(games_dir).resolve()
    app_dir = str(games_dir.parent)
    if app_dir not in sys.path:
        sys.path.insert(0, app_dir)
    games = []
    for meta in sorted(games_dir.glob("*/game.json")):
        info = json.loads(meta.read_text())
        entry = {"id": meta.parent.name, "name": info["name"], "description": info.get("description", "")}
        label = game_label(meta.parent.name)
        if label:
            entry["players"] = label
        games.append(entry)
    return sorted(games, key=lambda g: g["name"].lower())


def main(argv):
    if len(argv) != 2:
        print("usage: games_list.py <APP/games folder>", file=sys.stderr)
        return 2
    json.dump(build(argv[1]), sys.stdout, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
