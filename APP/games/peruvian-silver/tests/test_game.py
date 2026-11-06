"""Peruvian Silver: the rules, played through the real lobby with Sim.

Decks are rigged: `rig(sim, [...])` sets the draw order for the expedition (first id is
revealed at once, then the next ones) and random.shuffle does nothing, so every test is
deterministic. Timers don't run by themselves (auto_timers=False): `sim.run_timers()` plays
whatever comes after a reveal, so tests can look at the state in between.
"""

import importlib
import random
import unittest
from unittest import mock

from gamekit.sim import Sim

server = importlib.import_module("games.peruvian-silver.server")

STAY, LEAVE = {"action": "play", "card": "stay"}, {"action": "play", "card": "leave"}


class GameCase(unittest.TestCase):
    def setUp(self):
        random.seed(7)
        patch = mock.patch("random.shuffle", lambda items: None)
        patch.start()
        self.addCleanup(patch.stop)

    def new_game(self, draws, players=3, expeditions=2, seats=None, hands=None):
        with mock.patch.object(server, "STARTING_DECK", {"pinch": 1}):
            sim = Sim("peruvian-silver", players=players, settings={"expeditions": expeditions}, auto_timers=False)
        self.rig(sim, draws, seats, hands)
        return sim

    def rig(self, sim, draws, seats=None, hands=None):
        """Start expedition over with `draws` as the deck (first = revealed first)."""
        game = sim.game
        for index, fields in (seats or {}).items():
            game.seats[sim.pid(index)].update(fields)
        for index, cards in (hands or {}).items():
            game.hands[sim.pid(index)] += cards
            game.sort_hand(sim.pid(index))
        game.deck_list = [game.new_instance(card) for card in reversed(draws)]
        game.begin_expedition(game.expedition)
        sim._run(game.update())

    def play(self, sim, plays):
        """plays: {player index: hand card id or full message}"""
        for index, play in plays.items():
            message = play if isinstance(play, dict) else {"action": "play", "card": play}
            sim.ok(index, message)

    def seat(self, sim, index):
        return sim.game.seats[sim.pid(index)]

    def stage(self, sim):
        return sim.state(0)["game"]["stage"]

    def step(self, sim):
        """Run only the next queued timer (sim.run_timers() would also run what that one queues)."""
        self.assertTrue(sim.step(), "no timer was queued")


class SettingsTests(GameCase):
    def test_expeditions_clamped_and_validated(self):
        sim = Sim("peruvian-silver", players=2, start=False)
        spec = sim.state(0)["settingsSpec"]
        self.assertEqual([(f["key"], f["min"], f["max"]) for f in spec], [("expeditions", 1, 10)])
        self.assertEqual(sim.state(0)["settings"], {"expeditions": 5})
        for sent, expected in ((99, 10), (0, 1), (-4, 1), (7, 7)):
            self.assertIsNone(sim.lobby(0, {"type": "settings", "settings": {"expeditions": sent}}))
            self.assertEqual(sim.game.settings["expeditions"], expected)
        for bad in ("3", 2.5, True, None):
            self.assertIn("whole number", sim.lobby(0, {"type": "settings", "settings": {"expeditions": bad}}))
        self.assertEqual(sim.game.settings["expeditions"], 7)
        self.assertIn("host", sim.lobby(1, {"type": "settings", "settings": {"expeditions": 3}}))

    def test_game_number_is_top_level_and_counts_games(self):
        sim = self.new_game(["pinch"], players=2, expeditions=1)
        state = sim.state(0)
        self.assertEqual(state["gameNumber"], 1)
        self.assertNotIn("gameNumber", state["game"])
        self.assertEqual(state["game"]["expeditions"], 1)

    def test_start_needs_a_deck(self):
        with mock.patch.object(server, "STARTING_DECK", {}):
            sim = Sim("peruvian-silver", players=2, start=False)
            for i in range(2):
                sim.lobby(i, {"type": "ready", "ready": True})
            self.assertIn("starting deck", sim.state(0)["startBlocker"])


