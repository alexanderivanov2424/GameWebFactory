"""Bastion: enemies and the round flow on fixture content (arrival, attack cycle, defeat ways,
win and losses, leaving).
Run: python3 -I tools/run_tests.py bastion
"""

import importlib
import random
import unittest

from gamekit import LobbyError

helpers = importlib.import_module("games.bastion.tests.helpers")
foes = importlib.import_module("games.bastion.logic.foes")
match_module = importlib.import_module("games.bastion.logic.match")
build = helpers.build


def next_round(match):
    for pid in match.seats:
        match.end_turn(pid)


class ArrivalTests(helpers.FixtureCase):
    def test_enemies_arrive_after_the_peace_then_every_gap(self):
        match = helpers.new_match(self, enemies=("brute", "witch"), peaceRounds=2, enemyGap=2)
        self.assertEqual([f.arrives for f in match.foes], [3, 5])
        self.assertEqual(match.public()["foes"]["0"], {"state": "coming", "arrives": 3})  # face down
        next_round(match)
        self.assertEqual(match.foes[0].state, "coming")
        next_round(match)
        self.assertEqual((match.round, match.foes[0].state, match.foes[1].state), (3, "active", "coming"))
        self.assertEqual(match.public()["foes"]["0"]["name"], "Brute")

    def test_lineup_lower_tiers_first_boss_last(self):
        picked = foes.lineup(self.enemies, 3, random.Random(4))
        self.assertEqual(picked[-1]["tier"], 3)
        tiers = [e["tier"] for e in picked]
        self.assertEqual(tiers, sorted(tiers))

    def test_health_scales_with_difficulty_and_players(self):
        self.assertEqual(foes.scale(1, "normal"), 1.0)
        self.assertAlmostEqual(foes.scale(3, "hard"), foes.DIFFICULTY["hard"] * (1 + 2 * foes.PER_PLAYER))
        self.assertEqual(foes.Foe(0, self.enemies["brute"], 1, 2.0).max_hp, 4)


class AttackTests(helpers.FixtureCase):
    def test_attacks_come_in_turn_one_per_round(self):
        match = helpers.new_match(self)
        brute = helpers.foe(self, match, "brute")
        build(match, "hut", 5, 3)
        match.stock["gold"] = 10
        next_round(match)  # Smash: the only open tile
        self.assertNotIn((5, 3), match.board.at)  # a one-tile hut is destroyed
        next_round(match)  # Rob: keep income +1, then -2
        self.assertEqual(match.stock["gold"], 10 + 1 + 1 - 2)
        self.assertEqual(brute.public()["next"], 2)

    def test_walls_next_to_the_keep_shield_it(self):
        match = helpers.new_match(self)
        witch = helpers.foe(self, match, "witch")
        witch.step = 1  # Hit: 3 damage to the keep
        match.board.place("wall", 0, 4, 2, "p1")  # one tile next to the keep
        next_round(match)
        self.assertEqual(match.keep, match.keep_max - 2)

    def test_freeze_lasts_the_next_round(self):
        match = helpers.new_match(self)
        helpers.foe(self, match, "witch")
        mill = build(match, "mill", 1, 1)
        next_round(match)
        self.assertEqual(mill.frozen, match.round)
        self.assertTrue(match.public()["structures"][str(mill.uid)]["frozen"])
        match.foes[0].state = "defeated"
        next_round(match)
        self.assertFalse(match.public()["structures"][str(mill.uid)]["frozen"])

    def test_curses_go_to_each_discard_pile_marked_with_the_sender(self):
        match = helpers.new_match(self, players=2)
        sender = helpers.foe(self, match, "sender")
        next_round(match)
        for seat in match.seats.values():
            sent = [c for c in seat.all_cards() if c["card"] == "note"]
            self.assertEqual([c.get("from") for c in sent], [sender.index])


