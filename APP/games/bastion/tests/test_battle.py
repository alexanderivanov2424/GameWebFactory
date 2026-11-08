"""Bastion: siege simulation tests (logic/battle.py) with fixture cards and enemies (helpers.py).

Run: python3 -I tools/run_tests.py bastion
"""

import importlib
import unittest

helpers = importlib.import_module("games.bastion.tests.helpers")
wave = helpers.wave


def setUpModule():
    helpers.install()


def tearDownModule():
    helpers.remove()


def arrived(result):
    return result.summary["leaked"]


class KeepTests(unittest.TestCase):
    def test_undefended_enemies_damage_the_keep(self):
        match = helpers.new_match()
        result = helpers.siege(match, wave("t-grunt", 3))
        self.assertEqual(result.keep, 30 - 3 * 2)
        self.assertTrue(result.held)
        self.assertEqual(arrived(result), 3)

    def test_keep_can_fall(self):
        match = helpers.new_match()
        result = helpers.siege(match, wave("t-grunt", 3), keep=4)
        self.assertFalse(result.held)

    def test_tower_kills_enemies_in_range(self):
        match = helpers.new_match()
        helpers.build(match, "t-tower", 3, 1)
        result = helpers.siege(match, wave("t-grunt", 2, gap=10))
        self.assertEqual(result.summary["kills"], 2)
        self.assertEqual(result.keep, 30)

    def test_health_scale_makes_enemies_tougher(self):
        match = helpers.new_match()
        helpers.build(match, "t-tower", 3, 1)
        self.assertEqual(helpers.siege(match, wave("t-grunt"), hp_scale=1).summary["kills"], 1)
        self.assertEqual(helpers.siege(match, wave("t-grunt"), hp_scale=10).summary["kills"], 0)


class BlockingTests(unittest.TestCase):
    def test_wall_blocks_and_breaks(self):
        match = helpers.new_match()
        helpers.build(match, "t-wall", 3, 2)
        result = helpers.siege(match, wave("t-grunt"))
        self.assertEqual(arrived(result), 1)  # it broke through in the end
        self.assertIsNone(match.board.at(3, 2))  # destroyed walls are removed
        self.assertEqual(result.summary["wallsLost"], 1)

    def test_walls_keep_their_damage(self):
        match = helpers.new_match()
        wall = helpers.build(match, "t-wall", 3, 2, level=3)  # 30 hp; a grunt hits 5 per tick
        helpers.build(match, "t-tower", 3, 1)
        helpers.siege(match, wave("t-grunt"))
        self.assertLess(wall.hp, 30)
        self.assertGreater(wall.hp, 0)
        self.assertIs(match.board.at(3, 2), wall)

    def test_flyers_ignore_walls_and_ground_towers(self):
        match = helpers.new_match()
        helpers.build(match, "t-wall", 3, 2, level=3)
        helpers.build(match, "t-tower", 4, 1)
        result = helpers.siege(match, wave("t-flyer"))
        self.assertEqual(arrived(result), 1)
        self.assertEqual(match.board.at(3, 2).hp, 30)

    def test_air_towers_hit_flyers_only(self):
        match = helpers.new_match()
        helpers.build(match, "t-air", 4, 1)
        result = helpers.siege(match, wave("t-flyer"), wave("t-grunt", start=1))
        self.assertEqual(result.summary["kills"], 1)
        self.assertEqual(result.keep, 30 - 2)  # the grunt got through

    def test_squad_blocks_fights_and_respawns(self):
        match = helpers.new_match()
        helpers.build(match, "t-barracks", 3, 1)  # 30 hp soldiers on a road cell next to it
        # Each grunt costs the squad 15 hp: the 3rd breaks through, the 4th meets the respawned squad.
        result = helpers.siege(match, wave("t-grunt", 3, gap=6), wave("t-grunt", start=60))
        self.assertEqual(result.summary["kills"], 2)
        squad_hp = [e[3] for e in result.replay["events"] if e[1] == "q"]
        self.assertIn(0, squad_hp)
        self.assertIn(30, squad_hp[squad_hp.index(0):])  # back at full health

    def test_exploding_enemy_blows_up_on_a_blocker(self):
        match = helpers.new_match()
        helpers.build(match, "t-wall", 3, 2, level=3)  # 30 hp
        result = helpers.siege(match, wave("t-bomber"))
        self.assertEqual(match.board.at(3, 2).hp, 5)
        self.assertEqual(arrived(result), 0)