class SecretPlayTests(GameCase):
    def test_plays_stay_hidden_until_everyone_has_played(self):
        sim = self.new_game(["pile", "pile"])
        watcher = sim.spectator()
        p0, p1 = sim.pid(0), sim.pid(1)
        self.assertEqual(self.stage(sim), "choosing")

        sim.ok(0, LEAVE)
        self.assertEqual(sim.state(0)["private"]["played"], "leave")  # you see your own pick
        self.assertNotIn("leave", sim.state(0)["private"]["hand"])
        for viewer in (1, 2, watcher):
            game = sim.state(viewer)["game"]
            self.assertEqual(game["plays"][p0], {"chosen": True, "choice": None})
            self.assertEqual(game["plays"][p1], {"chosen": False, "choice": None})
        self.assertIsNone(sim.state(1)["private"]["played"])
        self.assertIsNone(sim.state(watcher)["private"])  # spectators have no hand
        self.assertEqual(self.stage(sim), "choosing")

        sim.ok(1, STAY)
        self.assertEqual(self.stage(sim), "choosing")  # p2 still has to play
        sim.ok(2, STAY)
        game = sim.state(watcher)["game"]
        self.assertEqual(game["stage"], "reveal")
        self.assertEqual(game["plays"][p0], {"chosen": True, "choice": "leave"})  # now everyone sees it
        self.assertEqual(game["plays"][p1]["choice"], "stay")

    def test_hands_are_private(self):
        sim = self.new_game(["pile"], hands={1: ["flee"]})
        self.assertEqual(sim.state(1)["private"]["hand"], ["stay", "leave", "flee"])
        self.assertEqual(sim.state(0)["private"]["hand"], ["stay", "leave"])
        game = sim.state(0)["game"]
        self.assertEqual(game["seats"][sim.pid(1)]["handSize"], 3)  # only the size is public
        self.assertNotIn("hands", game)

    def test_rejected_plays(self):
        sim = self.new_game(["pile"])
        sim.fails(0, {"action": "play", "card": "flee"}, "isn't in your hand")
        sim.fails(0, {"action": "play", "card": 5}, "isn't in your hand")
        sim.fails(0, {"action": "play"}, "isn't in your hand")
        sim.fails(0, {"action": "play", "card": "stash"}, "isn't in your hand")
        sim.ok(0, STAY)
        sim.fails(0, LEAVE, "already played")
        watcher = sim.spectator()
        sim.fails(watcher, STAY, "not playing")

    def test_unknown_action_and_wrong_stage(self):
        sim = self.new_game(["pile"])
        sim.fails(0, {"action": "dance"}, "Unknown action")
        sim.fails(0, {}, "Unknown action")
        sim.fails(0, {"action": "bid", "amount": 1}, "not your turn to bid")
        sim.fails(0, {"action": "charm", "use": True}, "can't use a charm")
        sim.fails(0, {"action": "fountain", "amount": 0}, "can't use the fountain")
        sim.fails(0, {"action": "mark", "uid": 1, "emoji": "x"}, "can't mark")
        sim.fails(0, {"action": "rob", "kind": "idol", "card": "little-idol"}, "not being robbed")
        sim.fails(0, {"action": "gem", "emoji": "x"}, "don't have a gem")
        sim.fails(0, {"action": "peek"}, "Crystal Ball")

    def test_game_messages_in_the_lobby_are_rejected(self):
        sim = Sim("peruvian-silver", players=2, start=False)
        sim.fails(0, STAY, "not playing")


class TreasureTests(GameCase):
    def test_treasure_is_split_and_leavers_bank_with_leftovers(self):
        # handful (3) between 3 players: 1 each. pile (5) between the 2 left: 2 each, 1 stays on it.
        sim = self.new_game(["handful", "pile", "pinch"])
        self.assertEqual([self.seat(sim, i)["backpack"] for i in range(3)], [1, 1, 1])
        self.play(sim, {0: "leave", 1: "stay", 2: "stay"})
        sim.run_timers()
        self.assertEqual((self.seat(sim, 0)["status"], self.seat(sim, 0)["chest"]), ("camp", 1))
        self.assertEqual([self.seat(sim, i)["backpack"] for i in (1, 2)], [3, 3])
        self.assertEqual(sim.state(0)["game"]["paths"][0]["cards"][1]["left"], 1)
        self.assertEqual(self.stage(sim), "choosing")

        # p1 leaves alone: banks the backpack plus the whole leftover.
        self.play(sim, {1: "leave", 2: "stay"})
        sim.run_timers()
        self.assertEqual(self.seat(sim, 1)["chest"], 4)
        self.assertEqual(self.seat(sim, 1)["backpack"], 0)

    def test_two_leavers_split_the_leftovers(self):
        sim = self.new_game(["pile", "pinch"], players=3)  # 5 / 3 = 1 each, 2 left on the card
        self.play(sim, {0: "leave", 1: "leave", 2: "stay"})
        sim.run_timers()
        self.assertEqual([self.seat(sim, i)["chest"] for i in range(3)], [2, 2, 0])  # 1 + (2 // 2)
        self.assertEqual(sim.state(2)["game"]["paths"][0]["cards"][0]["left"], 0)

    def test_gremlin_takes_a_share_and_keeps_it(self):
        sim = self.new_game(["gremlin", "pile"], players=2)
        self.play(sim, {0: "stay", 1: "stay"})
        sim.run_timers()  # pile: 5 / (2 players + 1 gremlin) = 1 each, 2 left
        self.assertEqual([self.seat(sim, i)["backpack"] for i in range(2)], [1, 1])
        cards = sim.state(0)["game"]["paths"][0]["cards"]
        self.assertEqual((cards[0]["left"], cards[1]["left"]), (1, 2))  # the gremlin's share, and the remainder

    def test_blessing_doubles_backpacks(self):
        sim = self.new_game(["pile", "blessing"], players=2)
        self.assertEqual(self.seat(sim, 0)["backpack"], 2)
        self.play(sim, {0: "stay", 1: "stay"})
        sim.run_timers()
        self.assertEqual(self.seat(sim, 0)["backpack"], 4)

    def test_pot_grows_every_turn(self):
        sim = self.new_game(["pot-of-greed", "pinch", "pinch"], players=2)
        self.play(sim, {0: "stay", 1: "stay"})
        sim.run_timers()
        self.play(sim, {0: "stay", 1: "stay"})
        sim.run_timers()
        pot = sim.state(0)["game"]["paths"][0]["cards"][0]
        self.assertEqual(pot["left"], 10)

    def test_altar_collects_backpacks_for_leavers(self):
        sim = self.new_game(["pile", "altar"], players=2)  # 2 each; the altar takes 4
        self.play(sim, {0: "stay", 1: "stay"})
        sim.run_timers()
        self.assertEqual([self.seat(sim, i)["backpack"] for i in range(2)], [0, 0])
        self.play(sim, {0: "leave", 1: "stay"})
        sim.run_timers()
        self.assertEqual(self.seat(sim, 0)["chest"], 5)  # alone: the pile's leftover 1 + the altar's 4

    def test_death_ends_the_expedition_for_everyone(self):
        sim = self.new_game(["pile", "death"], players=2)
        self.play(sim, {0: "stay", 1: "stay"})
        self.step(sim)
        game = sim.state(0)["game"]
        self.assertEqual(game["stage"], "over")
        self.assertEqual(game["ending"]["reason"], "death")
        self.assertEqual([self.seat(sim, i)["status"] for i in range(2)], ["busted", "busted"])
        self.assertEqual(self.seat(sim, 0)["chest"], 0)


