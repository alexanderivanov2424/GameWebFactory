"""gamekit.data (content files) and gamekit.validate (player input)."""

import json
import logging
import tempfile
import unittest
from pathlib import Path

from gamekit import LobbyError
from gamekit.data import load_json, load_json_dir, text, whole
from gamekit.validate import cell, one_of, whole_number

log = logging.getLogger("test-data")


def parse_card(card_id, data):
    return {"id": card_id, "name": text(data, "name", 10, required=True), "value": whole(data, "value", 0, 9, default=0)}


class DataTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())

    def write(self, name, content):
        (self.folder / name).write_text(content if isinstance(content, str) else json.dumps(content))

    def test_bad_files_are_skipped(self):
        self.write("good.json", {"name": "Good", "value": 3})
        self.write("no-name.json", {"value": 3})
        self.write("Bad Id.json", {"name": "X"})
        self.write("broken.json", "{")
        self.write("too-big.json", {"name": "Big", "value": 10})
        with self.assertLogs(log, level="ERROR") as logs:
            cards = load_json_dir(self.folder, parse_card, log)
        self.assertEqual(list(cards), ["good"])
        self.assertEqual(cards["good"], {"id": "good", "name": "Good", "value": 3})
        self.assertEqual(len(logs.output), 4)

    def test_load_json_default_on_error(self):
        with self.assertLogs(log, level="ERROR"):
            self.assertEqual(load_json(self.folder / "missing.json", lambda d: d, log, default=[]), [])
        self.write("pool.json", {"a": 1})
        self.assertEqual(load_json(self.folder / "pool.json", lambda d: d, log), {"a": 1})


class ValidateTests(unittest.TestCase):
    def test_whole_number(self):
        self.assertEqual(whole_number(50, "HP", 1, 20), 20)
        with self.assertRaisesRegex(LobbyError, "HP must be a whole number"):
            whole_number(True, "HP", 1, 20)
        with self.assertRaisesRegex(LobbyError, "from 1 to 20"):
            whole_number(50, "HP", 1, 20, clamp=False)

    def test_one_of_and_cell(self):
        self.assertEqual(one_of("up", {"up", "down"}, "Bad direction."), "up")
        with self.assertRaisesRegex(LobbyError, "Bad direction"):
            one_of("sideways", {"up", "down"}, "Bad direction.")
        self.assertEqual(cell([1, 2], 3), (1, 2))
        for bad in ([3, 0], [0], "a", [0, 1.0], None):
            with self.assertRaises(LobbyError):
                cell(bad, 3)


if __name__ == "__main__":
    unittest.main()
