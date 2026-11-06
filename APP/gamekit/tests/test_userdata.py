"""Saved player data through LobbyGame.load_data / save_data / account_name, driven by Sim."""

import unittest

from gamekit import LobbyGame
from gamekit.sim import Sim
from server import sessions
from server.turtle import Turtled
from server.accounts import AccountError


class Counter(LobbyGame):
    """Each "win" action adds one to the player's saved win count."""

    ACTIONS = {"win": "win"}

    def win(self, member, data):
        saved = self.load_data(member) or {"wins": 0}
        self.save_data(member, {"wins": saved["wins"] + 1})

    def game_state(self):
        return {"accounts": {m.id: self.account_name(m) for m in self.players}}


class UserDataTests(unittest.TestCase):
    def wins(self, sim, index):
        data = sim.game.load_data(sim.member(index))
        return data and data["wins"]

    def test_guest_save_and_load(self):
        sim = Sim(Counter, players=2)
        sim.ok(0, {"action": "win"})
        sim.ok(0, {"action": "win"})
        self.assertEqual(self.wins(sim, 0), 2)
        self.assertIsNone(self.wins(sim, 1))
        self.assertEqual(sim.state(0)["game"]["accounts"], {sim.pid(0): None, sim.pid(1): None})

    def test_logged_in_player_and_transfer(self):
        sim = Sim(Counter, players=2, start=False)
        sim.login(1, "bob")
        sim.start()
        sim.ok(0, {"action": "win"})
        sim.ok(1, {"action": "win"})
        self.assertEqual(sim.sessions.store.load("bob", "Counter"), {"wins": 1})
        self.assertEqual(sim.state(0)["game"]["accounts"], {sim.pid(0): None, sim.pid(1): "bob"})
        sim.lobby(0, {"type": "leave"})
        sim.lobby(1, {"type": "leave"})  # back in the lobby: logging in is allowed again
        sim.login(0, "alice")  # guest progress moves to the new account
        self.assertEqual(sim.sessions.store.load("alice", "Counter"), {"wins": 1})

    def test_games_are_kept_apart(self):
        sim = Sim(Counter, players=1)
        sim.ok(0, {"action": "win"})
        client = sim.clients[0].id
        self.assertIsNone(sim.sessions.load(client, "other-game"))
        self.assertEqual(sim.sessions.load(client, "Counter"), {"wins": 1})

    def test_no_logout_during_play(self):
        sim = Sim(Counter, players=1, start=False)
        sim.login(0, "alice")
        self.assertFalse(sim.game.busy(sim.clients[0].id))
        sim.start()
        self.assertTrue(sim.game.busy(sim.clients[0].id))
        with self.assertRaisesRegex(AccountError, "during a game"):
            sim.logout(0)

    def test_spamming_saves_turtles(self):
        sim = Sim(Counter, players=1)
        for _ in range(sessions.MAX_SAVES_PER_SESSION):
            sim.ok(0, {"action": "win"})
        with self.assertRaises(Turtled):
            sim.send(0, {"action": "win"})