class HazardTests(GameCase):
    def test_second_copy_strikes_and_only_explorers_lose_their_backpack(self):
        sim = self.new_game(["pinch", "cave-in", "cave-in"], players=3)
        self.assertEqual(self.seat(sim, 0)["backpack"], 0)  # 2 / 3 = 0 each; 2 stay on the card
        for i in range(3):
            self.seat(sim, i)["backpack"] = 4
        self.play(sim, {0: "stay", 1: "stay", 2: "stay"})
        sim.run_timers()  # the first Cave-in is harmless
        self.assertEqual(self.stage(sim), "choosing")
        self.assertIsNone(sim.state(0)["game"]["strike"])
        self.play(sim, {0: "leave", 1: "stay", 2: "stay"})
        self.step(sim)  # the second one strikes p1 and p2
        game = sim.state(0)["game"]
        self.assertEqual(game["stage"], "over")
        self.assertEqual(game["ending"]["reason"], "bust")
        self.assertEqual(game["ending"]["lost"], {sim.pid(1): 4, sim.pid(2): 4})
        self.assertEqual(self.seat(sim, 0)["chest"], 6)  # p0 left in time: 4 + the 2 left on the Pinch
        self.assertEqual([self.seat(sim, i)["status"] for i in range(3)], ["camp", "busted", "busted"])
        self.assertEqual(self.seat(sim, 1)["backpack"], 0)
        # One Cave-in is gone from the deck for the next expedition.
        self.assertEqual([i["card"] for i in sim.game.deck_list].count("cave-in"), 1)

    def test_a_mirror_copies_the_next_card_so_a_hazard_pair_is_instant(self):
        sim = self.new_game(["mirror", "cave-in"], players=2)
        self.seat(sim, 0)["backpack"] = 3
        self.play(sim, {0: "stay", 1: "stay"})
        self.step(sim)
        game = sim.state(0)["game"]
        self.assertEqual(game["ending"]["reason"], "bust")
        self.assertEqual(game["ending"]["card"], "cave-in")
        self.assertEqual(self.seat(sim, 0)["chest"], 0)

    def test_hazards_of_different_kinds_do_not_strike(self):
        sim = self.new_game(["cave-in", "bats", "flood"], players=2)
        self.play(sim, {0: "stay", 1: "stay"})
        sim.run_timers()
        self.play(sim, {0: "stay", 1: "stay"})
        sim.run_timers()
        self.assertEqual(self.stage(sim), "choosing")

    def test_deck_running_out_sends_everyone_home_safely(self):
        sim = self.new_game(["pile"], players=2, expeditions=2)
        self.play(sim, {0: "stay", 1: "stay"})
        self.step(sim)
        game = sim.state(0)["game"]
        self.assertEqual(game["ending"]["reason"], "empty")
        self.assertEqual([self.seat(sim, i)["chest"] for i in range(2)], [2, 2])  # 5 // 2 = 2 each; the 1 left can't be split


class CharmTests(GameCase):
    def strike_with_charm(self):
        sim = self.new_game(["cave-in", "cave-in"], players=3, seats={0: {"charms": ["charm-cave-in"]}})
        for i, silver in enumerate((2, 3, 3)):  # (backpacks are reset when an expedition begins)
            self.seat(sim, i)["backpack"] = silver
        self.play(sim, {0: "stay", 1: "stay", 2: "stay"})
        sim.run_timers()
        return sim

    def test_only_charm_holders_decide_and_stay_in(self):
        sim = self.strike_with_charm()
        self.assertEqual(self.stage(sim), "charm")
        self.assertEqual(sim.state(0)["game"]["strike"]["holders"], [sim.pid(0)])
        sim.fails(1, {"action": "charm", "use": True}, "can't use a charm")
        sim.fails(0, {"action": "charm", "use": "yes"}, "Use your charm or pass")
        sim.ok(0, {"action": "charm", "use": True})
        sim.fails(0, {"action": "charm", "use": False}, "can't use a charm")  # the stage moved on: already decided
        game = sim.state(0)["game"]
        self.assertEqual(game["stage"], "saved")
        self.assertEqual(game["strike"]["users"], [sim.pid(0)])
        self.assertEqual(self.seat(sim, 0)["charms"], [])  # spent
        self.assertEqual(self.seat(sim, 0)["backpack"], 2)  # kept
        self.assertEqual([self.seat(sim, i)["status"] for i in range(3)], ["exploring", "busted", "busted"])
        sim.run_timers()
        self.assertEqual(self.stage(sim), "choosing")  # p0 goes on alone
        self.assertEqual(sim.state(0)["game"]["explorerPlays"], sorted(server.EXPLORER_PLAYS))

    def test_the_decision_is_secret_and_declining_ends_the_expedition(self):
        sim = self.strike_with_charm()
        self.assertIsNone(sim.state(0)["private"]["charmChoice"])
        sim.ok(0, {"action": "charm", "use": False})
        game = sim.state(1)["game"]
        self.assertEqual(game["stage"], "over")
        self.assertEqual(game["ending"]["reason"], "bust")
        self.assertEqual(self.seat(sim, 0)["charms"], ["charm-cave-in"])  # kept for later
        self.assertEqual(self.seat(sim, 0)["backpack"], 0)

    def test_guide_dog_goes_home_with_the_backpack_and_skips_the_charm_question(self):
        sim = self.new_game(["cave-in", "cave-in"], players=2, hands={0: ["guide-dog"]})
        for i in range(2):
            self.seat(sim, i)["backpack"] = 5
        self.play(sim, {0: "guide-dog", 1: "stay"})
        self.step(sim)  # the second Cave-in strikes
        self.assertEqual((self.seat(sim, 0)["status"], self.seat(sim, 0)["chest"]), ("camp", 5))
        self.assertEqual(self.seat(sim, 1)["status"], "busted")


