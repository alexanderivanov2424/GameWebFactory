"""Tanks: settings, placing, every action, shields, mines, hidden information, game end, leaving.

Tests are deterministic: no random walls, and positions, mines and turn order are set
directly on `sim.game` after (or instead of) going through the placing stage.
"""

import json
import unittest

from gamekit import TurnQueue
from gamekit.sim import Sim

SIZE = 6
A, B, C = 0, 1, 2  # player indexes


def place(sim, index, row, col, mines):
    sim.ok(index, {"action": "place", "row": row, "col": col, "mines": mines})


def new_battle(players=2, tanks=None, size=SIZE, hp=None, **settings):
    """A game in the action stage. tanks: [(row, col)] per player (default: spread out).

    Everyone really places (mines far from the action at (size-1, size-1) and the square
    next to it), then turn order is fixed to A, B, C... with counters 1, 2, 3.
    """
    settings = {"boardSize": size, "wallChance": 0, **settings}
    if hp is not None:
        settings["hp"] = hp
    sim = Sim("tanks", players=players, settings=settings)
    tanks = tanks or [(0, 0), (0, 3), (4, 4)][:players]
    for i, (row, col) in enumerate(tanks):
        place(sim, i, row, col, [[size - 1, size - 1], [size - 1, size - 2]])
    sim.game.mines = []  # start every test without mines on the board
    sim.game.queue = TurnQueue([sim.pid(i) for i in range(players)], staggered=True)
    assert sim.game.stage == "action"
    return sim


def values(sim):
    return dict(sim.game.queue.values)


def cost_of(sim, index, action):
    """Send an action for `index` and return how much it added to their turn counter."""
    pid = sim.pid(index)
    before = sim.game.queue.values[pid]
    sim.ok(index, action)
    return sim.game.queue.values[pid] - before


def public(sim, index):
    return sim.state(index)["game"]


def player(sim, observer, index):
    return next(p for p in public(sim, observer)["players"] if p["id"] == sim.pid(index))


class SettingsTests(unittest.TestCase):
    def test_defaults_and_spec(self):
        sim = Sim("tanks", start=False)
        self.assertEqual(
            sim.game.settings,
            {"boardSize": 8, "hp": 5, "sprayCost": 2, "artilleryCost": 3, "wallChance": 15},
        )
        spec = {field["key"]: field for field in sim.state(0)["settingsSpec"]}
        self.assertEqual(list(spec), ["boardSize", "hp", "sprayCost", "artilleryCost", "wallChance"])
        self.assertEqual(spec["wallChance"]["suffix"], "%")
        self.assertEqual((spec["boardSize"]["min"], spec["boardSize"]["max"]), (4, 12))

    def test_values_are_clamped(self):
        sim = Sim("tanks", start=False)
        sim.lobby(0, {"type": "settings", "settings": {
            "boardSize": 99, "hp": 0, "sprayCost": 500, "artilleryCost": -3, "wallChance": 101,
        }})
        self.assertEqual(
            sim.game.settings,
            {"boardSize": 12, "hp": 1, "sprayCost": 20, "artilleryCost": 1, "wallChance": 100},
        )
        sim.lobby(0, {"type": "settings", "settings": {"boardSize": 1, "wallChance": -1}})
        self.assertEqual(sim.game.settings["boardSize"], 4)
        self.assertEqual(sim.game.settings["wallChance"], 0)

    def test_non_numbers_are_rejected(self):
        sim = Sim("tanks", start=False)
        for bad in ("5", None, 2.5, True, [3]):
            error = sim.lobby(0, {"type": "settings", "settings": {"hp": bad}})
            self.assertEqual(error, "Starting HP must be a whole number.", bad)
        self.assertEqual(sim.game.settings["hp"], 5)

    def test_missing_settings_keep_their_value(self):
        sim = Sim("tanks", start=False)
        sim.lobby(0, {"type": "settings", "settings": {"hp": 9}})
        self.assertEqual(sim.game.settings["hp"], 9)
        self.assertEqual(sim.game.settings["boardSize"], 8)

    def test_only_the_host_changes_settings(self):
        sim = Sim("tanks", start=False)
        self.assertIsNotNone(sim.lobby(1, {"type": "settings", "settings": {"hp": 9}}))
        self.assertEqual(sim.game.settings["hp"], 5)

    def test_settings_apply_to_the_game(self):
        sim = Sim("tanks", settings={"boardSize": 5, "hp": 7, "sprayCost": 4, "artilleryCost": 6, "wallChance": 0})
        game = public(sim, 0)
        self.assertEqual((game["size"], game["maxHp"]), (5, 7))
        self.assertEqual(game["walls"], [])
        self.assertEqual((game["costs"]["spray"], game["costs"]["artillery"]), (4, 6))
        self.assertEqual({p["hp"] for p in game["players"]}, {7})

    def test_scan_cost_table(self):
        sim = Sim("tanks", settings={"boardSize": 6, "wallChance": 0})
        # scan[k - 1] = cost of k lines: a single line 3, up to half 2, over half 1.
        self.assertEqual(public(sim, 0)["costs"]["scan"], [3, 2, 2, 1, 1, 1])
        sim = Sim("tanks", settings={"boardSize": 5, "wallChance": 0})
        self.assertEqual(public(sim, 0)["costs"]["scan"], [3, 2, 1, 1, 1])

    def test_game_number_is_top_level(self):
        sim = Sim("tanks")
        self.assertEqual(sim.state(0)["gameNumber"], 1)
        self.assertNotIn("gameNumber", public(sim, 0))
        sim.lobby(0, {"type": "back_to_lobby"})  # not finished yet: rejected, still game 1
        sim.game.finish({"winner": None, "reason": None})
        sim.lobby(0, {"type": "back_to_lobby"})
        sim.start()
        self.assertEqual(sim.state(0)["gameNumber"], 2)


