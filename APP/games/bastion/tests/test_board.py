"""Bastion: board rules on fixture content (placement, rotation, "next to", links, raid protection).
Run: python3 -I tools/run_tests.py bastion
"""

import importlib
import unittest

from gamekit import LobbyError

helpers = importlib.import_module("games.bastion.tests.helpers")
attacks = importlib.import_module("games.bastion.logic.attacks")
build = helpers.build


class PlacementTests(helpers.FixtureCase):
    def test_requirement_must_hold(self):
        match = helpers.new_match(self)
        with self.assertRaisesRegex(LobbyError, "next to forest"):
            match.board.check("mill", 0, 4, 3)
        self.assertEqual(match.board.check("mill", 0, 1, 1), [(1, 1), (2, 1)])

    def test_only_empty_grass_on_the_board(self):
        board = helpers.new_match(self).board
        for x, y in ((3, 2), (0, 0), (5, 4), (7, 3)):  # keep, forest, mountain, off the edge
            with self.assertRaises(LobbyError):
                board.check("ell", 0, x, y)
        board.place("wall", 0, 1, 3)  # (1,3) (2,3); buildings may go over roads, not walls
        with self.assertRaisesRegex(LobbyError, "empty grass"):
            board.check("hut", 0, 2, 3)

    def test_rotation_turns_the_footprint(self):
        board = helpers.new_match(self).board
        footprints = [sorted(board.footprint("ell", r, 4, 2)) for r in range(4)]
        self.assertEqual(len({tuple(f) for f in footprints}), 4)
        self.assertTrue(all(len(f) == 3 for f in footprints))
        built = board.place("ell", 1, 4, 2)
        self.assertEqual(sorted(built.cells), footprints[1])

    def test_unsold_structures_cant_be_built(self):
        with self.assertRaisesRegex(LobbyError, "can't be built"):
            helpers.new_match(self).board.check("keep", 0, 5, 1)


class NearTests(helpers.FixtureCase):
    def test_counts_distinct_buildings_but_tile_cells(self):
        match = helpers.new_match(self)
        shop = build(match, "shop", 6, 1)
        build(match, "field", 4, 0)  # cells (4,0) (5,0) (4,1) (5,1): two touch the shop
        match.board.place("road", 1, 7, 0)  # (7,0) (7,1): one touches the shop
        match.board.place("road", 0, 6, 2)  # (6,2) (7,2): one touches the shop
        self.assertEqual(match.board.near(shop.cells, "field"), 1)
        self.assertEqual(match.board.near(shop.cells, "road"), 2)

    def test_terrain_and_empty_grass(self):
        board = helpers.new_match(self).board
        self.assertEqual(board.near([(1, 1)], "forest"), 2)
        self.assertEqual(board.near([(5, 3)], "empty"), 4)
        board.place("hut", 0, 4, 3)
        self.assertEqual(board.near([(5, 3)], "empty"), 3)
        self.assertEqual(board.near([(5, 4)], "mountain"), 1)


class LinkTests(helpers.FixtureCase):
    def test_next_to_a_depot(self):
        match = helpers.new_match(self)
        self.assertEqual(match.board.link(build(match, "shop", 4, 2)), "depot")

    def test_road_reaching_a_depot(self):
        match = helpers.new_match(self)
        shop = build(match, "shop", 6, 3)
        self.assertIsNone(match.board.link(shop))
        match.board.place("road", 0, 4, 2)  # (4,2) touches the keep, (5,2)
        match.board.place("road", 1, 6, 1)  # (6,1) (6,2): touches (5,2) and the shop
        self.assertEqual(match.board.link(shop), "road")
        match.board.ruin((5, 2))  # raids break roads
        self.assertIsNone(match.board.link(shop))

    def test_a_ruined_depot_takes_nothing(self):
        match = helpers.new_match(self)
        build(match, "yard", 6, 3)
        shop = build(match, "shop", 5, 3)
        self.assertEqual(match.board.link(shop), "depot")
        match.board.structures[match.board.at[(6, 3)]].ruined.add((6, 3))
        self.assertIsNone(match.board.link(shop))


class RaidTests(helpers.FixtureCase):
    def test_walls_and_towers_protect(self):
        match = helpers.new_match(self)
        hut = build(match, "hut", 1, 4)
        far = build(match, "hut", 6, 0)
        self.assertEqual(match.board.raid_targets(), [(1, 4), (6, 0)])
        match.board.place("wall", 0, 1, 5)
        build(match, "tower", 7, 1)
        self.assertFalse(match.board.raid_targets())
        self.assertTrue(match.board.protected(hut.cells[0]) and match.board.protected(far.cells[0]))

    def test_the_keep_is_never_raided(self):
        self.assertEqual(helpers.new_match(self).board.raid_targets(), [])

    def test_raids_break_walls_when_all_is_protected(self):
        match = helpers.new_match(self)
        hut = build(match, "hut", 1, 4)
        match.board.place("wall", 0, 1, 5)
        attacks.ruin(match, 1, [])
        self.assertEqual(len(match.board.walls), 1)
        self.assertFalse(hut.ruined)

    def test_preferred_kinds_first(self):
        match = helpers.new_match(self)
        build(match, "hut", 6, 0)
        shop = build(match, "shop", 1, 4)
        attacks.ruin(match, 1, ["shop"])
        self.assertEqual(shop.ruined, {(1, 4)})

    def test_last_tile_destroys_the_building(self):
        match = helpers.new_match(self)
        field = build(match, "field", 4, 3)
        for cell in field.cells[:-1]:
            self.assertIsNone(match.board.ruin(cell))
        self.assertIs(match.board.ruin(field.cells[-1]), field)
        self.assertNotIn(field.uid, match.board.structures)
        self.assertNotIn((4, 3), match.board.at)


if __name__ == "__main__":
    unittest.main()
