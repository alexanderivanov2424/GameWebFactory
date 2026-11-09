"""Deep Colony: lobby tests (gamekit.sim.Sim). Rules tests are in the other test_*.py files.
Run: python3 -I tools/run_tests.py deep-colony
"""

import unittest

from gamekit.sim import Sim

GAME = "deep-colony"


def new_game(players=2):
    return Sim(GAME, players=players, settings={"mapSize": "small", "colonists": 2})


def dig_target(sim):
    """A diggable cell (any solid that isn't bedrock)."""
    world = sim.game.match.world
    for y in range(2, world.h - 2):
        for x in range(2, world.w - 2):
            i = world.idx(x, y)
            if world.is_solid(i) and world.element_id(i) != "bedrock":
                return x, y
    raise AssertionError("no diggable cell")


class LobbyTests(unittest.TestCase):
    def test_any_player_pauses_and_sets_speed(self):
        sim = new_game()
        sim.ok(1, {"action": "pause", "paused": True})
        sim.tick(1)  # real-time games send changes with the next tick
        self.assertTrue(sim.state(0)["game"]["clock"]["paused"])
        sim.ok(0, {"action": "speed", "speed": 3})
        sim.tick(1)
        self.assertEqual(sim.state(1)["game"]["clock"]["speed"], 3)
        sim.fails(0, {"action": "speed", "speed": 4}, "Speed must be")

    def test_paused_colony_does_not_advance(self):
        sim = new_game()
        sim.ok(0, {"action": "pause", "paused": True})
        before = sim.game.match.time
        sim.tick(5)
        self.assertEqual(sim.game.match.time, before)

    def test_speed_runs_more_steps_per_tick(self):
        sim = new_game()
        sim.ok(0, {"action": "speed", "speed": 2})
        before = sim.game.match.time
        sim.tick(1)
        self.assertAlmostEqual(sim.game.match.time - before, 2 / sim.game.TICK_RATE)

    def test_orders_show_who_gave_them_to_everyone(self):
        sim = new_game()
        x, y = dig_target(sim)
        sim.ok(1, {"action": "dig", "rect": [x, y, x, y]})
        sim.tick(1)
        i = str(sim.game.match.world.idx(x, y))
        self.assertEqual(sim.state(0)["game"]["digs"][i]["by"], sim.pid(1))

    def test_spectator_cannot_order(self):
        sim = new_game()
        spectator = sim.spectator()
        sim.fails(spectator, {"action": "pause", "paused": True}, "not playing")

    def test_cursor_input_is_shown_to_everyone(self):
        sim = new_game()
        sim.input(0, {"cursor": [3, 4], "tool": "dig"})
        sim.tick(1)
        player = sim.state(1)["game"]["players"][sim.pid(0)]
        self.assertEqual((player["cursor"], player["tool"]), ([3, 4], "dig"))

    def test_bad_input_rejected(self):
        sim = new_game()
        sim.input(0, {"cursor": ["a", 4]})
        sim.tick(1)
        self.assertNotIn("cursor", sim.state(1)["game"]["players"][sim.pid(0)])

    def test_only_host_ends(self):
        sim = new_game()
        sim.fails(1, {"action": "end"}, "Only the host")
        sim.ok(0, {"action": "end"})
        self.assertEqual(sim.state(1)["phase"], "finished")

    def test_colony_ends_when_every_colonist_died(self):
        sim = new_game()
        match = sim.game.match
        match._had_dupes = True
        match.dupes.clear()
        sim.tick(1)
        self.assertEqual(sim.state(0)["phase"], "finished")


def walk_none(value, path="game"):
    if value is None:
        raise AssertionError(f"None at {path}")
    if isinstance(value, dict):
        for k, v in value.items():
            walk_none(v, f"{path}.{k}")
    elif isinstance(value, list):
        for n, v in enumerate(value):
            walk_none(v, f"{path}[{n}]")


def open_cell(sim):
    """A free, non-solid cell where something can be built (inside the border)."""
    world = sim.game.match.world
    b = sim.game.match.buildings
    for y in range(2, world.h - 3):
        for x in range(2, world.w - 2):
            if not world.is_solid(world.idx(x, y)) and b.can_place("wire", x, y) is None:
                return x, y
    raise AssertionError("no open cell")