class HandCardTests(GameCase):
    def test_a_lone_leaver_takes_the_relics(self):
        sim = self.new_game(["flee-charm", "pinch"], players=3)
        self.play(sim, {0: "leave", 1: "stay", 2: "stay"})
        sim.run_timers()
        seat = self.seat(sim, 0)
        self.assertEqual(seat["relics"], ["flee-charm"])
        self.assertIn("flee", sim.game.hands[sim.pid(0)])
        self.assertTrue(sim.state(2)["game"]["paths"][0]["cards"][0]["taken"], sim.pid(0))
        self.assertNotIn("flee-charm", [i["card"] for i in sim.game.deck_list])  # a taken relic leaves the deck

    def test_two_leavers_leave_the_relics_behind(self):
        sim = self.new_game(["flee-charm", "pinch"], players=3)
        self.play(sim, {0: "leave", 1: "leave", 2: "stay"})
        sim.run_timers()
        self.assertEqual(self.seat(sim, 0)["relics"], [])
        self.assertIn("flee-charm", [i["card"] for i in sim.game.deck_list])

    def test_a_fleer_goes_first_and_takes_the_relics(self):
        sim = self.new_game(["flee-charm", "pinch"], players=3, hands={0: ["flee"]})
        self.play(sim, {0: "flee", 1: "leave", 2: "stay"})
        self.assertEqual(self.seat(sim, 0)["status"], "camp")
        self.assertEqual(self.seat(sim, 1)["status"], "camp")
        self.assertEqual(sim.game.hands[sim.pid(0)].count("flee"), 1)  # the played one is used up; the relic gave a new one
        self.assertEqual(sim.game.hands[sim.pid(1)].count("flee"), 0)
        entry = sim.state(2)["game"]["paths"][0]["cards"][0]
        self.assertEqual(entry["taken"], sim.pid(0))

    def test_stash_banks_and_keeps_exploring(self):
        sim = self.new_game(["pile", "pinch"], players=2, hands={0: ["stash"]})
        self.play(sim, {0: "stash", 1: "stay"})
        self.assertEqual(self.seat(sim, 0)["chest"], 2)
        self.assertEqual(self.seat(sim, 0)["status"], "exploring")
        self.assertNotIn("stash", sim.game.hands[sim.pid(0)])

    def test_backstab_robs_the_leavers(self):
        sim = self.new_game(["pile", "pinch"], players=2, hands={0: ["backstab"]})
        self.play(sim, {0: "backstab", 1: "leave"})  # 2 each, 1 left: share 0; p1's 2 go to p0
        self.assertEqual((self.seat(sim, 0)["chest"], self.seat(sim, 1)["chest"]), (4, 0))
        self.assertEqual(self.seat(sim, 1)["status"], "camp")

    def test_reusable_cards_come_back_and_the_others_do_not(self):
        sim = self.new_game(["pile"], players=2)
        self.play(sim, {0: "stay", 1: "leave"})
        self.assertEqual(sim.game.hands[sim.pid(1)], ["stay", "leave"])

    def test_seconds_lets_a_player_at_camp_return(self):
        sim = self.new_game(["pile", "pinch", "pinch"], players=3, hands={0: ["seconds"]})
        self.play(sim, {0: "leave", 1: "stay", 2: "stay"})
        sim.run_timers()
        self.assertEqual(self.seat(sim, 0)["status"], "camp")
        # At camp, only Seconds can be played, and nobody waits for it.
        sim.fails(0, STAY, "at camp")
        sim.ok(0, {"action": "play", "card": "seconds"})
        self.assertEqual(self.stage(sim), "choosing")  # p1 and p2 are still choosing
        self.play(sim, {1: "stay", 2: "stay"})
        sim.run_timers()
        self.assertEqual(self.seat(sim, 0)["status"], "exploring")
        self.assertEqual(self.seat(sim, 0)["backpack"], 0)  # back in with an empty backpack

    def test_crystal_ball_shows_only_you_the_next_cards(self):
        sim = self.new_game(["pinch", "bats", "flood", "pile", "heap"], players=2, hands={0: ["crystal-ball"]})
        sim.fails(0, {"action": "play", "card": "crystal-ball"}, "doesn't use your turn")
        sim.ok(0, {"action": "peek"})
        self.assertEqual(sim.state(0)["private"]["vision"], ["bats", "flood", "pile"])
        self.assertEqual(sim.state(1)["private"]["vision"], [])
        self.assertNotIn("crystal-ball", sim.state(0)["private"]["hand"])
        sim.fails(0, {"action": "peek"}, "Crystal Ball")


