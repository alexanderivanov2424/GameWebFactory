"""LobbyGame.admin_info: the room summary the site's admin view shows (server/admin.py)."""

import unittest

from gamekit import LobbyGame
from gamekit.sim import Sim
from server.admin import Admin
from server.accounts import AccountStore


class Plain(LobbyGame):
    pass


class AdminInfoTests(unittest.TestCase):
    def test_summary_lists_players_and_spectators(self):
        sim = Sim(Plain, players=2, start=False)
        sim.spectator("Watcher")
        info = sim.game.admin_info()
        self.assertEqual(info["phase"], "lobby")
        names = {m["name"]: m for m in info["members"]}
        self.assertTrue(names["Player1"]["host"] and names["Player1"]["playing"])
        self.assertFalse(names["Watcher"]["playing"])

    def test_admin_room_list_hides_client_ids(self):
        sim = Sim(Plain, players=1)

        class OneRoom:
            rooms = {("plain", "sim"): sim.room}

        [room] = Admin(AccountStore(None), sim.sessions, OneRoom, "/nonexistent").room_list()
        self.assertEqual(room["phase"], "playing")
        [member] = room["members"]
        self.assertNotIn("client", member)
        self.assertEqual(member["session"], sim.member(0).client_id[:8])
        self.assertTrue(member["online"])


if __name__ == "__main__":
    unittest.main()
