"""RealtimeGame + Snapshots: inputs, ticks, deltas, slow clients, ping, the real tick loop."""

import asyncio
import json
import unittest

from gamekit import LobbyError, RealtimeGame
from gamekit.sim import Sim


class Mover(RealtimeGame):
    """Each player has a position; input {"dx": -1..1} moves them 1 per tick."""

    TICK_RATE = 50
    ACTIONS = {"jump": "jump"}

    def start_game(self):
        self.pos = {p.id: 0 for p in self.players}
        self.finish_at = None

    def on_input(self, member, data):
        if data.get("dx") not in (-1, 0, 1):
            raise LobbyError("Bad input.")
        member.input = {"dx": data["dx"]}

    def tick(self, dt):
        for player in self.players:
            self.pos[player.id] += player.input.get("dx", 0)
        if self.finish_at is not None and self.tick_number >= self.finish_at:
            self.finish({"winner": None})

    def jump(self, member, data):
        self.pos[member.id] += 100

    def game_state(self):
        return {"pos": self.pos}

    def private_state(self, member):
        return {"mine": self.pos[member.id]} if member.id in self.pos else None


class BlockedSocket:
    """A client whose connection is stuck until released."""

    def __init__(self, loop):
        self.messages = []
        self.gate = loop.create_future()

    async def send(self, text):
        await self.gate
        self.messages.append(json.loads(text))


class RealtimeTests(unittest.TestCase):
    def setUp(self):
        self.sim = Sim(Mover, players=2)

    def test_start_sends_full_state_with_tick_rate(self):
        state = self.sim.state(0)
        self.assertEqual(state["phase"], "playing")
        self.assertEqual(state["tickRate"], 50)
        self.assertEqual(state["game"]["pos"], {self.sim.pid(0): 0, self.sim.pid(1): 0})

    def test_input_sends_nothing_until_tick(self):
        sim = self.sim
        before = len(sim.messages(1))
        self.assertIsNone(sim.input(0, {"dx": 1}))
        self.assertEqual(len(sim.messages(1)), before)
        sim.tick(3)
        snaps = sim.messages(1, "snap")
        self.assertEqual(len(snaps), 3)
        self.assertEqual(snaps[-1]["g"], {"pos": {sim.pid(0): 3}})
        self.assertEqual(sim.state(1)["game"]["pos"][sim.pid(0)], 3)
        self.assertEqual(sim.messages(0, "snap")[-1]["ack"], 1)
        self.assertEqual(sim.state(0)["private"], {"mine": 3})

    def test_empty_snaps_still_sent(self):
        sim = self.sim
        sim.tick(2)
        snap = sim.messages(0, "snap")[-1]
        self.assertNotIn("g", snap)
        self.assertEqual(snap["tick"], 2)
        self.assertIn("t", snap)

    def test_bad_input_rejected_and_spectator_input_ignored(self):
        sim = self.sim
        self.assertEqual(sim.input(0, {"dx": 5}), "Bad input.")
        watcher = sim.spectator()
        self.assertIsNone(sim.input(watcher, {"dx": 1}))
        sim.tick()
        self.assertEqual(sim.state(0)["game"]["pos"][sim.pid(0)], 0)

    def test_action_applies_at_next_tick(self):
        sim = self.sim
        before = len(sim.messages(1))
        sim.ok(0, {"action": "jump"})
        self.assertEqual(len(sim.messages(1)), before)
        sim.tick()
        self.assertEqual(sim.state(1)["game"]["pos"][sim.pid(0)], 100)

    def test_slow_client_skipped_then_catches_up(self):
        sim = self.sim
        stuck = BlockedSocket(sim.loop)
        sim.clients[1].ws = stuck
        sim.input(0, {"dx": 1})

        async def three_ticks_while_stuck():
            for _ in range(3):
                sim.game.step()
                await asyncio.sleep(0)

        sim._run(three_ticks_while_stuck())
        self.assertEqual(len(sim.messages(0, "snap")), 3)  # client 0 isn't held up
        stuck.gate.set_result(None)
        sim._run(sim.game.sync.drain())
        self.assertEqual(len(stuck.messages), 1)  # client 1 got only the first tick
        sim.tick()
        received = [m for m in stuck.messages if m["type"] == "snap"]
        self.assertEqual(len(received), 2)
        # The next snap is a delta against the last one client 1 actually got.
        self.assertEqual(received[1]["base"], received[0]["seq"])
        self.assertEqual(received[0]["g"], {"pos": {sim.pid(0): 1}})
        self.assertEqual(received[1]["g"], {"pos": {sim.pid(0): 4}})

    def test_finish_in_tick_sends_full_state(self):
        sim = self.sim
        sim.game.finish_at = 2
        sim.tick(2)
        self.assertEqual(sim.state(1)["phase"], "finished")
        self.assertEqual(sim.messages(1)[-1]["type"], "state")

    def test_changes_outside_play_are_patches(self):
        sim = self.sim
        sim.game.finish({"winner": None})
        sim._run(sim.game.update())
        sim.game.pos[sim.pid(0)] = 7
        sim._run(sim.game.update())
        last = sim.messages(1)[-1]
        self.assertEqual(last["type"], "patch")
        self.assertNotIn("t", last)
        self.assertEqual(sim.state(1)["game"]["pos"][sim.pid(0)], 7)

    def test_player_leaving_mid_game(self):
        sim = Sim(Mover, players=3)
        sim.leave(2)
        sim.tick()
        self.assertEqual(sim.state(0)["phase"], "playing")
        self.assertEqual(len(sim.state(0)["players"]), 2)

    def test_ping(self):
        sim = self.sim
        sim.lobby(0, {"type": "ping", "t": 123.5, "rtt": 42.4})
        self.assertEqual(sim.messages(0)[-1], {"type": "pong", "t": 123.5})
        self.assertEqual(sim.member(0).ping, 42)
        sim.ping(0, 10 ** 9)  # nonsense is ignored
        self.assertEqual(sim.member(0).ping, 42)


class TickLoopTests(unittest.TestCase):
    def test_loop_ticks_and_stops_when_finished(self):
        sim = Sim(Mover, players=1)
        game = sim.game
        del game._ensure_ticker  # use the real loop

        async def run():
            game._ensure_ticker()
            await asyncio.sleep(0.2)
            ticks = game.tick_number
            game.finish({"winner": None})
            await asyncio.sleep(0.1)
            return ticks

        ticks = sim._run(run())
        self.assertGreaterEqual(ticks, 5)
        self.assertTrue(game._ticker[1].done())
        self.assertEqual(sim.state(0)["phase"], "finished")


if __name__ == "__main__":
    unittest.main()