class ForkTests(GameCase):
    def test_fork_splits_the_path_and_players_pick_a_side(self):
        sim = self.new_game(["fork", "handful", "pile", "pinch", "pinch"], players=2)
        self.play(sim, {0: "stay", 1: "stay"})
        sim.run_timers()  # the path splits
        game = sim.state(0)["game"]
        self.assertEqual(game["stage"], "fork")
        left, right = game["forkOptions"]["0"]
        self.assertEqual([game["paths"][p]["side"] for p in (left, right)], ["left", "right"])
        self.assertTrue(game["paths"][0]["closed"])

        sim.fails(0, {"action": "play", "card": "flee"}, "isn't in your hand")
        sim.ok(0, STAY)  # Stay = left
        sim.fails(0, LEAVE, "already picked")
        self.assertEqual(sim.state(1)["game"]["plays"][sim.pid(0)], {"chosen": True, "choice": None})
        self.assertEqual(sim.state(0)["private"]["forkChoice"], "left")
        sim.ok(1, LEAVE)  # Leave = right
        self.assertEqual(self.stage(sim), "forked")
        self.assertEqual((self.seat(sim, 0)["path"], self.seat(sim, 1)["path"]), (left, right))
        sim.run_timers()  # the first card of each new path resolves for whoever took it
        self.assertEqual((self.seat(sim, 0)["backpack"], self.seat(sim, 1)["backpack"]), (3, 5))
        self.assertEqual(self.stage(sim), "choosing")
        self.assertEqual(sim.state(0)["game"]["order"], [sim.pid(0), sim.pid(1)])

    def test_the_fork_discards_cards_but_keeps_the_fork_and_hazards(self):
        sim = self.new_game(["cave-in", "fork", "pinch", "handful", "pile", "pinch"], players=2)
        self.play(sim, {0: "stay", 1: "stay"})
        sim.run_timers()  # the Fork
        self.play(sim, {0: "stay", 1: "stay"})
        sim.run_timers()  # the split
        self.assertEqual([e["card"] for e in sim.state(0)["game"]["paths"][0]["cards"]], ["cave-in", "fork"])


class AuctionTests(GameCase):
    def test_gem_auction_in_turn_highest_bid_wins_and_pays(self):
        sim = self.new_game(["red-gem", "pinch"], players=3, seats={0: {"chest": 10}, 1: {"chest": 6}})
        game = sim.state(0)["game"]
        self.assertEqual(game["stage"], "auction")
        self.assertEqual(game["auction"]["order"], [sim.pid(i) for i in range(3)])
        sim.fails(1, {"action": "bid", "amount": 1}, "not your turn")
        sim.fails(0, {"action": "bid", "amount": 11}, "at most 10")
        sim.fails(0, {"action": "bid", "amount": -1}, "at most 10")
        sim.fails(0, {"action": "bid", "amount": "3"}, "at most 10")
        sim.ok(0, {"action": "bid", "amount": 4})
        sim.fails(1, {"action": "bid", "amount": 4}, "more than 4")
        sim.ok(1, {"action": "bid", "amount": 5})  # p2 has nothing to bid: passes by itself
        self.assertEqual(self.stage(sim), "choosing")
        self.assertEqual((self.seat(sim, 1)["chest"], self.seat(sim, 0)["chest"]), (1, 10))  # only the winner pays
        self.assertEqual(self.seat(sim, 1)["gems"], ["red-gem"])
        self.assertNotIn("red-gem", [i["card"] for i in sim.game.deck_list])
        self.assertEqual(sim.state(0)["game"]["log"][-1]["winner"], sim.pid(1))

    def test_nobody_bids_the_gem_stays_in_the_deck(self):
        sim = self.new_game(["red-gem"], players=2)  # empty chests: everyone passes at once
        self.assertEqual(self.stage(sim), "choosing")
        self.assertIn("red-gem", [i["card"] for i in sim.game.deck_list])
        self.assertEqual(self.seat(sim, 0)["gems"], [])

    def test_the_first_bidder_rotates(self):
        sim = self.new_game(["red-gem", "blue-gem"], players=2, seats={0: {"chest": 9}, 1: {"chest": 9}})
        self.assertEqual(sim.state(0)["game"]["auction"]["order"][0], sim.pid(0))
        sim.ok(0, {"action": "bid", "amount": 0})
        sim.ok(1, {"action": "bid", "amount": 0})
        self.play(sim, {0: "stay", 1: "stay"})
        sim.run_timers()  # the Blue Gem
        self.assertEqual(sim.state(0)["game"]["auction"]["order"][0], sim.pid(1))

    def test_the_current_bidder_leaving_passes_the_turn(self):
        sim = self.new_game(["red-gem", "pinch"], players=3, seats={i: {"chest": 9} for i in range(3)})
        sim.leave(0)
        self.assertEqual(sim.game.bidder(), sim.pid(1))
        sim.ok(1, {"action": "bid", "amount": 3})
        sim.ok(2, {"action": "bid", "amount": 4})
        self.assertEqual(self.seat(sim, 2)["gems"], ["red-gem"])
        self.assertEqual(sim.game.stage, "choosing")


