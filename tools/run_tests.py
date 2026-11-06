"""Check everything that can be checked without a browser. deploy.sh runs this first.

    python3 -I tools/run_tests.py            # everything
    python3 -I tools/run_tests.py tanks      # one game's tests (plus compile + JS checks)
    python3 -I tools/run_tests.py gamekit    # the shared library's tests
    python3 -I tools/run_tests.py tools      # the host tools' tests (accounts.sh)

Steps (stops with exit code 1 if any fails):
1. Compile every .py file under APP.
2. Import every game exactly as the server does (games.<id>.server) and check it has Game.
3. Run unit tests: every tests/test_*.py under APP/server, APP/gamekit, APP/games/<id> and tools
   (standard-library unittest; APP is on sys.path, so tests import gamekit, gamekit.sim, ...).
4. Syntax-check every .js file under APP/web and APP/games/*/client (tools/jscheck.py).

Safety: tests run with server/turtle.py in test mode (turtle() raises Turtled instead of shutting
the site down), with the state folder ($STATE_DIRECTORY) pointed at a temporary folder and
$ACCOUNTS_DIRECTORY unset (so accounts go there too), so no
test touches real accounts or writes a real TURTLE marker, even when deploy.sh runs this as root.
"""

import importlib.util
import logging
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True  # keep __pycache__ folders out of APP (deploy copies it)

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "APP"
sys.path.insert(0, str(APP))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import jscheck  # noqa: E402


def compile_all():
    failures = []
    for path in sorted(APP.rglob("*.py")):
        try:
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
        except SyntaxError as error:
            failures.append(f"{path.relative_to(ROOT)}:{error.lineno}: {error.msg}")
    return failures


def import_games():
    from server.main import GAMES_DIR, load_game

    failures = []
    for server_file in sorted(GAMES_DIR.glob("*/server.py")):
        game_id = server_file.parent.name
        try:
            game = load_game(game_id)
            if not isinstance(game, type):
                raise TypeError("Game isn't a class")
        except Exception as error:  # noqa: BLE001
            failures.append(f"{game_id}: {type(error).__name__}: {error}")
    return failures


def test_dirs(only):
    dirs = [APP / "server" / "tests", APP / "gamekit" / "tests"]
    dirs += sorted(p / "tests" for p in (APP / "games").iterdir() if p.is_dir())
    dirs.append(ROOT / "tools" / "tests")
    if only:
        dirs = [d for d in dirs if d.parent.name == only]
    return [d for d in dirs if d.is_dir()]


def load_tests(dirs):
    suite = unittest.TestSuite()
    loader = unittest.defaultTestLoader
    for folder in dirs:
        for path in sorted(folder.glob("test_*.py")):
            name = f"tests_{folder.parent.name.replace('-', '_')}_{path.stem}"
            spec = importlib.util.spec_from_file_location(name, path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
            suite.addTests(loader.loadTestsFromModule(module))
    return suite


def js_files():
    files = sorted((APP / "web").rglob("*.js"))
    files += sorted((APP / "games").glob("*/client/**/*.js"))
    return files


def main(argv):
    state = tempfile.mkdtemp(prefix="gwf-tests-")
    os.environ["STATE_DIRECTORY"] = state
    os.environ.pop("ACCOUNTS_DIRECTORY", None)  # never the real accounts
    from server import turtle
    turtle.install_test_handler()
    try:
        return run(argv)
    finally:
        shutil.rmtree(state, ignore_errors=True)


def run(argv):
    only = argv[0] if argv else None
    ok = True
    # Game modules log content problems (bad card files) at import; show only real errors.
    logging.basicConfig(level=logging.ERROR, format="  %(levelname)s %(name)s: %(message)s")

    print("== Compiling Python")
    for failure in compile_all():
        print(" ", failure)
        ok = False

    print("== Importing games")
    for failure in import_games():
        print(" ", failure)
        ok = False

    dirs = test_dirs(only)
    print("== Unit tests:", ", ".join(str(d.relative_to(ROOT)) for d in dirs) or "none found")
    if dirs:
        result = unittest.TextTestRunner(stream=sys.stdout, verbosity=1).run(load_tests(dirs))
        ok &= result.wasSuccessful()

    print("== Checking JavaScript")
    for path in js_files():
        result = jscheck.check(str(path))
        if result != "ok":
            print(f"  {path.relative_to(ROOT)}: {result}")
            ok = False

    print("\nAll checks passed." if ok else "\nCHECKS FAILED (see above).")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
