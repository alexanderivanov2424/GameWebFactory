"""gamekit.shapes: parsing polyomino rows and turning shapes.
Run: python3 -I tools/run_tests.py gamekit
"""

import unittest

from gamekit.shapes import parse, rotate, rotations


class ShapeTests(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(parse(["##", "#."]), ([(0, 0), (0, 1), (1, 0)], 2, 2))
        self.assertEqual(parse(["xo"], filled="x"), ([(0, 0)], 1, 2))

    def test_parse_refuses_bad_rows(self):
        for rows in ([], ["##", "#"], [".."], "##", [1], ["######"], ["#"] * 6):
            with self.assertRaises(ValueError):
                parse(rows)
        with self.assertRaises(ValueError):
            parse(["####"], max_size=3)

    def test_quarter_turn_clockwise(self):
        cells, h, w = parse(["###", "#.."])
        turned, th, tw = rotate(cells, h, w)
        self.assertEqual((th, tw), (3, 2))
        self.assertEqual(sorted(turned), [(0, 0), (0, 1), (1, 1), (2, 1)])  # "##" / ".#" / ".#"

    def test_four_turns_come_back_and_extra_fields_stay(self):
        cells = [(0, 0, "a"), (0, 1, "b"), (1, 0, "c")]
        pieces, sizes = rotations(cells, 2, 2)
        self.assertEqual(len(pieces), 4)
        back, h, w = rotate(pieces[3], *sizes[3])
        self.assertEqual((sorted(back), h, w), (sorted(cells), 2, 2))
        self.assertEqual(sorted(c[2] for c in pieces[1]), ["a", "b", "c"])

    def test_never_mirrored(self):
        pieces, _ = rotations(parse(["##.", ".##"])[0], 2, 3)  # an S: its mirror (Z) never appears
        z = sorted(parse([".##", "##."])[0])
        self.assertNotIn(z, [sorted(p) for p in pieces])


if __name__ == "__main__":
    unittest.main()
