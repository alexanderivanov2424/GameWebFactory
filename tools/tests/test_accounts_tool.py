"""tools/accounts.py (the account manager behind accounts.sh): find, select, show, delete."""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "tools_accounts", Path(__file__).resolve().parent.parent / "accounts.py")
tool = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tool)


class FakeService:
    def __init__(self, active=True):
        self.active = active
        self.calls = []

    def is_active(self):
        return self.active

    def stop(self):
        self.calls.append("stop")
        self.active = False
        return True

    def start(self):
        self.calls.append("start")
        self.active = True
        return True


class ToolTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.folder = Path(self.dir.name) / "accounts"
        self.folder.mkdir()
        for name, display in [("Alice", "Ally"), ("bob", "Bobby"), ("carol", "Al's friend")]:
            record = {"name": name, "password": {}, "created": 0, "displayName": display,
                      "games": {"tanks": {"wins": 3}}}
            (self.folder / f"{name.lower()}.json").write_text(json.dumps(record))
        (self.folder / "broken.json").write_text("{not json")
        self.lines = []
        self.answers = []
        self.service = FakeService()
        self.m = tool.Manager(self.folder, self.service, out=self.lines.append,
                              ask=lambda prompt: self.answers.pop(0))

    def text(self):
        return "\n".join(self.lines)

    def files(self):
        return sorted(p.name for p in self.folder.glob("*.json"))

    def test_list_and_find(self):
        self.m.run_command("list")
        self.assertIn("4 of 4 accounts", self.text())
        self.assertIn("(unreadable", self.text())
        self.lines.clear()
        self.m.run_command("find al")  # name or display name, any case
        self.assertIn("2 of 4 accounts matching 'al'", self.text())
        self.assertEqual(self.m.last, ["alice", "carol"])  # carol by display name

    def test_select_by_number_range_name_and_all(self):
        self.m.run_command("list")  # alice, bob, broken, carol
        self.m.run_command("select 2 CAROL")
        self.assertEqual(self.m.selected, ["bob", "carol"])
        self.m.run_command("unselect bob")
        self.m.run_command("select 1-2 nobody")
        self.assertEqual(self.m.selected, ["carol", "alice", "bob"])
        self.assertIn("No account 'nobody'", self.text())
        self.m.run_command("clear")
        self.m.run_command("find bob")
        self.m.run_command("select all")
        self.assertEqual(self.m.selected, ["bob"])
        self.assertIn("accounts (1 selected)> ", self.m.prompt())

    def test_show(self):
        self.m.run_command("show alice broken")
        self.assertIn("Display name:  Ally", self.text())
        self.assertIn("tanks", self.text())
        self.assertIn("Unreadable:", self.text())

    def test_delete_restarts_running_server(self):
        self.m.run_command("select alice broken")
        self.answers = ["yes"]
        self.m.run_command("delete")
        self.assertEqual(self.files(), ["bob.json", "carol.json"])
        self.assertEqual(self.service.calls, ["stop", "start"])
        self.assertEqual(self.m.selected, [])
        self.assertEqual(sorted(p.name for p in self.folder.parent.iterdir()), ["accounts"])  # no backup
        self.assertIn("will be restarted", self.text())

    def test_delete_needs_yes(self):
        self.answers = ["y"]
        self.m.run_command("delete bob")
        self.assertIn("Cancelled", self.text())
        self.assertIn("bob.json", self.files())
        self.assertEqual(self.service.calls, [])

    def test_delete_leaves_stopped_server_alone(self):
        self.service.active = False
        self.answers = ["yes"]
        self.m.run_command("delete bob")
        self.assertNotIn("bob.json", self.files())
        self.assertEqual(self.service.calls, [])

    def test_delete_without_service(self):
        m = tool.Manager(self.folder, None, out=self.lines.append, ask=lambda p: "yes")
        m.run_command("delete carol")
        self.assertNotIn("carol.json", self.files())

    def test_delete_nothing_selected(self):
        self.m.run_command("delete")
        self.assertIn("Nothing selected", self.text())
        self.assertEqual(len(self.files()), 4)

    def test_interactive_quits(self):
        self.answers = ["help", "bogus", "quit"]
        self.m.interactive()
        self.assertIn("Unknown command 'bogus'", self.text())
        self.assertIn("Commands:", self.text())


if __name__ == "__main__":
    unittest.main()
