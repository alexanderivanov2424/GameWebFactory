"""Create a new game folder from the new-game skill's templates (for agents, in the pod).

    python3 -I tools/new_game.py <game-id> --name "Game Name" [--description "One sentence."]

Copies .claude/skills/new-game/templates/ to APP/games/<game-id>/ and fills in the game id,
name and description ({{GAME_ID}}, {{GAME_NAME}}, {{DESCRIPTION}} in the templates). The
result passes `python3 -I tools/run_tests.py <game-id>` straight away: a placeholder
round-robin game whose TODOs say what to write next (`grep -rn TODO APP/games/<game-id>`).

    game.json              name + description for the home page
    server.py              rules docstring; class Game(LobbyGame): lobby side (SETTINGS, ACTIONS)
    logic/__init__.py      what each module in logic/ holds
    logic/match.py         class Match: the rules and state of one game
    client/index.html      page with the shared script tags, lobby and game sections
    client/game.js         AppLobby.connect + render functions
    tests/test_<id>.py     rules tests (Match) and lobby tests (gamekit.sim.Sim)
    NOTES.md               developer notes: what to learn from it, map, pitfalls

Refuses to touch an existing folder. Builds the game in a temporary folder next to the
destination and renames it into place, so a failure never leaves a half-made game.
--games-dir (default APP/games) exists for tools/tests/test_new_game.py.
Touches nothing outside the project folder.
"""

import argparse
import html
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / ".claude" / "skills" / "new-game" / "templates"
GAMES_DIR = ROOT / "APP" / "games"

GAME_ID = re.compile(r"^[a-z0-9][a-z0-9_-]*$")  # server/main.py loads [a-z0-9_-]+
MAX_ID, MAX_NAME, MAX_DESCRIPTION = 40, 40, 160
# Kept out of the name and description so they can go into Python, JSON, JS and HTML as is.
FORBIDDEN = set('"\\<>`')
DEFAULT_DESCRIPTION = "TODO One short sentence shown on the home page."
TEXT_SUFFIXES = {".py", ".json", ".js", ".html", ".md", ".css", ".txt"}
SKIP = {"__pycache__"}


class Error(Exception):
    pass


def default_name(game_id):
    return " ".join(word.capitalize() for word in re.split(r"[-_]+", game_id) if word)


def check(game_id, name, description):
    if not GAME_ID.match(game_id) or len(game_id) > MAX_ID:
        raise Error(f"Game id {game_id!r}: use lowercase letters, digits, - and _ (starting with a "
                    f"letter or digit, at most {MAX_ID} characters).")
    for label, value, limit in (("Name", name, MAX_NAME), ("Description", description, MAX_DESCRIPTION)):
        if not value.strip():
            raise Error(f"{label} is empty.")
        if len(value) > limit:
            raise Error(f"{label} is longer than {limit} characters.")
        bad = sorted({c for c in value if c in FORBIDDEN or not c.isprintable()})
        if bad:
            raise Error(f"{label} can't contain {' '.join(repr(c) for c in bad)}.")


def fill(text, suffix, values):
    for key, value in values.items():
        if suffix == ".html":
            value = html.escape(value, quote=False)
        elif suffix == ".json":
            value = json.dumps(value)[1:-1]
        text = text.replace("{{" + key + "}}", value)
    return text


def destination(relative, game_id):
    if relative == Path("tests") / "test_game.py":
        return Path("tests") / f"test_{game_id.replace('-', '_')}.py"
    return relative


def create(game_id, name=None, description=None, games_dir=GAMES_DIR, templates=TEMPLATES):
    """Create games_dir/<game_id> from the templates; return the list of files created."""
    name = (name or default_name(game_id)).strip()
    description = (description or DEFAULT_DESCRIPTION).strip()
    check(game_id, name, description)
    games_dir = Path(games_dir)
    target = games_dir / game_id
    if target.exists():
        raise Error(f"{target} already exists; pick another id or work on that game (game-dev skill).")
    if not templates.is_dir():
        raise Error(f"Templates not found: {templates}")
    values = {"GAME_ID": game_id, "GAME_NAME": name, "DESCRIPTION": description}

    games_dir.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".new-{game_id}-", dir=games_dir))
    created = []
    try:
        for source in sorted(templates.rglob("*")):
            relative = source.relative_to(templates)
            if source.is_dir() or SKIP & set(relative.parts):
                continue
            relative = destination(relative, game_id)
            out = staging / relative
            out.parent.mkdir(parents=True, exist_ok=True)
            if source.suffix in TEXT_SUFFIXES:
                text = fill(source.read_text(encoding="utf-8"), source.suffix, values)
                left = re.findall(r"\{\{[A-Z_]+\}\}", text)
                if left:
                    raise Error(f"{relative}: unknown placeholder(s) {', '.join(sorted(set(left)))}")
                out.write_text(text, encoding="utf-8")
            else:
                shutil.copyfile(source, out)
            created.append(relative)
        umask = os.umask(0)
        os.umask(umask)
        staging.chmod(0o777 & ~umask)  # mkdtemp makes it 700; give it a normal folder's mode
        staging.rename(target)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return created


def main(argv):
    parser = argparse.ArgumentParser(description="Create APP/games/<game-id>/ from the new-game templates.")
    parser.add_argument("game_id", help="folder name and id: lowercase letters, digits, - and _")
    parser.add_argument("--name", help="display name (default: from the id)")
    parser.add_argument("--description", help="one sentence for the home page")
    parser.add_argument("--games-dir", default=str(GAMES_DIR), help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        created = create(args.game_id, args.name, args.description, Path(args.games_dir))
    except Error as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    target = Path(args.games_dir) / args.game_id
    try:
        shown = target.resolve().relative_to(ROOT)
    except ValueError:
        shown = target
    print(f"Created {shown}/:")
    for path in created:
        print(f"  {path}")
    print("\nNext:")
    print(f"  1. grep -rn TODO {shown}   (replace every TODO; rules go in logic/, lobby glue in server.py)")
    print(f"  2. python3 -I tools/run_tests.py {args.game_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