class PlacingTests(unittest.TestCase):
    def new(self, players=3):
        return Sim("tanks", players=players, settings={"boardSize": SIZE, "wallChance": 0})

    def test_starts_in_placing_with_a_turn_order(self):
        sim = self.new()
        game = public(sim, 0)
        self.assertEqual(game["stage"], "placing")
        self.assertIsNone(game["current"])
        self.assertEqual(sorted(sim.game.queue.order()), sorted(sim.pid(i) for i in range(3)))
        self.assertEqual([p["placed"] for p in game["players"]], [False] * 3)

    def test_validation(self):
        sim = self.new()
        bad_tank = {"action": "place", "row": 0, "col": 0}
        sim.fails(A, {**bad_tank, "mines": [[0, 1]]}, "exactly 2 mines")
        sim.fails(A, {**bad_tank, "mines": [[0, 1], [0, 2], [0, 3]]}, "exactly 2 mines")
        sim.fails(A, {**bad_tank, "mines": "no"}, "exactly 2 mines")
        sim.fails(A, {**bad_tank}, "exactly 2 mines")
        sim.fails(A, {**bad_tank, "mines": [[1, 1], [1, 1]]}, "different squares")
        sim.fails(A, {**bad_tank, "mines": [[1, 1], [6, 0]]}, "not a square")
        sim.fails(A, {**bad_tank, "mines": [[1, 1], [0]]}, "not a square")
        sim.fails(A, {**bad_tank, "mines": [[1, 1], [True, 0]]}, "not a square")
        sim.fails(A, {"action": "place", "row": SIZE, "col": 0, "mines": [[1, 1], [2, 2]]}, "not a square")
        sim.fails(A, {"action": "place", "row": "0", "col": 0, "mines": [[1, 1], [2, 2]]}, "not a square")
        self.assertEqual(sim.game.locations, {})
        self.assertEqual(sim.game.mines, [])

    def test_only_placing_is_allowed_first(self):
        sim = self.new()
        sim.fails(A, {"action": "move", "row": 0, "col": 1}, "hidden location first")
        sim.fails(A, {"action": "nonsense"}, "hidden location first")

    def test_place_once_and_stage_ends_when_all_placed(self):
        sim = self.new()
        place(sim, A, 0, 0, [[1, 1], [2, 2]])
        sim.fails(A, {"action": "place", "row": 3, "col": 3, "mines": [[1, 1], [2, 2]]}, "already chosen")
        self.assertEqual(sim.game.locations[sim.pid(A)], [0, 0])
        self.assertTrue(player(sim, B, A)["placed"])
        self.assertEqual(public(sim, B)["stage"], "placing")
        place(sim, B, 0, 3, [[1, 1], [2, 2]])
        self.assertEqual(public(sim, C)["stage"], "placing")
        place(sim, C, 4, 4, [[0, 0], [5, 5]])
        game = public(sim, A)
        self.assertEqual(game["stage"], "action")
        self.assertEqual(game["log"], [{"type": "start"}])
        self.assertEqual(game["current"], sim.game.queue.current())

    def test_tanks_and_mines_may_share_squares(self):
        sim = self.new(players=2)
        place(sim, A, 2, 2, [[2, 2], [3, 3]])
        place(sim, B, 2, 2, [[2, 2], [3, 3]])
        self.assertEqual(sim.game.stage, "action")
        self.assertEqual(len(sim.game.mines), 4)

    def test_nothing_is_acted_on_before_everyone_hid(self):
        sim = self.new()
        place(sim, A, 0, 0, [[1, 1], [2, 2]])
        sim.fails(A, {"action": "heal"}, "hidden location first")

    def test_hidden_information_while_placing(self):
        sim = self.new()
        place(sim, A, 0, 0, [[1, 1], [2, 2]])
        for observer in (B, C):
            state = sim.state(observer)
            self.assertIsNone(state["game"]["locations"])
            self.assertIsNone(state["game"]["mines"])
            self.assertEqual(state["private"], {"location": None, "mines": [], "notes": {}})
            self.assertNotIn('"mines": [[', json.dumps(state["game"]))
        self.assertEqual(sim.state(A)["private"]["location"], [0, 0])
        self.assertEqual(sim.state(A)["private"]["mines"], [[1, 1], [2, 2]])


