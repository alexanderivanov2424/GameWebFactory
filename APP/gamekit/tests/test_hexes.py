"""gamekit.hexes: distances, neighbours, map disks and shape rotations."""

import unittest

from gamekit.hexes import adjacent, dist, disk, neighbors, ring, rotate, rotations


class HexTests(unittest.TestCase):
    def test_neighbors_are_at_distance_one(self):
        self.assertTrue(all(dist("0,0", n) == 1 for n in neighbors("0,0")))
        self.assertEqual(len(set(neighbors("3,-2"))), 6)
        self.assertFalse(adjacent("0,0", "1,1"))

    def test_disk_size(self):
        self.assertEqual(len(disk(0)), 1)
        self.assertEqual(len(disk(3)), 37)
        self.assertTrue(all(dist("0,0", k) <= 3 for k in disk(3)))

    def test_ring(self):
        cells = ring(2, (1, 1))
        self.assertEqual(len(set(cells)), 12)
        self.assertTrue(all(dist("1,1", k) == 2 for k in cells))
        self.assertTrue(all(dist(a, b) == 1 for a, b in zip(cells, cells[1:] + cells[:1])))

    def test_six_turns_come_back(self):
        self.assertEqual(rotate((2, -1), 6), (2, -1))
        self.assertEqual(rotate((1, 0)), (0, 1))

    def test_rotations_keep_shape_connected(self):
        shapes = rotations([(0, 0), (1, 0), (0, 1)])
        self.assertEqual(len(shapes), 6)
        for cells in shapes:
            self.assertEqual(cells[0], (0, 0))
            self.assertEqual(sum(1 for a in cells for b in cells if a < b and dist(f"{a[0]},{a[1]}", f"{b[0]},{b[1]}") == 1), 3)


if __name__ == "__main__":
    unittest.main()
