"""Turtle: the real shutdown (in a child process), the startup refusal and test mode."""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from server import turtle

APP = Path(__file__).resolve().parent.parent.parent


def run_child(code, state):
    env = {**os.environ, "STATE_DIRECTORY": state}
    script = f"import sys; sys.path.insert(0, {str(APP)!r}); {code}"
    return subprocess.run([sys.executable, "-I", "-c", script], env=env, capture_output=True, text=True,
                          timeout=30)


class TurtleTests(unittest.TestCase):
    def test_turtle_exits_and_leaves_a_marker(self):
        with tempfile.TemporaryDirectory() as state:
            done = run_child("from server.turtle import turtle; turtle('limit broken'); print('still running')", state)
            self.assertEqual(done.returncode, turtle.EXIT_CODE)
            self.assertNotIn("still running", done.stdout)
            self.assertIn("limit broken", (Path(state) / turtle.MARKER).read_text())
            self.assertIn("TURTLE: limit broken", done.stderr)

            # While the marker exists, the server refuses to start.
            again = run_child("from server import turtle; turtle.check_startup(); print('started')", state)
            self.assertEqual(again.returncode, turtle.EXIT_CODE)
            self.assertNotIn("started", again.stdout)

    def test_startup_without_marker(self):
        with tempfile.TemporaryDirectory() as state:
            done = run_child("from server import turtle; turtle.check_startup(); print('started')", state)
            self.assertEqual(done.returncode, 0)
            self.assertIn("started", done.stdout)

    def test_test_mode_raises_past_except_exception(self):
        turtle.install_test_handler()
        before = len(turtle.triggered)
        with self.assertRaises(turtle.Turtled):
            try:
                turtle.turtle("in a test")
            except Exception:  # noqa: BLE001 - a game's catch-all must not swallow it
                self.fail("Turtled was caught by except Exception")
        self.assertEqual(turtle.triggered[before:], ["in a test"])