class HiddenInformationTests(unittest.TestCase):
    def test_other_players_get_only_their_own_secrets(self):
        sim = new_battle(3)
        sim.game.mines = [{"owner": sim.pid(A), "row": 3, "col": 3}]
        sim.ok(A, {"action": "move", "row": 0, "col": 1})
        sim.ok(B, {"action": "mine", "row": 0, "col": 4})
        self.assertEqual(sim.state(A)["private"]["location"], [0, 1])
        self.assertEqual(sim.state(B)["private"]["location"], [0, 3])
        self.assertEqual(sim.state(C)["private"]["location"], [4, 4])
        self.assertEqual(sim.state(A)["private"]["mines"], [[3, 3]])
        self.assertEqual(sim.state(B)["private"]["mines"], [[0, 4]])
        self.assertEqual(sim.state(C)["private"]["mines"], [])
        for observer in (A, B, C):
            game = public(sim, observer)
            self.assertIsNone(game["locations"])
            self.assertIsNone(game["mines"])
            for entry in game["log"]:
                if entry["type"] in ("move", "mine"):
                    self.assertFalse({"row", "col", "cell", "to", "from"} & set(entry), entry)

    def test_spectators_get_no_private_information(self):
        sim = new_battle(2)
        watcher = sim.spectator()
        sim.ok(A, {"action": "scan", "axis": "row", "from": 0, "to": 0})
        state = sim.state(watcher)
        self.assertIsNone(state["private"])
        self.assertIsNone(state["game"]["locations"])
        self.assertIsNone(state["game"]["mines"])
        sim.fails(watcher, {"action": "heal"}, "not playing")

    def test_everything_is_revealed_when_the_game_ends(self):
        sim = new_battle(2, hp=1)
        sim.game.mines = [{"owner": sim.pid(B), "row": 2, "col": 2}]
        sim.ok(A, {"action": "artillery", "row": 0, "col": 3})
        game = public(sim, A)
        self.assertEqual(game["locations"], {sim.pid(A): [0, 0], sim.pid(B): [0, 3]})
        self.assertEqual(game["mines"], [{"owner": sim.pid(B), "row": 2, "col": 2}])
        self.assertEqual(public(sim, A)["locations"], public(sim, B)["locations"])


