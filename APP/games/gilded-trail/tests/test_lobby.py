"""Gilded Trail: lobby tests through gamekit.sim.Sim (real messages, hidden hands, leaving).

Run: python3 -I tools/run_tests.py gilded-trail
"""

import unittest

from gamekit.sim import Sim

GAME = "gilded-trail"


def new_sim(**kw):
    return Sim(GAME, players=2, settings={"map": "serpent"}, **kw)


def mover(sim):
    """(index of the player whose turn it is, index of the other)."""
    i = sim.index_of(sim.game.match.turn())
    return i, 1 - i


class MessageTests(unittest.TestCase):
    def test_game_starts_playing(self):
        sim = new_sim()
        self.assertEqual(sim.state(0)["phase"], "playing")
        self.assertEqual(sim.state(0)["game"]["board"]["name"], "Serpent River")

    def test_not_your_turn_is_rejected(self):
        sim = new_sim()
        me, other = mover(sim)
        sim.fails(other, {"action": "endTurn", "discard": []}, "not your turn")
        sim.fails(other, {"action": "buy", "card": "tracker", "cards": [1]}, "not your turn")
        sim.ok(me, {"action": "endTurn", "discard": []})
        sim.fails(me, {"action": "endTurn", "discard": []}, "not your turn")
        sim.ok(other, {"action": "endTurn", "discard": []})

    def test_bad_message_shapes_are_rejected(self):
        sim = new_sim()
        me, _ = mover(sim)
        bad = [
            ({"action": "zzz"}, "Unknown action"),
            ({"action": "move", "explorer": "0", "to": "0,0"}, "explorer"),
            ({"action": "move", "explorer": 0}, "bad to"),
            ({"action": "move", "explorer": 0, "to": 5}, "bad to"),
            ({"action": "move", "explorer": 0, "to": "0,0", "card": "x"}, "Pick a card"),
            ({"action": "move", "explorer": True, "to": "0,0"}, "explorer"),
            ({"action": "pay", "explorer": 0, "to": "0,0", "cards": "1"}, "Bad card list"),
            ({"action": "pay", "explorer": 0, "to": "0,0", "cards": [1, "2"]}, "Bad card list"),
            ({"action": "pay", "explorer": 0, "to": "0,0", "cards": [True]}, "Bad card list"),
            ({"action": "buy", "card": 7, "cards": [1]}, "bad card"),
            ({"action": "buy", "card": "tracker", "cards": list(range(50))}, "Bad card list"),
            ({"action": "play", "card": "1"}, "Pick a card"),
            ({"action": "play"}, "Pick a card"),
            ({"action": "trash", "cards": None}, "Bad card list"),
            ({"action": "take", "card": 5}, "bad card"),
            ({"action": "guide", "explorer": 0, "to": 5}, "bad to"),
            ({"action": "endTurn", "discard": {"a": 1}}, "Bad card list"),
        ]
        for message, text in bad:
            sim.fails(me, message, text)
        self.assertEqual(sim.game.match.turn(), sim.pid(me))  # nothing changed

    def test_cards_not_in_hand_or_off_board_are_rejected(self):
        sim = new_sim()
        me, _ = mover(sim)
        sim.fails(me, {"action": "endTurn", "discard": [9999]}, "isn't in your hand")
        sim.fails(me, {"action": "move", "explorer": 5, "to": "0,0"}, "explorers")
        sim.fails(me, {"action": "move", "explorer": 0, "to": "999,999", "card": 1}, "next to")
        sim.fails(me, {"action": "trash", "cards": []}, "nothing like that")

    def test_turn_passes_after_end_turn(self):
        sim = new_sim()
        me, other = mover(sim)
        sim.ok(me, {"action": "endTurn", "discard": []})
        self.assertEqual(sim.game.match.turn(), sim.pid(other))
        self.assertEqual(sim.state(me)["game"]["turn"], sim.pid(other))


class PrivacyTests(unittest.TestCase):
    def test_hands_are_only_in_the_owners_private_state(self):
        sim = new_sim()
        watcher = sim.spectator()
        for i in (0, 1):
            private = sim.state(i)["private"]
            self.assertEqual(len(private["hand"]), 4)
            self.assertEqual(private["hand"], sim.game.match.players[sim.pid(i)]["hand"])
        self.assertNotEqual(sim.state(0)["private"]["hand"], sim.state(1)["private"]["hand"])
        self.assertIsNone(sim.state(watcher).get("private"))

    def test_public_state_only_has_hand_counts(self):
        sim = new_sim()
        watcher = sim.spectator()
        for i in (0, 1, watcher):
            players = sim.state(i)["game"]["players"]
            for pid, p in players.items():
                self.assertEqual(p["hand"], 4)
                self.assertIsInstance(p["deck"], int)
                self.assertNotIn("uid", repr(p))
        text = repr(sim.state(watcher)["game"])
        for i in (0, 1):
            for card in sim.state(i)["private"]["hand"]:
                self.assertNotIn(f"'uid': {card['uid']}", text)

    def test_options_only_for_the_player_whose_turn_it_is(self):
        sim = new_sim()
        me, other = mover(sim)
        self.assertIn("options", sim.state(me)["private"])
        self.assertNotIn("options", sim.state(other)["private"])


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.sim = Sim(GAME, start=False)

    def test_map_must_be_a_listed_choice(self):
        self.assertIn("Map must be one of", self.sim.lobby(0, {"type": "settings", "settings": {"map": "nope"}}))
        self.assertIsNone(self.sim.lobby(0, {"type": "settings", "settings": {"map": "random"}}))
        self.assertEqual(self.sim.game.settings["map"], "random")

    def test_tiles_are_clamped_and_must_be_numbers(self):
        self.sim.lobby(0, {"type": "settings", "settings": {"tiles": 99}})
        self.assertEqual(self.sim.game.settings["tiles"], 9)
        self.sim.lobby(0, {"type": "settings", "settings": {"tiles": 0}})
        self.assertEqual(self.sim.game.settings["tiles"], 3)
        self.assertIn("whole number", self.sim.lobby(0, {"type": "settings", "settings": {"tiles": "x"}}))

    def test_seed_is_clamped(self):
        self.sim.lobby(0, {"type": "settings", "settings": {"seed": 10 ** 9}})
        self.assertEqual(self.sim.game.settings["seed"], 999999)

    def test_random_map_with_seed_is_reproducible(self):
        boards = []
        for _ in range(2):
            sim = Sim(GAME, players=2, settings={"map": "random", "tiles": 4, "seed": 55})
            boards.append(sim.state(0)["game"]["board"]["hexes"])
        self.assertEqual(boards[0], boards[1])


class LeavingTests(unittest.TestCase):
    def test_leaving_mid_game_finishes_it_for_the_other(self):
        sim = new_sim()
        me, other = mover(sim)
        sim.leave(other)
        state = sim.state(me)
        self.assertEqual(state["phase"], "finished")
        self.assertEqual(state["result"]["winner"], sim.pid(me))

    def test_current_player_leaving_also_ends_a_two_player_game(self):
        sim = new_sim()
        me, other = mover(sim)
        sim.leave(me)
        self.assertEqual(sim.state(other)["phase"], "finished")
        self.assertEqual(sim.state(other)["result"]["winner"], sim.pid(other))

    def test_three_players_leaving_keeps_the_game_going(self):
        sim = Sim(GAME, players=3, settings={"map": "serpent"})
        cur = sim.index_of(sim.game.match.turn())
        sim.leave(cur)
        self.assertEqual(sim.state((cur + 1) % 3)["phase"], "playing")
        self.assertNotEqual(sim.game.match.turn(), sim.pid(cur))