class BetweenExpeditionsTests(GameCase):
    def end_round(self, sim):
        """Everyone leaves: the expedition ends (the 'over' stage waits for its timer)."""
        explorers = [i for i in range(len(sim.clients)) if self.seat(sim, i)["status"] == "exploring"]
        self.play(sim, {i: "leave" for i in explorers})
        self.step(sim)  # after the reveal the expedition is over; the next step is queued
        self.assertEqual(self.stage(sim), "over")

    def test_red_gem_adds_three_of_five_pool_cards_secretly(self):
        sim = self.new_game(["pinch"], players=2, expeditions=2, seats={0: {"gems": ["red-gem"]}})
        before = len(sim.game.deck_list)
        self.end_round(sim)
        sim.run_timers()  # begin_gems
        game = sim.state(0)["game"]
        self.assertEqual(game["stage"], "gem")
        self.assertEqual(game["gemTurn"], {"player": sim.pid(0), "gem": "red-gem", "color": "red"})
        options = sim.state(0)["private"]["gemOptions"]
        self.assertEqual(len(set(options)), 5)
        self.assertEqual(sim.state(1)["private"]["gemOptions"], [])
        sim.fails(1, {"action": "gem", "cards": options[:3]}, "don't have a gem")
        sim.fails(0, {"action": "gem", "cards": options[:2]}, "Pick 3 different")
        sim.fails(0, {"action": "gem", "cards": [options[0]] * 3}, "Pick 3 different")
        sim.fails(0, {"action": "gem", "cards": ["pinch", "pinch", "pinch"]}, "Pick 3 different")
        sim.ok(0, {"action": "gem", "cards": options[:3]})
        self.assertEqual(len(sim.game.deck_list), before + 3)
        self.assertEqual(self.stage(sim), "marking")  # on to marking
        self.assertEqual(sim.state(1)["game"]["log"][-1]["type"], "red-gem")
        self.assertNotIn(options[0], str(sim.state(1)["game"]["log"][-1]))  # which cards were added is secret

    def test_blue_gem_marks_three_cards_and_only_you_know_which(self):
        sim = self.new_game(["pinch"], players=2, expeditions=2, seats={0: {"gems": ["blue-gem"]}})
        sim.game.deck_list += [sim.game.new_instance("pile") for _ in range(4)]
        self.end_round(sim)
        sim.run_timers()
        self.assertEqual(self.stage(sim), "gem")
        sim.fails(0, {"action": "gem", "emoji": "nope"}, "Pick one of the marks")
        sim.ok(0, {"action": "gem", "emoji": "⭐"})
        self.assertEqual(len(sim.state(0)["private"]["myMarks"]), 3)
        self.assertEqual(sim.state(1)["private"]["myMarks"], [])
        self.assertEqual(sum(i["marks"].count("⭐") for i in sim.game.deck_list), 3)

    def test_marking_is_secret_and_starts_the_next_expedition(self):
        sim = self.new_game(["pinch"], players=2, expeditions=2)
        sim.game.deck_list += [sim.game.new_instance("pile") for _ in range(5)]
        self.end_round(sim)
        sim.run_timers()  # begin_gems (none) -> marking
        game = sim.state(0)["game"]
        self.assertEqual(game["stage"], "marking")
        emojis = game["markEmojis"]
        self.assertEqual(len(emojis), 3)
        self.assertEqual(len(set(emojis)), 3)
        offers = [sim.state(i)["private"]["offers"] for i in range(2)]
        self.assertTrue(all(len(o) == 3 for o in offers))
        self.assertNotIn("marks", offers[0][0])  # faces only
        sim.fails(0, {"action": "mark", "uid": 99999, "emoji": emojis[0]}, "wasn't shown")
        sim.fails(0, {"action": "mark", "uid": offers[0][0]["uid"], "emoji": "nope"}, "one of the three marks")
        sim.ok(0, {"action": "mark", "uid": offers[0][0]["uid"], "emoji": emojis[0]})
        sim.fails(0, {"action": "mark", "uid": offers[0][1]["uid"], "emoji": emojis[1]}, "already marked")
        self.assertEqual(sim.state(1)["game"]["plays"][sim.pid(0)], {"chosen": True, "choice": None})
        self.assertEqual(sim.state(0)["private"]["picked"], {"uid": offers[0][0]["uid"], "emoji": emojis[0]})
        self.assertIsNone(sim.state(1)["private"]["picked"])
        sim.ok(1, {"action": "mark", "uid": offers[1][0]["uid"], "emoji": emojis[1]})
        game = sim.state(0)["game"]  # expedition 2 has begun
        self.assertEqual((game["stage"], game["expedition"]), ("choosing", 2))
        self.assertEqual(len(sim.state(0)["private"]["myMarks"]), 1)
        self.assertEqual(len(sim.state(1)["private"]["myMarks"]), 1)
        self.assertEqual(sum(len(i["marks"]) for i in sim.game.deck_list), 2)

    def test_a_player_leaving_while_marking_does_not_hold_the_others_up(self):
        sim = self.new_game(["pinch"], players=3, expeditions=2)
        sim.game.deck_list += [sim.game.new_instance("pile") for _ in range(5)]
        self.end_round(sim)
        sim.run_timers()
        self.assertEqual(self.stage(sim), "marking")
        for i in (0, 1):
            offer = sim.state(i)["private"]["offers"][0]["uid"]
            sim.ok(i, {"action": "mark", "uid": offer, "emoji": sim.state(i)["game"]["markEmojis"][0]})
        self.assertEqual(self.stage(sim), "marking")
        sim.leave(2)
        self.assertEqual(sim.game.expedition, 2)