class ActionTests(unittest.TestCase):
    def test_turn_order_and_wrong_player(self):
        sim = new_battle(3)
        sim.fails(B, {"action": "heal"}, "not your turn")
        sim.fails(C, {"action": "move", "row": 4, "col": 3}, "not your turn")
        self.assertEqual(public(sim, A)["current"], sim.pid(A))
        sim.ok(A, {"action": "move", "row": 0, "col": 1})
        self.assertEqual(public(sim, A)["current"], sim.pid(B))
        sim.fails(A, {"action": "move", "row": 0, "col": 0}, "not your turn")

    def test_unknown_action_and_place_after_placing(self):
        sim = new_battle(2)
        sim.fails(A, {"action": "teleport"}, "Unknown action")
        sim.fails(A, {}, "Unknown action")
        sim.fails(A, {"action": "place", "row": 1, "col": 1, "mines": [[2, 2], [3, 3]]}, "Unknown action")
        sim.fails(B, {"action": "teleport"}, "not your turn")

    def test_cheap_actions_can_repeat_before_others_act(self):
        sim = new_battle(2)  # A=1, B=2
        sim.ok(A, {"action": "wall", "cells": [[3, 3], [3, 4]]})  # A=2, B reached 2 first
        self.assertEqual(public(sim, A)["current"], sim.pid(B))
        sim.ok(B, {"action": "blast", "dir": "down"})  # B=7
        self.assertEqual(public(sim, A)["current"], sim.pid(A))
        sim.ok(A, {"action": "wall", "cells": [[3, 1], [3, 2]]})
        self.assertEqual(public(sim, A)["current"], sim.pid(A))  # A=3 is still lowest

    def test_scan(self):
        sim = new_battle(2)  # A (0,0), B (0,3)
        # Scanning rows 0 (a single line): cost 3. Finds B, the scanner is not counted.
        self.assertEqual(cost_of(sim, A, {"action": "scan", "axis": "row", "from": 0, "to": 0}), 3)
        self.assertEqual(sim.state(A)["private"]["notes"], {"1": {"found": True}})
        note = sim.game.notes[sim.pid(A)]
        self.assertEqual(note, {1: {"found": True}})  # log[0] is the "start" entry
        entry = public(sim, B)["log"][-1]
        self.assertEqual(entry, {"type": "scan", "actor": sim.pid(A), "axis": "row", "from": 0, "to": 0, "cost": 3})
        self.assertEqual(sim.state(B)["private"]["notes"], {})  # the target learns nothing
        sim.ok(B, {"action": "scan", "axis": "col", "from": 4, "to": 5})  # two columns of six: cost 2, empty
        self.assertEqual(sim.game.notes[sim.pid(B)], {2: {"found": False}})

    def test_scan_costs_and_ranges(self):
        sim = new_battle(2)
        self.assertEqual(cost_of(sim, A, {"action": "scan", "axis": "col", "from": 1, "to": 3}), 2)  # exactly half
        sim.game.queue.values[sim.pid(B)] = 99
        self.assertEqual(cost_of(sim, A, {"action": "scan", "axis": "col", "from": 0, "to": 3}), 1)  # over half
        self.assertEqual(cost_of(sim, A, {"action": "scan", "axis": "row", "from": 0, "to": 5}), 1)  # everything
        self.assertEqual(cost_of(sim, A, {"action": "scan", "axis": "row", "from": 2, "to": 2}), 3)

    def test_scan_never_finds_yourself_and_ignores_the_dead(self):
        sim = new_battle(3)  # A (0,0), B (0,3), C (4,4)
        sim.ok(A, {"action": "scan", "axis": "col", "from": 0, "to": 0})
        self.assertFalse(sim.game.notes[sim.pid(A)][1]["found"])
        sim.game.queue.remove(sim.pid(B))  # B destroyed: scanning column 3 now finds nobody
        sim.game.queue.values[sim.pid(A)] = 0
        sim.ok(A, {"action": "scan", "axis": "col", "from": 3, "to": 3})
        self.assertFalse(sim.game.notes[sim.pid(A)][2]["found"])

    def test_scan_validation(self):
        sim = new_battle(2)
        for action in (
            {"axis": "diagonal", "from": 0, "to": 1},
            {"axis": ["row"], "from": 0, "to": 1},
            {"from": 0, "to": 1},
            {"axis": "row", "from": 2, "to": 1},
            {"axis": "row", "from": -1, "to": 1},
            {"axis": "row", "from": 0, "to": SIZE},
            {"axis": "row", "from": "0", "to": 1},
            {"axis": "row", "from": 0, "to": True},
        ):
            error = sim.send(A, {"action": "scan", **action})
            self.assertIsNotNone(error, action)
            self.assertIn("Scan rows or columns." if action.get("axis") not in ("row",) else "valid range", error)
        self.assertEqual(sim.game.log, [{"type": "start"}])
        self.assertEqual(values(sim)[sim.pid(A)], 1)

    def test_spray(self):
        sim = new_battle(2, tanks=[(0, 0), (1, 3)])
        sim.fails(A, {"action": "spray", "row": SIZE - 1, "col": 0}, "2x2 area")
        sim.fails(A, {"action": "spray", "row": 0, "col": SIZE - 1}, "2x2 area")
        self.assertEqual(sim.game.hp[sim.pid(B)], 5)
        self.assertEqual(cost_of(sim, A, {"action": "spray", "row": 0, "col": 2}), 2)  # covers (1, 3)
        self.assertEqual(sim.game.hp[sim.pid(B)], 4)
        entry = public(sim, B)["log"][-1]
        self.assertEqual(entry["hits"], [{"player": sim.pid(B), "damage": 1, "destroyed": False}])
        self.assertEqual((entry["row"], entry["col"]), (0, 2))

    def test_spray_misses_and_never_hurts_the_sprayer(self):
        sim = new_battle(2, tanks=[(0, 0), (4, 4)])
        sim.ok(A, {"action": "spray", "row": 3, "col": 3})  # covers (4, 4)
        self.assertEqual(sim.game.hp[sim.pid(B)], 4)
        sim.ok(B, {"action": "spray", "row": 0, "col": 0})  # B sprays A's square
        self.assertEqual(sim.game.hp[sim.pid(A)], 4)
        sim.game.queue.values[sim.pid(A)] = 0
        sim.ok(A, {"action": "spray", "row": 0, "col": 0})  # own square: no self damage
        self.assertEqual(sim.game.hp[sim.pid(A)], 4)
        self.assertEqual(public(sim, A)["log"][-1]["hits"], [])

    def test_spray_cost_is_a_setting(self):
        sim = new_battle(2, sprayCost=7, artilleryCost=9)
        self.assertEqual(cost_of(sim, A, {"action": "spray", "row": 3, "col": 3}), 7)
        sim.game.queue.values[sim.pid(A)] = 0
        self.assertEqual(cost_of(sim, A, {"action": "artillery", "row": 3, "col": 3}), 9)

    def test_artillery(self):
        sim = new_battle(2)
        sim.fails(A, {"action": "artillery", "row": 0, "col": SIZE}, "not a square")
        sim.fails(A, {"action": "artillery", "row": None, "col": 0}, "not a square")
        self.assertEqual(cost_of(sim, A, {"action": "artillery", "row": 0, "col": 3}), 3)
        self.assertEqual(sim.game.hp[sim.pid(B)], 3)
        entry = public(sim, B)["log"][-1]
        self.assertEqual(entry["hits"], [{"player": sim.pid(B), "damage": 2, "destroyed": False}])
        sim.game.queue.values[sim.pid(A)] = 0
        sim.ok(A, {"action": "artillery", "row": 0, "col": 0})  # your own square
        self.assertEqual(sim.game.hp[sim.pid(A)], 5)

    def test_artillery_hits_every_tank_on_a_square(self):
        sim = new_battle(3, tanks=[(0, 0), (2, 2), (2, 2)])
        sim.ok(A, {"action": "artillery", "row": 2, "col": 2})
        self.assertEqual((sim.game.hp[sim.pid(B)], sim.game.hp[sim.pid(C)]), (3, 3))

    def test_blast_hit(self):
        sim = new_battle(3, tanks=[(0, 0), (0, 3), (0, 5)])
        self.assertEqual(cost_of(sim, A, {"action": "blast", "dir": "right"}), 5)
        entry = public(sim, C)["log"][-1]
        self.assertEqual(entry["hit"], [0, 3])  # the first tank on the line, not the one behind it
        self.assertEqual(entry["hits"], [{"player": sim.pid(B), "damage": 4, "destroyed": False}])
        self.assertEqual((sim.game.hp[sim.pid(B)], sim.game.hp[sim.pid(C)]), (1, 5))
        self.assertNotIn("dir", entry)
        self.assertEqual(sim.game.notes[sim.pid(A)][1], {"dir": "right"})

    def test_blast_all_directions_and_stacked_tanks(self):
        sim = new_battle(3, tanks=[(2, 2), (2, 5), (2, 5)], hp=10)
        for direction, target in (("right", (2, 5)), ("up", None), ("left", None), ("down", None)):
            sim.game.queue.values[sim.pid(A)] = 0
            sim.ok(A, {"action": "blast", "dir": direction})
            self.assertEqual(sim.game.log[-1]["hit"], list(target) if target else None, direction)
        self.assertEqual((sim.game.hp[sim.pid(B)], sim.game.hp[sim.pid(C)]), (6, 6))  # both tanks on the square

    def test_blast_miss_reveals_nothing_publicly(self):
        sim = new_battle(2)
        sim.ok(A, {"action": "blast", "dir": "down"})
        entry = public(sim, B)["log"][-1]
        self.assertEqual(entry, {"type": "blast", "actor": sim.pid(A), "cost": 5, "hit": None, "hits": []})
        self.assertEqual(sim.state(B)["private"]["notes"], {})
        self.assertEqual(sim.state(A)["private"]["notes"], {"1": {"dir": "down"}})
        self.assertEqual(sim.game.notes[sim.pid(A)], {1: {"dir": "down"}})
        self.assertEqual(sim.game.hp[sim.pid(B)], 5)

    def test_blast_is_stopped_by_walls_and_the_edge(self):
        sim = new_battle(2)  # A (0,0), B (0,3)
        sim.game.walls = {((0, 1), (0, 2))}
        sim.ok(A, {"action": "blast", "dir": "right"})
        self.assertIsNone(sim.game.log[-1]["hit"])
        self.assertEqual(sim.game.hp[sim.pid(B)], 5)
        sim.game.walls = set()
        sim.game.queue.values[sim.pid(A)] = 0
        sim.ok(A, {"action": "blast", "dir": "up"})  # straight off the board
        self.assertIsNone(sim.game.log[-1]["hit"])

    def test_blast_validation(self):
        sim = new_battle(2)
        for bad in ("north", None, ["up"], 1):
            sim.fails(A, {"action": "blast", "dir": bad}, "Blast up, down, left or right.")
        self.assertEqual(sim.game.log, [{"type": "start"}])

    def test_move(self):
        sim = new_battle(2)
        self.assertEqual(cost_of(sim, A, {"action": "move", "row": 1, "col": 0}), 1)
        self.assertEqual(sim.game.locations[sim.pid(A)], [1, 0])
        self.assertEqual(public(sim, B)["log"][-1], {"type": "move", "actor": sim.pid(A), "cost": 1})
        self.assertEqual(sim.state(A)["private"]["location"], [1, 0])

    def test_move_validation(self):
        sim = new_battle(2)  # A (0,0)
        sim.fails(A, {"action": "move", "row": 1, "col": 1}, "one square")
        sim.fails(A, {"action": "move", "row": 0, "col": 2}, "one square")
        sim.fails(A, {"action": "move", "row": 0, "col": 0}, "one square")
        sim.fails(A, {"action": "move", "row": -1, "col": 0}, "not a square")
        sim.fails(A, {"action": "move", "row": 0}, "not a square")
        sim.game.walls = {((0, 0), (0, 1))}
        sim.fails(A, {"action": "move", "row": 0, "col": 1}, "wall is in the way")
        sim.ok(A, {"action": "move", "row": 1, "col": 0})
        self.assertEqual(sim.game.locations[sim.pid(A)], [1, 0])

    def test_heal(self):
        sim = new_battle(2)
        sim.fails(A, {"action": "heal"}, "full HP")
        sim.game.hp[sim.pid(A)] = 3
        self.assertEqual(cost_of(sim, A, {"action": "heal"}), 3)
        self.assertEqual(sim.game.hp[sim.pid(A)], 4)
        self.assertEqual(public(sim, B)["log"][-1]["amount"], 1)
        sim.game.queue.values[sim.pid(A)] = 0
        sim.ok(A, {"action": "heal"})
        self.assertEqual(sim.game.hp[sim.pid(A)], 5)
        sim.game.queue.values[sim.pid(A)] = 0
        sim.fails(A, {"action": "heal"}, "full HP")

    def test_build_and_remove_walls(self):
        sim = new_battle(2)
        self.assertEqual(cost_of(sim, A, {"action": "wall", "cells": [[1, 1], [1, 2]]}), 1)
        self.assertEqual(public(sim, B)["walls"], [[1, 1, 1, 2]])
        sim.game.queue.values[sim.pid(A)] = 0
        sim.fails(A, {"action": "wall", "cells": [[1, 2], [1, 1]]}, "already a wall")  # order doesn't matter
        self.assertEqual(cost_of(sim, A, {"action": "unwall", "cells": [[1, 2], [1, 1]]}), 2)
        self.assertEqual(public(sim, B)["walls"], [])
        sim.game.queue.values[sim.pid(A)] = 0
        sim.fails(A, {"action": "unwall", "cells": [[1, 1], [1, 2]]}, "no wall there")

    def test_wall_validation(self):
        sim = new_battle(2)
        sim.fails(A, {"action": "wall", "cells": [[0, 0], [1, 1]]}, "neighboring")
        sim.fails(A, {"action": "wall", "cells": [[0, 0], [0, 0]]}, "neighboring")
        sim.fails(A, {"action": "wall", "cells": [[0, 0]]}, "neighboring")
        sim.fails(A, {"action": "wall", "cells": "x"}, "neighboring")
        sim.fails(A, {"action": "wall", "cells": [[0, 0], [0, SIZE]]}, "not a square")
        sim.fails(A, {"action": "unwall", "cells": [[0, 0], [2, 0]]}, "neighboring")
        self.assertEqual(sim.game.walls, set())

    def test_walls_may_not_split_the_board(self):
        sim = new_battle(2, size=4, tanks=[(0, 0), (3, 3)])
        sim.ok(A, {"action": "wall", "cells": [[0, 0], [0, 1]]})
        sim.game.queue.values[sim.pid(A)] = 0
        sim.fails(A, {"action": "wall", "cells": [[0, 0], [1, 0]]}, "cut the board in two")
        self.assertEqual(len(sim.game.walls), 1)

    def test_mine(self):
        sim = new_battle(2)  # A (0,0)
        self.assertEqual(cost_of(sim, A, {"action": "mine", "row": 0, "col": 3}), 1)  # exactly 3 steps
        self.assertEqual(sim.state(A)["private"]["mines"], [[0, 3]])
        self.assertEqual(sim.state(B)["private"]["mines"], [])
        self.assertEqual(public(sim, B)["log"][-1], {"type": "mine", "actor": sim.pid(A), "cost": 1})
        self.assertEqual(sim.state(A)["private"]["notes"], {"1": {"cell": [0, 3]}})
        self.assertEqual(sim.state(B)["private"]["notes"], {})

    def test_mine_range_follows_walls(self):
        sim = new_battle(2)
        sim.game.queue.values[sim.pid(A)] = 0
        sim.fails(A, {"action": "mine", "row": 0, "col": 4}, "at most 3 steps")
        sim.fails(A, {"action": "mine", "row": 2, "col": 2}, "at most 3 steps")  # 4 steps away
        sim.fails(A, {"action": "mine", "row": 9, "col": 0}, "not a square")
        sim.game.walls = {((0, 1), (0, 2))}  # A can't walk straight along the top row
        sim.fails(A, {"action": "mine", "row": 0, "col": 3}, "at most 3 steps")  # detour is 5 steps
        sim.game.walls = {((0, 0), (0, 1))}
        sim.ok(A, {"action": "mine", "row": 1, "col": 1})
        sim.game.queue.values[sim.pid(A)] = 0
        sim.fails(A, {"action": "mine", "row": 0, "col": 2}, "at most 3 steps")  # via (1,0),(1,1),(1,2),(0,2) = 4

    def test_mine_on_your_own_square_does_nothing(self):
        sim = new_battle(2)
        sim.ok(A, {"action": "mine", "row": 0, "col": 0})
        self.assertEqual(sim.game.hp[sim.pid(A)], 5)
        self.assertEqual(public(sim, A)["log"][-1]["type"], "mine")

    def test_action_costs_table(self):
        sim = new_battle(2, hp=10)
        sim.game.hp[sim.pid(A)] = 5
        costs = {}
        for name, action in (
            ("move", {"action": "move", "row": 1, "col": 0}),
            ("blast", {"action": "blast", "dir": "down"}),
            ("heal", {"action": "heal"}),
            ("wall", {"action": "wall", "cells": [[3, 3], [3, 4]]}),
            ("unwall", {"action": "unwall", "cells": [[3, 3], [3, 4]]}),
            ("mine", {"action": "mine", "row": 1, "col": 1}),
        ):
            sim.game.queue.values[sim.pid(A)] = 0
            costs[name] = cost_of(sim, A, action)
        self.assertEqual(costs, {"move": 1, "blast": 5, "heal": 3, "wall": 1, "unwall": 2, "mine": 1})
        self.assertEqual(public(sim, A)["costs"]["move"], 1)