class RobustnessTests(unittest.TestCase):
    def test_malformed_messages_are_rejected(self):
        sim = new_game()
        bad = [
            {"action": "dig"}, {"action": "dig", "rect": "abcd"}, {"action": "dig", "rect": [1, 2, 3]},
            {"action": "dig", "rect": [True, 2, 3, 4]}, {"action": "dig", "rect": [1.5, 2, 3, 4]},
            {"action": "dig", "rect": [0, 0, 100, 100]}, {"action": "dig", "rect": [-5, -5, -1, -1]},
            {"action": "dig", "rect": [10 ** 12, 0, 10 ** 12, 0]},
            {"action": "dig", "rect": [3, 3, 4, 4], "prio": True},
            {"action": "dig", "rect": [3, 3, 4, 4], "prio": "5"},
            {"action": "dig", "rect": [3, 3, 4, 4], "prio": 10},
            {"action": "cancel", "rect": None}, {"action": "deconstruct", "rect": {}},
            {"action": "build", "building": 5, "cells": [[3, 3]]},
            {"action": "build", "building": "wire", "cells": "x"},
            {"action": "build", "building": "wire", "cells": []},
            {"action": "build", "building": "wire", "cells": [[3, 3]] * 100000},
            {"action": "build", "building": "wire", "cells": [[3]]},
            {"action": "build", "building": "wire", "cells": [[True, 3]]},
            {"action": "build", "building": "wire", "cells": [None]},
            {"action": "build", "building": "nope", "cells": [[3, 3]]},
            {"action": "build", "building": ["wire"], "cells": [[3, 3]]},
            {"action": "build", "building": "arrival_pod", "cells": [[5, 5]]},
            {"action": "build", "building": "wire", "cells": [[0, 0]]},
            {"action": "build", "building": "wire", "cells": [[-1, 3]]},
            {"action": "toggle", "building": None}, {"action": "toggle", "building": ["b1"]},
            {"action": "toggle", "building": "zzz"},
            {"action": "pause", "paused": 1}, {"action": "pause", "paused": "yes"}, {"action": "pause"},
            {"action": "speed", "speed": True}, {"action": "speed", "speed": "2"},
            {"action": "speed", "speed": 2.0}, {"action": "speed"},
        ]
        for msg in bad:
            self.assertIsNotNone(sim.send(0, msg), msg)
        sim.tick(2)

    def test_build_on_rock_and_bedrock_rejected(self):
        sim = new_game()
        x, y = dig_target(sim)
        sim.fails(0, {"action": "build", "building": "wire", "cells": [[x, y]]}, "")
        world = sim.game.match.world
        sim.fails(0, {"action": "build", "building": "wire", "cells": [[world.w - 1, 5]]}, "")

    def test_bad_input_types_do_not_crash(self):
        sim = new_game()
        for data in ({"cursor": 5}, {"drag": [1, 2]}, {"cursor": [True, 1]}, {"tool": 5}, {"cursor": None}):
            sim.input(0, data)
        sim.tick(2)
        walk_none(sim.state(1)["game"])

    def test_public_state_has_no_none(self):
        sim = new_game()
        match = sim.game.match
        x, y = dig_target(sim)
        sim.ok(0, {"action": "dig", "rect": [x, y, x + 1, y + 1], "prio": 7})
        ox, oy = open_cell(sim)
        sim.ok(1, {"action": "build", "building": "wire", "cells": [[ox, oy]]})
        done = match.buildings.place("liquid_pipe", ox, oy, "p1", built=True)
        match.items.add("dirt", 3.0, ox, oy, 20.0)
        sim.input(0, {"cursor": [ox, oy], "drag": [0, 0, 3, 3], "tool": "dig"})
        sim.tick(5)
        walk_none(sim.state(0)["game"])
        walk_none(sim.state(1)["game"])
        walk_none(sim.state(0).get("private", {}))
        self.assertIsNotNone(done)

    def test_cancel_removes_dig_and_site_with_debris(self):
        sim = new_game()
        match = sim.game.match
        x, y = dig_target(sim)
        sim.ok(0, {"action": "dig", "rect": [x, y, x, y]})
        self.assertIn(match.world.idx(x, y), match.digs)
        sim.ok(0, {"action": "cancel", "rect": [x, y, x, y]})
        self.assertNotIn(match.world.idx(x, y), match.digs)
        ox, oy = open_cell(sim)
        sim.ok(0, {"action": "build", "building": "wire", "cells": [[ox, oy]]})
        site = match.buildings.at(ox, oy, "wire")
        site.delivered["copper"] = 2.0
        before = sum(i.kg for i in match.items)
        sim.ok(0, {"action": "cancel", "rect": [ox, oy, ox, oy]})
        self.assertIsNone(match.buildings.at(ox, oy, "wire"))
        self.assertAlmostEqual(sum(i.kg for i in match.items) - before, 2.0)

    def test_deconstruct_site_removes_it_and_pod_is_kept(self):
        sim = new_game()
        match = sim.game.match
        ox, oy = open_cell(sim)
        sim.ok(0, {"action": "build", "building": "wire", "cells": [[ox, oy]]})
        sim.ok(0, {"action": "deconstruct", "rect": [ox, oy, ox, oy]})
        self.assertIsNone(match.buildings.at(ox, oy, "wire"))
        pod = match.buildings.of_kind("none")
        pod = [b for b in match.buildings if b.type == "arrival_pod"][0]
        sim.fails(0, {"action": "deconstruct", "rect": [pod.x, pod.y, pod.x, pod.y]}, "Nothing to deconstruct")
        self.assertFalse(pod.deconstruct)

    def test_priority_changes_digs_and_buildings(self):
        sim = new_game()
        match = sim.game.match
        x, y = dig_target(sim)
        ox, oy = open_cell(sim)
        sim.ok(0, {"action": "dig", "rect": [x, y, x, y]})
        sim.ok(0, {"action": "build", "building": "wire", "cells": [[ox, oy]]})
        sim.ok(1, {"action": "priority", "rect": [x, y, x, y], "prio": 9})
        sim.ok(1, {"action": "priority", "rect": [ox, oy, ox, oy], "prio": 9})
        self.assertEqual(match.digs[match.world.idx(x, y)]["prio"], 9)
        self.assertEqual(match.buildings.at(ox, oy, "wire").prio, 9)

    def test_toggle_passive_building_rejected(self):
        sim = new_game()
        ox, oy = open_cell(sim)
        match = sim.game.match
        match.buildings.place("wire", ox, oy, "p1", built=True)
        b = match.buildings.at(ox, oy, "wire")
        if b.d["kind"] == "none":
            sim.fails(0, {"action": "toggle", "building": b.id}, "can't be switched")

    def test_leaving_players(self):
        sim = new_game(3)
        x, y = dig_target(sim)
        sim.ok(2, {"action": "dig", "rect": [x, y, x, y]})
        sim.leave(2)
        sim.tick(3)
        self.assertEqual(sim.state(0)["phase"], "playing")
        self.assertIn(str(sim.game.match.world.idx(x, y)), sim.state(0)["game"]["digs"])
        sim.leave(1)
        sim.tick(1)
        self.assertEqual(sim.state(0)["phase"], "playing")
        sim.leave(0)
        self.assertNotEqual(sim.game.phase, "playing")

    def test_private_cell_follows_cursor(self):
        sim = new_game()
        spectator = sim.spectator()
        sim.input(0, {"cursor": [3, 4]})
        sim.tick(1)
        cell = sim.state(0)["private"]["cell"]
        self.assertEqual((cell["x"], cell["y"]), (3, 4))
        sim.input(0, {"cursor": [5, 6]})
        sim.tick(1)
        cell = sim.state(0)["private"]["cell"]
        self.assertEqual((cell["x"], cell["y"]), (5, 6))
        sim.input(0, {"cursor": [999, 6]})
        sim.tick(1)
        self.assertNotIn("cell", sim.state(0).get("private") or {})
        self.assertNotIn("cell", sim.state(spectator).get("private") or {})
        sim.input(1, {"cursor": [3, 4]})
        sim.tick(1)
        self.assertNotIn("cell", sim.state(spectator).get("private") or {})