class DamageTests(unittest.TestCase):
    def test_armor_reduces_hits_to_at_least_one(self):
        match = helpers.new_match()
        helpers.build(match, "t-weak", 3, 1)  # 2 damage - 4 armor -> 1 per hit
        result = helpers.siege(match, wave("t-armored"))
        frames = result.replay["frames"]
        self.assertEqual(frames[0][2], 19)

    def test_pierce_ignores_armor(self):
        match = helpers.new_match()
        helpers.build(match, "t-pierce", 3, 1)
        result = helpers.siege(match, wave("t-armored"))
        self.assertEqual(result.replay["frames"][0][2], 18)

    def test_forge_adds_damage(self):
        match = helpers.new_match()
        helpers.build(match, "t-weak", 3, 1)
        helpers.build(match, "t-forge", 4, 1)
        result = helpers.siege(match, wave("t-armored"))
        self.assertEqual(result.replay["frames"][0][2], 20 - (2 + 3 - 4))

    def test_watchtower_adds_range(self):
        match = helpers.new_match()
        helpers.build(match, "t-tower", 6, 0)  # range 1.5: never reaches row 2
        self.assertEqual(helpers.siege(match, wave("t-grunt")).summary["kills"], 0)
        helpers.build(match, "t-watch", 5, 0)
        self.assertEqual(helpers.siege(match, wave("t-grunt")).summary["kills"], 1)

    def test_spikes_hurt_ground_enemies_standing_on_them(self):
        match = helpers.new_match()
        helpers.build(match, "t-spikes", 4, 2)
        result = helpers.siege(match, wave("t-grunt"))
        self.assertEqual(result.summary["kills"], 1)

    def test_tar_slows(self):
        plain = helpers.siege(helpers.new_match(), wave("t-grunt"))
        match = helpers.new_match()
        for x in (2, 3, 4, 5):
            helpers.build(match, "t-tar", x, 2)
        slowed = helpers.siege(match, wave("t-grunt"))
        self.assertGreater(slowed.summary["ticks"], plain.summary["ticks"])

    def test_upgrades_raise_stats(self):
        match = helpers.new_match()
        tower = helpers.build(match, "t-tower", 3, 1)
        self.assertEqual(match.board.public()["3,1"]["damage"], 5)
        tower.level = 3
        self.assertEqual(match.board.public()["3,1"]["damage"], 11)


class SpecialTests(unittest.TestCase):
    def test_summoner_raises_enemies(self):
        result = helpers.siege(helpers.new_match(), wave("t-summoner"))
        kinds = [entry[0] for entry in result.replay["enemies"].values()]
        self.assertEqual(kinds.count("t-grunt"), 2)  # its max

    def test_regeneration(self):
        match = helpers.new_match()
        helpers.build(match, "t-weak", 6, 1)  # only reaches the first cells
        result = helpers.siege(match, wave("t-troll"))
        self.assertEqual(arrived(result), 1)
        hp = [frame[2] for frame in result.replay["frames"] if frame]
        self.assertEqual(hp[-1], 20)  # healed back up after leaving the tower's reach

    def test_healer_heals_others(self):
        match = helpers.new_match()
        helpers.build(match, "t-tower", 7, 1)
        result = helpers.siege(match, wave("t-healer"), wave("t-grunt", start=0))
        self.assertEqual(result.summary["kills"], 0)

    def test_breath_stuns_towers(self):
        match = helpers.new_match()
        helpers.build(match, "t-tower", 3, 1)
        result = helpers.siege(match, wave("t-dragon"), wave("t-grunt", start=2))
        self.assertTrue(any(e[1] == "b" for e in result.replay["events"]))
        self.assertEqual(result.summary["kills"], 0)  # the tower never got to fire

    def test_replay_has_a_frame_per_tick(self):
        result = helpers.siege(helpers.new_match(), wave("t-grunt", 2))
        self.assertEqual(len(result.replay["frames"]), result.replay["ticks"])
        self.assertEqual(set(result.replay["enemies"]), {"1", "2"})


if __name__ == "__main__":
    unittest.main()