class ShieldTests(unittest.TestCase):
    def setUp(self):
        # Order A (1), B (2), C (3). A hits C, then B (acting before C) hits C again.
        self.sim = new_battle(3, tanks=[(0, 0), (0, 3), (4, 4)])

    def test_damage_shields_until_the_tanks_next_turn(self):
        sim = self.sim
        sim.ok(A, {"action": "artillery", "row": 4, "col": 4})  # A = 4, C takes 2
        self.assertEqual(sim.game.hp[sim.pid(C)], 3)
        self.assertTrue(player(sim, A, C)["shielded"])
        self.assertEqual(public(sim, A)["current"], sim.pid(B))
        sim.ok(B, {"action": "artillery", "row": 4, "col": 4})  # shielded: no damage
        self.assertEqual(sim.game.hp[sim.pid(C)], 3)
        hit = public(sim, A)["log"][-1]["hits"]
        self.assertEqual(hit, [{"player": sim.pid(C), "damage": 0, "destroyed": False, "shielded": True}])
        # B = 5; C (3) is next, and its shield is gone as its turn starts.
        self.assertEqual(public(sim, A)["current"], sim.pid(C))
        self.assertFalse(player(sim, A, C)["shielded"])

    def test_a_shielded_tank_still_stops_a_blast(self):
        sim = self.sim
        sim.game.locations[sim.pid(C)] = [0, 5]
        sim.ok(A, {"action": "artillery", "row": 0, "col": 5})  # shield C
        sim.ok(B, {"action": "blast", "dir": "right"})
        entry = public(sim, A)["log"][-1]
        self.assertEqual(entry["hit"], [0, 5])
        self.assertEqual(entry["hits"][0]["shielded"], True)
        self.assertEqual(sim.game.hp[sim.pid(C)], 3)

    def test_mines_respect_shields(self):
        sim = self.sim
        sim.game.mines = [{"owner": sim.pid(B), "row": 4, "col": 3}]
        sim.game.locations[sim.pid(C)] = [4, 3]
        sim.game.locations[sim.pid(A)] = [4, 2]
        sim.game.shielded = {sim.pid(C)}
        sim.ok(A, {"action": "move", "row": 4, "col": 3})  # A walks onto the mine, with C also there
        entry = public(sim, A)["log"][-1]
        by_player = {h["player"]: h for h in entry["hits"]}
        self.assertEqual(by_player[sim.pid(C)]["damage"], 0)  # shielded
        self.assertEqual(by_player[sim.pid(A)]["damage"], 1)
        self.assertEqual((sim.game.hp[sim.pid(A)], sim.game.hp[sim.pid(C)]), (4, 5))

    def test_hits_after_the_shield_ends_count(self):
        sim = self.sim
        sim.ok(A, {"action": "spray", "row": 3, "col": 3})  # C (4,4) takes 1
        sim.ok(B, {"action": "move", "row": 1, "col": 3})
        sim.ok(C, {"action": "move", "row": 4, "col": 3})  # C's turn started: shield gone
        sim.game.queue.values[sim.pid(A)] = 0
        sim.ok(A, {"action": "artillery", "row": 4, "col": 3})
        self.assertEqual(sim.game.hp[sim.pid(C)], 2)