import importlib  # noqa: E402

buildings_mod = importlib.import_module("games.deep-colony.logic.buildings")
research_mod = importlib.import_module("games.deep-colony.logic.research")
content_mod = importlib.import_module("games.deep-colony.logic.content")
Match = importlib.import_module("games.deep-colony.logic.match").Match


def any_rotatable(ports=False):
    for bid, d in content_mod.BUILDINGS.items():
        if d["rotatable"] and d["w"] != d["h"] and (not ports or any(d[p] for p in content_mod.PORTS)):
            return bid, d
    return None, None


class GroundworkTests(unittest.TestCase):
    def test_footprint_rotation_swaps_size_and_keeps_cell_count(self):
        bid, d = any_rotatable()
        if bid is None:
            self.skipTest("no non-square rotatable building")
        for rot in range(4):
            w, h, cells = buildings_mod.footprint(d, rot)
            self.assertEqual((w, h), (d["w"], d["h"]) if rot % 2 == 0 else (d["h"], d["w"]))
            self.assertEqual(sorted(cells), sorted((x, y) for x in range(w) for y in range(h)))

    def test_four_turns_bring_a_port_back(self):
        bid, d = any_rotatable(ports=True)
        if bid is None:
            self.skipTest("no rotatable building with ports")
        port = next(p for p in content_mod.PORTS if d[p])
        self.assertEqual(buildings_mod.rotate_offset(d, 4, d[port]), tuple(d[port]))
        m = Match.blank(12, 12)
        b = m.buildings.place(bid, 3, 3, "p1", built=True, rot=1)
        self.assertIn(b.port_cell(port), b.cells())

    def test_non_rotatable_building_refuses_rotation(self):
        bid = next(b for b, d in content_mod.BUILDINGS.items() if d["buildable"] and not d["rotatable"])
        m = Match.blank(12, 12)
        self.assertEqual(m.buildings.can_place(bid, 3, 3, 1), "That building can't be turned.")

    def test_locked_building_needs_research(self):
        if not research_mod.LOCKED_BY:
            self.skipTest("no locked buildings")
        btype, tech = next(iter(research_mod.LOCKED_BY.items()))
        m = Match.blank(16, 16)
        orders = importlib.import_module("games.deep-colony.logic.orders")
        with self.assertRaises(Exception) as ctx:
            orders.build(m, "p1", btype, [(4, 4)])
        self.assertIn("Research", str(ctx.exception))
        m.research.done.add(tech)
        self.assertTrue(m.research.is_unlocked(btype))

    def test_store_temperature_is_mass_averaged(self):
        m = Match.blank(12, 12)
        b = m.buildings.place("storage_bin", 3, 3, "p1", built=True)
        b.deliver("sand", 10, 40.0)
        b.deliver("sand", 10, 0.0)
        kg, temp, _ = b.take("sand", 5)
        self.assertEqual((kg, round(temp, 3)), (5, 20.0))

    def test_sweep_filter_research_schedule_actions(self):
        sim = new_game()
        m = sim.game.match
        x, y = open_cell(sim)
        m.items.add("sand", 50, x, y)
        sim.ok(1, {"action": "sweep", "rect": [x, y, x, y]})
        self.assertEqual(m.items.at(x, y)[0].sweep["by"], sim.pid(1))
        sim.ok(0, {"action": "cancel", "rect": [x, y, x, y]})
        self.assertIsNone(m.items.at(x, y)[0].sweep)
        pod = next(b for b in m.buildings if b.type == "arrival_pod")
        sim.fails(0, {"action": "filter", "building": pod.id, "elements": ["sand"]}, "no filter")
        tech = next(t for t, d in research_mod.TECHS.items() if not d["requires"])
        sim.ok(1, {"action": "research", "tech": tech})
        self.assertEqual(m.research.current, tech)
        sim.ok(0, {"action": "schedule", "schedule": "2", "blocks": "s" * 24})
        sim.fails(0, {"action": "schedule", "schedule": "2", "blocks": "x" * 24}, "24 blocks")
        dupe = next(iter(m.dupes))
        sim.ok(1, {"action": "assign", "colonist": dupe, "schedule": "2"})
        self.assertEqual(m.dupes[dupe].schedule, "2")
        sim.fails(0, {"action": "build", "building": "ladder", "cells": [[x, y]], "rot": 1}, "can't be turned")


if __name__ == "__main__":
    unittest.main()