class RobberyTests(GameCase):
    def test_the_richest_player_chooses_a_relic_to_lose(self):
        sim = self.new_game(
            ["robbery", "pinch"], players=3,
            seats={0: {"chest": 9, "idols": ["little-idol"], "charms": ["charm-bats"]}, 1: {"chest": 3, "idols": ["great-idol"]}},
        )
        game = sim.state(0)["game"]
        self.assertEqual(game["stage"], "robbery")
        self.assertEqual(game["robbery"]["choosers"], [sim.pid(0)])
        sim.fails(1, {"action": "rob", "kind": "idol", "card": "great-idol"}, "not being robbed")
        sim.fails(0, {"action": "rob", "kind": "idol", "card": "great-idol"}, "don't have that card")
        sim.fails(0, {"action": "rob", "kind": "charm", "card": "little-idol"}, "don't have that card")
        sim.ok(0, {"action": "rob", "kind": "idol", "card": "little-idol"})
        self.assertEqual(self.seat(sim, 0)["idols"], [])
        self.assertEqual(self.seat(sim, 0)["charms"], ["charm-bats"])
        self.assertEqual(self.seat(sim, 1)["idols"], ["great-idol"])
        self.assertEqual(self.stage(sim), "choosing")

    def test_a_relic_card_lost_takes_its_hand_card_with_it(self):
        sim = self.new_game(["robbery", "pinch"], players=2, seats={0: {"chest": 9, "relics": ["flee-charm"]}}, hands={0: ["flee"]})
        sim.ok(0, {"action": "rob", "kind": "relic", "card": "flee-charm"})
        self.assertNotIn("flee", sim.game.hands[sim.pid(0)])

    def test_nothing_to_lose_nothing_happens(self):
        sim = self.new_game(["robbery"], players=2, seats={0: {"chest": 9}})
        self.assertEqual(self.stage(sim), "choosing")


class FountainTests(GameCase):
    def test_fountain_doubles_pools_and_moves_silver_in_secret(self):
        sim = self.new_game(["pinch", "fountain"], players=2, seats={0: {"fountain": 4}})
        self.assertEqual(self.seat(sim, 0)["backpack"], 1)
        self.play(sim, {0: "stay", 1: "stay"})
        sim.run_timers()
        self.assertEqual(self.stage(sim), "fountain")
        self.assertEqual(self.seat(sim, 0)["fountain"], 8)  # doubled
        sim.fails(1, {"action": "fountain", "amount": 5}, "up to 1")
        sim.fails(0, {"action": "fountain", "amount": -9}, "take out up to 8")
        sim.fails(0, {"action": "fountain", "amount": "1"}, "put in up to")
        sim.ok(0, {"action": "fountain", "amount": -3})
        self.assertEqual(sim.state(0)["private"]["fountainChoice"], -3)
        self.assertIsNone(sim.state(1)["private"]["fountainChoice"])
        self.assertEqual(self.seat(sim, 0)["fountain"], 8)  # nothing moves until everyone has chosen
        sim.fails(0, {"action": "fountain", "amount": 0}, "already decided")
        sim.ok(1, {"action": "fountain", "amount": 1})
        self.assertEqual((self.seat(sim, 0)["backpack"], self.seat(sim, 0)["fountain"]), (4, 5))
        self.assertEqual((self.seat(sim, 1)["backpack"], self.seat(sim, 1)["fountain"]), (0, 1))
        self.assertEqual(self.stage(sim), "choosing")