class MineTests(unittest.TestCase):
    def test_walking_onto_a_mine_sets_it_off(self):
        sim = new_battle(2)  # A (0,0)
        sim.game.mines = [{"owner": sim.pid(B), "row": 0, "col": 1}]
        self.assertEqual(cost_of(sim, A, {"action": "move", "row": 0, "col": 1}), 1)
        self.assertEqual(sim.game.mines, [])
        self.assertEqual(sim.game.hp[sim.pid(A)], 4)
        entry = public(sim, B)["log"][-1]
        self.assertTrue(entry["mine"])
        self.assertEqual(entry["hits"], [{"player": sim.pid(A), "damage": 1, "destroyed": False}])
        self.assertNotIn("row", entry)  # the square stays hidden from everyone but the mine's owner
        self.assertEqual(sim.state(B)["private"]["notes"], {"1": {"mineAt": [0, 1]}})
        self.assertEqual(sim.state(A)["private"]["notes"], {})
        self.assertEqual(sim.state(B)["private"]["mines"], [])

    def test_a_mine_hits_every_tank_on_the_square_once(self):
        sim = new_battle(3, tanks=[(0, 0), (0, 1), (0, 1)])
        sim.game.mines = [
            {"owner": sim.pid(B), "row": 0, "col": 1},
            {"owner": sim.pid(C), "row": 0, "col": 1},
        ]
        sim.ok(A, {"action": "move", "row": 0, "col": 1})
        self.assertEqual(sim.game.mines, [])  # all mines there are used up
        self.assertEqual([sim.game.hp[sim.pid(i)] for i in (A, B, C)], [4, 4, 4])
        self.assertEqual(sim.game.notes[sim.pid(B)], {1: {"mineAt": [0, 1]}})
        self.assertEqual(sim.game.notes[sim.pid(C)], {1: {"mineAt": [0, 1]}})

    def test_your_own_mine_goes_off_too(self):
        sim = new_battle(2)
        sim.game.mines = [{"owner": sim.pid(A), "row": 0, "col": 1}]
        sim.ok(A, {"action": "move", "row": 0, "col": 1})
        self.assertEqual(sim.game.hp[sim.pid(A)], 4)
        self.assertEqual(sim.state(A)["private"]["mines"], [])
        self.assertEqual(sim.state(A)["private"]["notes"], {"1": {"mineAt": [0, 1]}})

    def test_mines_elsewhere_stay_and_starting_on_a_mine_is_safe(self):
        sim = new_battle(2)
        sim.game.mines = [{"owner": sim.pid(B), "row": 0, "col": 0}, {"owner": sim.pid(B), "row": 3, "col": 3}]
        sim.ok(A, {"action": "scan", "axis": "row", "from": 0, "to": 5})
        self.assertEqual(sim.game.hp[sim.pid(A)], 5)  # standing on a mine does nothing
        sim.game.queue.values[sim.pid(A)] = 0
        sim.ok(A, {"action": "move", "row": 0, "col": 1})  # leaving it doesn't set it off either
        self.assertEqual(len(sim.game.mines), 2)

    def test_artillery_does_not_set_off_mines(self):
        sim = new_battle(2, tanks=[(0, 0), (0, 3)])
        sim.game.mines = [{"owner": sim.pid(A), "row": 0, "col": 3}]
        sim.ok(A, {"action": "artillery", "row": 0, "col": 3})
        self.assertEqual(len(sim.game.mines), 1)  # only walking onto a mine sets it off
        self.assertEqual(sim.game.hp[sim.pid(B)], 3)

    def test_player_destroyed_by_their_own_move_ends_the_game_for_two(self):
        sim = new_battle(2, hp=1)
        sim.game.mines = [{"owner": sim.pid(B), "row": 0, "col": 1}]
        sim.ok(A, {"action": "move", "row": 0, "col": 1})
        self.assertEqual(sim.game.phase, "finished")
        result = sim.state(B)["result"]
        self.assertEqual(result, {"winner": sim.pid(B), "reason": None})
        self.assertNotIn(sim.pid(A), sim.game.queue)
        self.assertFalse(player(sim, B, A)["alive"])
        self.assertEqual(player(sim, B, A)["hp"], 0)
        self.assertEqual(public(sim, B)["locations"][sim.pid(A)], [0, 1])  # revealed at the end

    def test_everyone_destroyed_at_once_has_no_winner(self):
        sim = new_battle(2, tanks=[(0, 0), (0, 1)], hp=1)
        sim.game.mines = [{"owner": sim.pid(B), "row": 0, "col": 1}]
        sim.ok(A, {"action": "move", "row": 0, "col": 1})  # B stands on its own mine's square
        self.assertEqual(sim.game.phase, "finished")
        self.assertEqual(sim.state(A)["result"], {"winner": None, "reason": "No tanks are left."})
        self.assertEqual(public(sim, A)["current"], None)

    def test_destroyed_in_a_bigger_game_the_rest_play_on(self):
        sim = new_battle(3, hp=1)
        sim.game.mines = [{"owner": sim.pid(B), "row": 0, "col": 1}]
        sim.ok(A, {"action": "move", "row": 0, "col": 1})
        self.assertEqual(sim.game.phase, "playing")
        self.assertEqual(public(sim, B)["current"], sim.pid(B))
        self.assertEqual([p["id"] for p in public(sim, B)["players"]][-1], sim.pid(A))  # the dead go last
        sim.fails(A, {"action": "heal"}, "destroyed")
        sim.fails(A, {"action": "place", "row": 0, "col": 0, "mines": []}, "destroyed")


