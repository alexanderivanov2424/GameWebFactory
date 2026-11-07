"""tools/new_game.py (scaffolds a game from the new-game skill's templates).

The end-to-end test generates a game into a temporary games/ folder, puts it on sys.path (the
`games` package has no __init__.py, so it picks the folder up) and runs the generated game's
own tests through the real lobby: the templates must always produce a passing game.
"""

import contextlib
import importlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))

import jscheck  # noqa: E402

_spec = importlib.util.spec_from_file_location("tools_new_game", TOOLS / "new_game.py")
tool = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tool)

GAME_ID = "zz-scaffold-check"  # not a real game's id
EXPECTED = {
    "game.json", "server.py", "NOTES.md", "logic/__init__.py", "logic/match.py",
    "client/index.html", "client/game.js", "tests/test_zz_scaffold_check.py",
}


class CreateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.games = self.root / "games"

    def tearDown(self):
        self.tmp.cleanup()

    def create(self, game_id=GAME_ID, name="Scaffold & Check", description="Checks the templates."):
        return tool.create(game_id, name, description, games_dir=self.games)

    def test_files_and_placeholders(self):
        created = self.create()
        folder = self.games / GAME_ID
        self.assertEqual({p.as_posix() for p in created}, EXPECTED)
        self.assertEqual([p.name for p in self.games.iterdir()], [GAME_ID])  # no staging folder left
        for path in folder.rglob("*"):
            if path.is_file():
                self.assertNotIn("{{", path.read_text(encoding="utf-8"), path)
        info = json.loads((folder / "game.json").read_text())
        self.assertEqual(info, {"name": "Scaffold & Check", "description": "Checks the templates."})
        self.assertIn("<title>Scaffold &amp; Check</title>", (folder / "client/index.html").read_text())
        self.assertIn(f'AppLobby.connect("{GAME_ID}"', (folder / "client/game.js").read_text())
        for path in folder.rglob("*.py"):
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
        for path in folder.rglob("*.js"):
            self.assertEqual(jscheck.check(str(path)), "ok", path)

    def test_default_name(self):
        self.create(name=None, description=None)
        info = json.loads((self.games / GAME_ID / "game.json").read_text())
        self.assertEqual(info["name"], "Zz Scaffold Check")
        self.assertTrue(info["description"].startswith("TODO"))

    def test_refuses_existing_folder(self):
        (self.games / GAME_ID).mkdir(parents=True)
        (self.games / GAME_ID / "server.py").write_text("keep me")
        with self.assertRaisesRegex(tool.Error, "already exists"):
            self.create()
        self.assertEqual((self.games / GAME_ID / "server.py").read_text(), "keep me")

    def test_refuses_bad_ids_and_text(self):
        for game_id in ("Tanks", "my game", "-x", "a/b", "", "x" * 41):
            with self.assertRaises(tool.Error, msg=game_id):
                self.create(game_id=game_id)
        for name in ('Say "hi"', "a<b>", "back\\slash", "two\nlines", "   ", "x" * 41):
            with self.assertRaises(tool.Error, msg=name):
                self.create(name=name)
        self.assertFalse(self.games.exists() and any(self.games.iterdir()))

    def test_unknown_placeholder_leaves_nothing(self):
        templates = self.root / "templates"
        templates.mkdir()
        (templates / "server.py").write_text('"""{{GAME_NAME}} {{NOPE}}"""\n')
        with self.assertRaisesRegex(tool.Error, "NOPE"):
            tool.create(GAME_ID, "X", "Y", games_dir=self.games, templates=templates)
        self.assertEqual(list(self.games.iterdir()), [])

    def test_main(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertEqual(tool.main([GAME_ID, "--games-dir", str(self.games)]), 0)
            self.assertEqual(tool.main([GAME_ID, "--games-dir", str(self.games)]), 1)  # exists now
        self.assertIn("run_tests.py zz-scaffold-check", out.getvalue())
        self.assertIn("already exists", err.getvalue())


class GeneratedGameTests(unittest.TestCase):
    """The generated game imports like the server imports games, and its own tests pass."""

    def test_generated_game_passes_its_tests(self):
        with tempfile.TemporaryDirectory() as tmp:
            tool.create(GAME_ID, "Scaffold Check", "x", games_dir=Path(tmp) / "games")
            sys.path.insert(0, tmp)
            try:
                importlib.invalidate_caches()
                tests = Path(tmp) / "games" / GAME_ID / "tests" / "test_zz_scaffold_check.py"
                spec = importlib.util.spec_from_file_location("tests_zz_scaffold_check", tests)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                suite = unittest.defaultTestLoader.loadTestsFromModule(module)
                result = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
                self.assertGreater(result.testsRun, 5)
                self.assertTrue(result.wasSuccessful(), result.failures + result.errors)
            finally:
                sys.path.remove(tmp)
                for name in [n for n in sys.modules if n.startswith(f"games.{GAME_ID}")]:
                    del sys.modules[name]


if __name__ == "__main__":
    unittest.main()
