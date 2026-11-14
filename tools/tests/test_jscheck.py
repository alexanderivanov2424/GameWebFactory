"""tools/jscheck.py: the rough JS syntax check run_tests.py uses (no Node allowed)."""

import importlib.util
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("jscheck", Path(__file__).resolve().parent.parent / "jscheck.py")
jscheck = importlib.util.module_from_spec(spec)
spec.loader.exec_module(jscheck)


def check(code):
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(code)
    try:
        return jscheck.check(f.name)
    finally:
        Path(f.name).unlink()


class JsCheckTests(unittest.TestCase):
    def test_valid_code_passes(self):
        self.assertEqual(check('const a = "x" in o ? f("a", \'b\') : `t ${"y"}`;\nfor (const c of "abc") g(c);\n'), "ok")

    def test_quote_inside_a_string(self):
        self.assertIn("string followed by", check('el("p", {}, "Producers marked "needs a road" deliver");\n'))

    def test_lost_brace(self):
        self.assertNotEqual(check("function f() { return 1;\n"), "ok")


if __name__ == "__main__":
    unittest.main()