class GameEndTests(unittest.TestCase):
    def test_last_tank_standing_wins(self):
        sim = new_battle(3, hp=2)
        sim.ok(A, {"action": "artillery", "row": 0, "col": 3})  # B destroyed
        self.assertEqual(sim.game.phase, "playing")
        self.assertFalse(player(sim, A, B)["alive"])
        self.assertEqual(public(sim, A)["current"], sim.pid(C))
        sim.fails(B, {"action": "heal"}, "destroyed")
        sim.ok(C, {"action": "artillery", "row": 0, "col": 0})  # A destroyed
        self.assertEqual(sim.game.phase, "finished")
        self.assertEqual(sim.state(B)["result"], {"winner": sim.pid(C), "reason": None})
        self.assertIsNone(public(sim, B)["current"])
        sim.fails(C, {"action": "heal"}, "not playing")

    def test_a_blast_can_win(self):
        sim = new_battle(2, hp=4)
        sim.ok(A, {"action": "blast", "dir": "right"})
        self.assertEqual(sim.state(A)["result"]["winner"], sim.pid(A))
        self.assertEqual(public(sim, A)["log"][-1]["hits"][0]["destroyed"], True)

    def test_back_to_the_lobby_and_a_new_game(self):
        sim = new_battle(2, hp=1)
        sim.ok(A, {"action": "artillery", "row": 0, "col": 3})
        sim.lobby(A, {"type": "back_to_lobby"})
        self.assertEqual(sim.game.phase, "lobby")
        self.assertEqual((sim.game.locations, sim.game.mines, sim.game.log), ({}, [], []))
        sim.start()
        self.assertEqual(public(sim, A)["stage"], "placing")
        self.assertEqual(sim.state(A)["private"], {"location": None, "mines": [], "notes": {}})
        self.assertEqual(public(sim, A)["log"], [])
        self.assertEqual({p["hp"] for p in public(sim, A)["players"]}, {1})