class LeavingTests(GameCase):
    def test_leaving_when_everyone_else_has_played_reveals_the_cards(self):
        sim = self.new_game(["pile", "pinch"], players=3)
        self.play(sim, {0: "stay", 1: "leave"})
        sim.leave(2)
        game = sim.state(0)["game"]
        self.assertEqual(game["stage"], "reveal")
        self.assertEqual(game["seats"][sim.pid(2)]["status"], "gone")
        self.assertEqual(game["log"][-2]["type"], "gone")
        self.assertEqual(self.seat(sim, 1)["status"], "camp")
        self.assertNotIn(sim.pid(2), sim.game.hands)
        sim.run_timers()
        self.assertEqual(self.stage(sim), "choosing")
        self.assertEqual(sim.game.explorers(), [sim.pid(0)])

    def test_leaving_before_playing_waits_for_the_rest(self):
        sim = self.new_game(["pile"], players=3)
        sim.ok(0, STAY)
        sim.leave(1)
        self.assertEqual(self.stage(sim), "choosing")
        self.assertEqual(self.seat(sim, 1)["backpack"], 0)  # their silver is lost
        sim.ok(2, STAY)
        self.assertEqual(self.stage(sim), "reveal")

    def test_the_last_explorers_leaving_still_reveals_and_ends_the_expedition(self):
        sim = self.new_game(["pile", "pinch"], players=3)
        self.play(sim, {0: "leave"})
        sim.leave(1)
        sim.leave(2)
        self.assertEqual(self.stage(sim), "reveal")  # p0's Leave is revealed once nobody is left to wait for
        self.step(sim)
        self.assertEqual(self.stage(sim), "over")
        self.assertEqual(sim.state(0)["game"]["ending"]["reason"], "camp")
        self.assertEqual(self.seat(sim, 0)["chest"], 3)  # 1 + the 2 left on the Pile

    def test_a_charm_holder_leaving_does_not_hold_up_the_strike(self):
        sim = self.new_game(["cave-in", "cave-in"], players=3, seats={0: {"charms": ["charm-cave-in"]}})
        self.play(sim, {0: "stay", 1: "stay", 2: "stay"})
        sim.run_timers()
        self.assertEqual(self.stage(sim), "charm")
        sim.leave(0)
        self.assertEqual(self.stage(sim), "over")  # nobody left to use a charm: it strikes

    def test_everyone_leaving_returns_to_the_lobby(self):
        sim = self.new_game(["pile"], players=2)
        sim.leave(0)
        sim.leave(1)
        self.assertEqual(sim.game.phase, "lobby")


class ScoringTests(GameCase):
    def test_final_score_is_chest_idols_and_five_per_unused_relic(self):
        sim = self.new_game(
            ["pinch"], players=2, expeditions=1,
            seats={0: {"idols": ["great-idol"], "charms": ["charm-cave-in"], "relics": ["flee-charm"]}, 1: {"fountain": 50}},
        )
        self.play(sim, {0: "leave", 1: "leave"})  # 1 silver each
        sim.run_timers()
        self.assertEqual(sim.game.phase, "finished")
        result = sim.state(1)["result"]
        self.assertEqual(result["chests"], {sim.pid(0): 1, sim.pid(1): 1})
        self.assertEqual(result["idols"], {sim.pid(0): 10, sim.pid(1): 0})
        self.assertEqual(result["bonus"], {sim.pid(0): 10, sim.pid(1): 0})  # the fountain pool doesn't count
        self.assertEqual(result["scores"], {sim.pid(0): 21, sim.pid(1): 1})
        self.assertEqual(result["winners"], [sim.pid(0)])
        sim.fails(0, STAY, "not playing")

    def test_a_tie_has_several_winners_and_the_host_can_go_back_to_the_lobby(self):
        sim = self.new_game(["pile"], players=2, expeditions=1)
        self.play(sim, {0: "leave", 1: "leave"})
        sim.run_timers()
        self.assertEqual(sim.state(0)["result"]["winners"], [sim.pid(0), sim.pid(1)])
        self.assertIsNone(sim.lobby(0, {"type": "back_to_lobby"}))
        self.assertEqual(sim.game.phase, "lobby")
        self.assertEqual(sim.game.seats, {})


class FullGameTests(unittest.TestCase):
    def test_a_game_with_the_real_deck_plays_to_the_end(self):
        for seed in (1, 2, 3):
            random.seed(seed)
            sim = Sim("peruvian-silver", players=3, settings={"expeditions": 3}, auto_timers=False)
            for _ in range(5000):
                if sim.game.phase == "finished":
                    break
                self.drive(sim)
            self.assertEqual(sim.game.phase, "finished", f"seed {seed}")
            result = sim.state(0)["result"]
            self.assertEqual(set(result["scores"]), {sim.pid(i) for i in range(3)})
            self.assertTrue(result["winners"])
            self.assertEqual(sim.game.expedition, 3)

    def drive(self, sim):
        """Make the simplest legal move for whoever has to act, or run the timers."""
        game = sim.game
        stage = game.stage
        pending = [i for i in range(len(sim.clients)) if sim.pid(i) in game.choices.pending and not game.choices.chosen(sim.pid(i))]
        if stage == "auction":
            sim.ok(sim.index_of(game.bidder()), {"action": "bid", "amount": 0})
        elif stage in ("choosing", "fork") and pending:
            seat = game.seats[sim.pid(pending[0])]
            sim.ok(pending[0], {"action": "play", "card": "leave" if seat["backpack"] >= 6 else "stay"})
        elif stage == "charm" and pending:
            sim.ok(pending[0], {"action": "charm", "use": True})
        elif stage == "fountain" and pending:
            sim.ok(pending[0], {"action": "fountain", "amount": 0})
        elif stage == "robbery" and pending:
            kind, card = game.losable(sim.pid(pending[0]))[0]
            sim.ok(pending[0], {"action": "rob", "kind": kind, "card": card})
        elif stage == "gem" and pending:
            turn = game.gem_turn
            message = {"action": "gem", "cards": game.gem_options[:3]} if turn["color"] == "red" else {"action": "gem", "emoji": server.MARKS[0]}
            sim.ok(sim.index_of(turn["player"]), message)
        elif stage == "marking" and pending:
            offer = sim.state(pending[0])["private"]["offers"][0]["uid"]
            sim.ok(pending[0], {"action": "mark", "uid": offer, "emoji": sim.state(pending[0])["game"]["markEmojis"][0]})
        else:
            sim.run_timers()


if __name__ == "__main__":
    unittest.main()