class DefeatTests(helpers.FixtureCase):
    def test_soldiers_per_damage(self):
        match = helpers.new_match(self)
        brute = helpers.foe(self, match, "brute")  # 2 soldiers per damage
        match.soldiers = 3
        match.strike("p1", brute.index, "soldiers")
        self.assertEqual((match.soldiers, brute.hp), (1, brute.max_hp - 1))
        with self.assertRaisesRegex(LobbyError, "takes 2 soldiers"):
            match.strike("p1", brute.index, "soldiers")
        with self.assertRaisesRegex(LobbyError, "can't be hurt that way"):
            match.strike("p1", brute.index, "resources")

    def test_times_never_overkill(self):
        match = helpers.new_match(self)
        brute = helpers.foe(self, match, "brute")
        match.soldiers = 20
        match.strike("p1", brute.index, "soldiers", times=10)
        self.assertEqual((brute.state, match.soldiers), ("defeated", 20 - 2 * brute.max_hp))

    def test_resources_per_damage(self):
        match = helpers.new_match(self)
        witch = helpers.foe(self, match, "witch")
        match.stock["wood"] = 3
        match.strike("p1", witch.index, "resources")
        self.assertEqual((match.stock["wood"], witch.hp), (1, witch.max_hp - 1))
        with self.assertRaisesRegex(LobbyError, "short of wood"):
            match.strike("p1", witch.index, "resources")

    def test_only_active_enemies(self):
        match = helpers.new_match(self, enemies=("brute",))
        match.soldiers = 5
        with self.assertRaisesRegex(LobbyError, "isn't here"):
            match.strike("p1", 0, "soldiers")

    def test_razing_the_lair_beats_it_and_clears_its_tiles(self):
        match = helpers.new_match(self)
        lich = helpers.foe(self, match, "lich")
        helpers.foe(self, match, "rat").enemy = dict(self.enemies["rat"], attacks=[{"name": "Rest", "text": ""}])
        lair = [c for c, b in match.board.blights.items() if b["lair"]]
        self.assertEqual(len(lair), lich.max_hp)
        build(match, "hut", 5, 3)
        next_round(match)  # Grave: a blight next to a building
        grave = next(c for c, b in match.board.blights.items() if not b["lair"])
        match.soldiers = 5
        match.raze("p1", *grave)  # 1 soldier, no damage
        self.assertEqual((match.soldiers, lich.hp), (4, lich.max_hp))
        next_round(match)
        next_round(match)  # Kill 2 soldiers, then another Grave
        self.assertEqual(match.soldiers, 2)
        match.raze("p1", *lair[0])
        self.assertEqual(lich.state, "defeated")
        self.assertFalse(match.board.blights)
        with self.assertRaisesRegex(LobbyError, "no enemy tile"):
            match.raze("p1", *grave)

    def test_raze_needs_soldiers(self):
        match = helpers.new_match(self)
        helpers.foe(self, match, "lich")
        lair = next(c for c, b in match.board.blights.items() if b["lair"])
        with self.assertRaisesRegex(LobbyError, "takes 1 soldier"):
            match.raze("p1", *lair)

    def test_a_beaten_enemys_plague_is_lifted(self):
        match = helpers.new_match(self)
        rat = helpers.foe(self, match, "rat")
        brute = helpers.foe(self, match, "brute")
        build(match, "mill", 1, 1).plague = rat.index
        build(match, "mill", 1, 3).plague = brute.index
        match.hurt(rat, rat.hp)
        self.assertEqual([s.plague for s in match.plagued()], [brute.index])


class EndTests(helpers.FixtureCase):
    def test_beating_every_enemy_wins(self):
        match = helpers.new_match(self, enemies=("brute", "witch"), peaceRounds=0, enemyGap=0)
        match.soldiers, match.stock["wood"] = 20, 20
        match.strike("p1", 0, "soldiers", times=5)
        self.assertIsNone(match.result)
        match.strike("p1", 1, "resources", times=5)
        self.assertEqual((match.result["victory"], match.result["winner"]), (True, None))
        with self.assertRaisesRegex(LobbyError, "over"):
            match.end_turn("p1")

    def test_keep_at_zero_loses(self):
        match = helpers.new_match(self)
        witch = helpers.foe(self, match, "witch")
        witch.step = 1
        match.keep = 2
        next_round(match)
        self.assertEqual((match.keep, match.result["victory"]), (0, False))
        self.assertIn("fallen", match.result["reason"])

    def test_enemies_left_long_after_the_last_arrival_lose(self):
        match = helpers.new_match(self, enemies=("brute",), peaceRounds=0)
        match.foes[0].enemy = dict(match.foes[0].enemy, attacks=[{"name": "Rest", "text": ""}])
        deadline = match.last_arrival() + match_module.OVERTIME
        while match.round < deadline:
            next_round(match)
            if match.round < deadline:
                self.assertIsNone(match.result)
        next_round(match)
        self.assertIn("too long", match.result["reason"])

    def test_the_last_one_done_ends_the_round_and_leavers_dont_block(self):
        match = helpers.new_match(self, players=2)
        match.end_turn("p2")
        self.assertEqual(match.round, 1)
        match.leave("p1")
        self.assertEqual(match.round, 2)
        self.assertFalse(match.seats["p2"].done)
        match.leave("p2")
        self.assertEqual((match.result["victory"], match.result["reason"]), (False, "Everyone left."))

    def test_taking_back_done(self):
        match = helpers.new_match(self, players=2)
        match.end_turn("p1")
        match.end_turn("p1", False)
        match.end_turn("p2")
        self.assertEqual(match.round, 1)


if __name__ == "__main__":
    unittest.main()