class LeavingTests(unittest.TestCase):
    def test_leaving_one_of_three_continues(self):
        sim = new_battle(3)
        sim.leave(B)
        self.assertEqual(sim.game.phase, "playing")
        self.assertNotIn(sim.pid(B), sim.game.queue)
        self.assertEqual(public(sim, A)["log"][-1], {"type": "left", "actor": sim.pid(B)})
        self.assertFalse(player(sim, A, B)["alive"])
        sim.fails(B, {"action": "heal"}, "not playing")
        sim.ok(A, {"action": "move", "row": 1, "col": 0})  # A = 2, C = 3
        self.assertEqual(public(sim, A)["current"], sim.pid(A))
        sim.ok(A, {"action": "move", "row": 1, "col": 1})  # A = 3, C reached 3 first
        self.assertEqual(public(sim, A)["current"], sim.pid(C))

    def test_the_current_player_leaving_passes_the_turn(self):
        sim = new_battle(3)
        sim.game.shielded.add(sim.pid(B))
        sim.leave(A)
        self.assertEqual(public(sim, B)["current"], sim.pid(B))
        self.assertEqual(sim.game.shielded, set())  # B's turn started: its shield drops

    def test_the_last_player_left_wins(self):
        sim = new_battle(2)
        sim.leave(B)
        self.assertEqual(sim.state(A)["result"], {"winner": sim.pid(A), "reason": "Everyone else left."})
        self.assertEqual(sim.game.phase, "finished")

    def test_leaving_while_placing_can_start_the_battle(self):
        sim = Sim("tanks", players=3, settings={"boardSize": SIZE, "wallChance": 0})
        place(sim, A, 0, 0, [[1, 1], [2, 2]])
        place(sim, B, 0, 3, [[1, 1], [2, 2]])
        self.assertEqual(sim.game.stage, "placing")
        sim.leave(C)  # the one everyone was waiting for
        self.assertEqual(sim.game.stage, "action")
        self.assertEqual(public(sim, A)["log"][-2:], [{"type": "left", "actor": sim.pid(C)}, {"type": "start"}])
        self.assertIn(public(sim, A)["current"], (sim.pid(A), sim.pid(B)))

    def test_leaving_while_placing_down_to_one(self):
        sim = Sim("tanks", players=2, settings={"boardSize": SIZE, "wallChance": 0})
        sim.leave(B)
        self.assertEqual(sim.state(A)["result"]["winner"], sim.pid(A))

    def test_a_destroyed_player_leaving_changes_nothing(self):
        sim = new_battle(3, hp=1)
        sim.ok(A, {"action": "artillery", "row": 0, "col": 3})  # B destroyed
        log_length = len(sim.game.log)
        sim.leave(B)
        self.assertEqual(len(sim.game.log), log_length)
        self.assertEqual(sim.game.phase, "playing")

    def test_a_leaving_players_mines_stay_on_the_board(self):
        sim = new_battle(3)
        sim.game.mines = [{"owner": sim.pid(C), "row": 0, "col": 1}]
        sim.leave(C)
        sim.ok(A, {"action": "move", "row": 0, "col": 1})
        self.assertEqual(sim.game.hp[sim.pid(A)], 4)  # the owner is gone; no note to write, no crash


if __name__ == "__main__":
    unittest.main()
