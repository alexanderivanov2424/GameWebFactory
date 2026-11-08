"""Deep Colony: machine and network unit tests (power, pipes, air, food, toilets).
Run: cd APP && python3 -B -m unittest discover -s games/deep-colony/tests -p test_machines.py
"""

import importlib
import types
import unittest

machines = importlib.import_module("games.deep-colony.logic.machines")
content = importlib.import_module("games.deep-colony.logic.content")
Match = importlib.import_module("games.deep-colony.logic.match").Match

FLOOR_Y = 15  # sandstone row; buildings stand on row 14


def new_match():
    m = Match.blank(30, 20, "oxygen")
    for x in range(30):
        m.world.set_cell(m.world.idx(x, FLOOR_Y), "sandstone", 1000, 20)
    return m


def put(m, kind, x, y_bottom=14, **state):
    """Place a finished building so its bottom row is y_bottom."""
    d = content.BUILDINGS[kind]
    b = m.buildings.place(kind, x, y_bottom - d["h"] + 1, "p1", built=True)
    b.state.update(state)
    return b


def thin(m, x, y):
    """Make the gas at a cell thin enough that machines emitting there are not 'full'."""
    m.world.mass[m.world.idx(x, y)] = 1.0


def ports(m, b, kind="liquid_pipe"):
    """A pipe (or wire) on each of a building's pipe ports (separate networks unless they touch)."""
    wires(m, [b.port_cell(k) for k in ("pipeIn", "pipeOut") if b.port_cell(k)], kind)


def wires(m, cells, kind="wire"):
    for x, y in cells:
        m.buildings.place(kind, x, y, "p1", built=True)


def run(m, steps=5, dt=0.1, operate=()):
    for _ in range(steps):
        for g in operate:
            g.state["operated_at"] = m.time
        m.networks.step(dt)
        machines.step(m, dt)


def dupe():
    return types.SimpleNamespace(bladder=100, germs=0, needs_wash=False)


class PowerTests(unittest.TestCase):
    def test_generator_powers_same_network_only(self):
        m = new_match()
        gen = put(m, "manual_generator", 2)           # port cell (3, 13)
        near = put(m, "algae_oxygenator", 6, algae=0)  # port cell (6, 13)
        far = put(m, "algae_oxygenator", 10)
        near.store["algae"] = far.store["algae"] = 50
        thin(m, 6, 13)
        wires(m, [(3, 14), (4, 14), (5, 14), (6, 14)])
        run(m, 6, operate=[gen])
        self.assertTrue(near.powered)
        self.assertFalse(far.powered)
        self.assertLess(near.store["algae"], 50)
        self.assertEqual(far.store["algae"], 50)
        summary = m.networks.power_summary()
        self.assertEqual(len(summary), 1)
        self.assertGreater(list(summary.values())[0]["gen"], 0)

    def test_battery_charges_from_surplus_and_covers_shortfall(self):
        m = new_match()
        gen = put(m, "manual_generator", 2)
        bat = put(m, "battery", 5)  # port (5, 14)... bottom cell
        wires(m, [(3, 14), (4, 14), (5, 14)])
        run(m, 10, operate=[gen])
        charged = bat.state["charge"]
        self.assertGreater(charged, 0)
        user = put(m, "algae_oxygenator", 7)
        user.store["algae"] = 50
        thin(m, 7, 13)
        wires(m, [(6, 14), (7, 14)])
        gen.state["operated_at"] = -1000.0  # generator stops
        run(m, 10)
        self.assertTrue(user.powered)
        self.assertLess(bat.state["charge"], charged)
        self.assertTrue(m.networks.needs_power(bat) or bat.state["charge"] >= 0)

    def test_unpowered_when_no_supply(self):
        m = new_match()
        user = put(m, "algae_oxygenator", 6)
        user.store["algae"] = 50
        wires(m, [(6, 14)])
        run(m, 5)
        self.assertFalse(user.powered)
        self.assertEqual(user.status, "No power")
        self.assertTrue(m.networks.needs_power(user))


class AirTests(unittest.TestCase):
    def setUp(self):
        self.m = new_match()
        self.w = self.m.world
        self.gen = put(self.m, "manual_generator", 2)
        self.ox = put(self.m, "algae_oxygenator", 6)
        self.ox.store["algae"] = 50
        wires(self.m, [(3, 14), (4, 14), (5, 14), (6, 14)])
        self.top = self.w.idx(6, 13)
        self.w.mass[self.top] = 1.0

    def test_oxygenator_adds_oxygen_and_uses_algae(self):
        run(self.m, 10, operate=[self.gen])
        self.assertGreater(self.w.mass[self.top], 1.0)
        self.assertLess(self.ox.store["algae"], 50)

    def test_oxygenator_without_power_does_nothing(self):
        run(self.m, 10)
        self.assertEqual(self.w.mass[self.top], 1.0)
        self.assertEqual(self.ox.store["algae"], 50)

    def test_disabled_machine_does_nothing(self):
        self.ox.enabled = False
        run(self.m, 10, operate=[self.gen])
        self.assertEqual(self.w.mass[self.top], 1.0)
        self.assertEqual(self.ox.store["algae"], 50)
        self.assertEqual(self.ox.status, "Disabled")

    def test_deodorizer_cleans_polluted_oxygen_using_sand(self):
        dz = put(self.m, "deodorizer", 20)
        dz.store["sand"] = 20
        i = self.w.idx(21, 13)
        self.w.set_cell(i, "polluted_oxygen", 1.5, 20)
        run(self.m, 20)
        self.assertEqual(self.w.element_id(i), "oxygen")
        self.assertLess(dz.store["sand"], 20)


def total(m, el):
    """kg of an element in the world cells, waiting in world.pending and travelling in pipes."""
    w = m.world
    n = sum(w.mass[i] for i in range(w.w * w.h) if w.element_id(i) == el)
    n += sum(p[3] for p in w.pending if p[2] == el)
    n += sum(pk[1] for kind in m.networks._pk.values() for pk in kind.values() if pk[0] == el)
    return n


class PipeTests(unittest.TestCase):
    def pump_line(self, m, pipe_kind="liquid_pipe", pump_kind="liquid_pump", vent_kind="liquid_vent"):
        gen = put(m, "manual_generator", 6)  # port (7, 13)
        pump = put(m, pump_kind, 2)          # power port (3, 13), out port (2, 13)
        wires(m, [(3, 13), (4, 13), (5, 13), (6, 13), (7, 13), (7, 14)])
        wires(m, [(2, 13), (2, 12), (2, 11), (2, 10), (2, 9)], pipe_kind)
        vent = put(m, vent_kind, 2, 9)
        return gen, pump, vent

    def test_packet_travels_from_pump_to_vent(self):
        m = new_match()
        w = m.world
        gen, pump, vent = self.pump_line(m)
        pool = w.idx(2, 14)
        w.set_cell(pool, "water", 50, 20)
        run(m, 4, operate=[gen])
        self.assertTrue(m.networks.pipe_summary())  # something is in the pipe already
        vi = w.idx(2, 9)
        self.assertNotEqual(w.element_id(vi), "water")  # but has not arrived yet
        before = total(m, "water")
        run(m, 40, operate=[gen])
        self.assertEqual(w.element_id(vi), "water")
        self.assertGreater(w.mass[vi], 1)
        self.assertLess(w.mass[pool], 50)
        self.assertAlmostEqual(total(m, "water"), before, places=3)

    def test_unattached_ports_do_nothing(self):
        m = new_match()
        vent = put(m, "liquid_vent", 2, 9)
        self.assertEqual(m.networks.pipe_take(vent, "pipeIn", None, 1), (None, 0, 0, 0))
        self.assertEqual(m.networks.pipe_put(vent, "pipeIn", "water", 1, 20, 0), 0)

    def test_segment_holds_one_element_up_to_capacity(self):
        m = new_match()
        wires(m, [(2, 9), (3, 9)], "liquid_pipe")
        vent = put(m, "liquid_vent", 2, 9)
        nets = m.networks
        got = nets.pipe_put(vent, "pipeIn", "water", 1000, 10, 100)
        self.assertGreater(got, 0)
        self.assertLess(got, 1000)
        self.assertEqual(nets.pipe_room(vent, "pipeIn"), 0)
        self.assertEqual(nets.pipe_put(vent, "pipeIn", "water", 1, 10, 0), 0)
        el, kg, temp, germs = nets.pipe_take(vent, "pipeIn", ["water"], 1)
        self.assertEqual((el, kg, temp), ("water", 1, 10))
        self.assertGreater(germs, 0)
        self.assertEqual(nets.pipe_take(vent, "pipeIn", ["oxygen"], 1)[1], 0)
        self.assertEqual(nets.pipe_put(vent, "pipeIn", "oxygen", 1, 10, 0), 0)  # another element: blocked
        self.assertEqual(nets.pipe_room(vent, "pipeIn", "oxygen"), 0)

    def test_wrong_element_at_a_consumer_blocks_it(self):
        m = new_match()
        pump = put(m, "liquid_pump", 2)   # out port (2, 13)
        lav = put(m, "lavatory", 5)       # in port (5, 14)
        route = [(2, 13), (2, 12), (3, 12), (4, 12), (4, 13), (4, 14), (5, 14)]
        wires(m, route, "liquid_pipe")
        nets = m.networks
        nets.pipe_put(lav, "pipeIn", "polluted_water", 1, 20, 0)
        nets.pipe_put(pump, "pipeOut", "water", 5, 20, 0)
        run(m, 60)
        self.assertEqual(nets.pipe_has(lav, "pipeIn", "water"), 0)
        self.assertAlmostEqual(nets.pipe_has(lav, "pipeIn", "polluted_water"), 1, places=3)
        stuck = m.networks.pipe_summary()[str(m.world.idx(4, 14))]
        self.assertEqual(stuck["el"], "water")
        self.assertFalse(machines.toilet_usable(m, lav))

    def test_same_element_packets_merge_in_a_segment(self):
        m = new_match()
        pump = put(m, "liquid_pump", 2)
        vent = put(m, "liquid_vent", 2, 9)
        wires(m, [(2, 13), (2, 12), (2, 11), (2, 10), (2, 9)], "liquid_pipe")
        m.networks.pipe_put(pump, "pipeOut", "water", 3, 20, 0)
        for _ in range(3):
            run(m, 2)
            m.networks.pipe_put(pump, "pipeOut", "water", 2, 20, 0)
        run(m, 20)
        self.assertEqual(len(m.networks.pipe_summary()), 0)  # all of it reached the vent
        self.assertEqual(m.world.element_id(m.world.idx(2, 9)), "water")

    def test_gas_pump_pipe_vent_moves_gas(self):
        m = new_match()
        w = m.world
        gen, pump, vent = self.pump_line(m, "gas_pipe", "gas_pump", "gas_vent")
        thin(m, 2, 9)
        vi = w.idx(2, 9)
        before, here = total(m, "oxygen"), w.mass[vi]
        run(m, 4, operate=[gen])
        self.assertTrue(m.networks.gas_summary())
        self.assertEqual(m.networks.pipe_summary(), {})
        run(m, 60, operate=[gen])
        self.assertGreater(w.mass[vi], here + 0.3)
        self.assertAlmostEqual(total(m, "oxygen"), before, places=3)

    def test_gas_vent_stops_at_max_pressure(self):
        m = new_match()
        wires(m, [(2, 9), (2, 10)], "gas_pipe")
        vent = put(m, "gas_vent", 2, 9)
        m.world.mass[m.world.idx(2, 9)] = vent.d["params"]["maxPressure"] + 1
        m.networks.pipe_put(vent, "gasIn", "oxygen", 0.5, 20, 0)
        run(m, 10)
        self.assertAlmostEqual(m.networks.pipe_has(vent, "gasIn", "oxygen"), 0.5, places=3)

    def test_hydrogen_generator_powers_from_piped_hydrogen(self):
        m = new_match()
        gen = put(m, "hydrogen_generator", 2)  # gas in (2, 14), power port (3, 14)
        user = put(m, "algae_oxygenator", 6)   # power port (6, 14)
        user.store["algae"] = 50
        thin(m, 6, 13)
        wires(m, [(3, 14), (4, 14), (5, 14), (6, 14)])
        wires(m, [(2, 14)], "gas_pipe")
        run(m, 5)
        self.assertFalse(user.powered)
        self.assertEqual(gen.status, "No hydrogen")
        m.networks.pipe_put(gen, "gasIn", "hydrogen", 1.0, 20, 0)
        run(m, 10)
        self.assertTrue(gen.state["producing"])
        self.assertTrue(user.powered)
        self.assertLess(m.networks.pipe_has(gen, "gasIn", "hydrogen"), 1.0)
        self.assertLess(user.store["algae"], 50)

    def test_removed_segment_releases_its_contents(self):
        m = new_match()
        wires(m, [(2, 9), (3, 9), (4, 9)], "liquid_pipe")
        vent = put(m, "liquid_vent", 4, 9)
        m.networks.pipe_put(vent, "pipeIn", "water", 5, 20, 40)
        m.networks.step(0)
        before = total(m, "water")
        self.assertAlmostEqual(before, 5, places=3)
        seg = m.buildings.at(4, 9, "pipe")
        m.buildings.remove(seg)
        m.networks.step(0)
        self.assertEqual(m.networks.pipe_summary(), {})
        self.assertAlmostEqual(total(m, "water"), before, places=3)
        self.assertGreater(m.world.mass[m.world.idx(4, 9)], 4)

    def test_rotated_pump_ports_and_operation(self):
        m = new_match()
        w = m.world
        gen = put(m, "manual_generator", 6)
        pump = m.buildings.place("liquid_pump", 2, 13, "p1", built=True, rot=1)
        out, power = pump.port_cell("pipeOut"), pump.port_cell("powerPort")
        self.assertNotEqual(out, content.BUILDINGS["liquid_pump"]["pipeOut"])
        wires(m, [power, (3, 13), (4, 13), (5, 13), (6, 13), (7, 13), (7, 14)])
        wires(m, [out], "liquid_pipe")
        w.set_cell(w.idx(2, 14), "water", 50, 20)
        run(m, 20, operate=[gen])
        self.assertGreater(m.networks.pipe_has(pump, "pipeOut", "water"), 0)
        self.assertIn(str(w.idx(*out)), m.networks.pipe_summary())
        self.assertLess(w.mass[w.idx(2, 14)], 50)


class FoodTests(unittest.TestCase):
    def test_fungus_grows_only_in_range_and_can_be_harvested(self):
        m = new_match()
        p = content.BUILDINGS["fungus_bed"]["params"]
        bed = put(m, "fungus_bed", 4)
        i = m.world.idx(4, 14)
        m.world.temp[i] = p["maxTemp"] + 20
        run(m, 5)
        self.assertEqual(bed.state.get("growth", 0), 0)
        self.assertFalse(machines.harvest_ready(bed))
        m.world.temp[i] = (p["minTemp"] + p["maxTemp"]) / 2
        run(m, 5)
        self.assertGreater(bed.state["growth"], 0)
        self.assertFalse(machines.harvest_ready(bed))
        machines.step(m, p["growTime"])
        self.assertTrue(machines.harvest_ready(bed))
        machines.harvest(m, bed)
        self.assertGreater(m.items.totals().get("fungus", 0), 0)
        self.assertFalse(machines.harvest_ready(bed))

    def test_nutrient_press_makes_food_when_operated(self):
        m = new_match()
        gen = put(m, "manual_generator", 6)
        press = put(m, "nutrient_press", 2)  # power (3, 13), pipe in (2, 14)
        p = press.d["params"]
        wires(m, [(3, 14), (4, 14), (5, 14), (6, 14), (7, 14)])
        wires(m, [(2, 14)], "liquid_pipe")
        press.store["dirt"] = p["dirt"] * 2
        m.networks.pipe_put(press, "pipeIn", "water", p["water"] * 2, 20, 0)
        run(m, 5, operate=[gen])
        self.assertTrue(machines.wants_operator(m, press))
        for _ in range(int(p["work"] / 0.1) + 5):
            run(m, 1, operate=[gen])
            machines.operate(m, press, dupe(), 0.1)
        self.assertGreater(m.items.totals().get(p["product"], 0), 0)
        self.assertLess(press.store["dirt"], p["dirt"] * 2)


class ToiletTests(unittest.TestCase):
    def test_outhouse_use_then_needs_emptying(self):
        m = new_match()
        oh = put(m, "outhouse", 4)
        p = oh.d["params"]
        d = dupe()
        self.assertFalse(machines.toilet_usable(m, oh))  # no dirt yet
        oh.store["dirt"] = p["dirtPerUse"] * p["uses"]
        self.assertTrue(machines.use_toilet(m, oh, d))
        self.assertEqual(d.bladder, 0)
        self.assertGreater(d.germs, 0)
        self.assertTrue(d.needs_wash)
        for _ in range(p["uses"] - 1):
            self.assertTrue(machines.use_toilet(m, oh, dupe()))
        self.assertTrue(machines.needs_emptying(oh))
        self.assertFalse(machines.toilet_usable(m, oh))
        self.assertFalse(machines.use_toilet(m, oh, dupe()))
        machines.empty(m, oh)
        self.assertFalse(machines.needs_emptying(oh))
        self.assertGreater(m.items.totals().get("polluted_dirt", 0), 0)

    def test_lavatory_uses_piped_water(self):
        m = new_match()
        lav = put(m, "lavatory", 4)
        ports(m, lav)
        self.assertFalse(machines.toilet_usable(m, lav))
        m.networks.pipe_put(lav, "pipeIn", "water", 10, 20, 0)
        d = dupe()
        self.assertTrue(machines.use_toilet(m, lav, d))
        self.assertEqual(d.bladder, 0)
        self.assertTrue(d.needs_wash)
        self.assertGreater(m.networks.pipe_has(lav, "pipeOut", "polluted_water"), 0)

    def test_wash_basin_removes_germs(self):
        m = new_match()
        basin = put(m, "wash_basin", 4)
        ports(m, basin)
        d = types.SimpleNamespace(bladder=0, germs=5000, needs_wash=True)
        self.assertFalse(machines.basin_usable(m, basin))
        m.networks.pipe_put(basin, "pipeIn", "water", 8, 20, 0)
        self.assertTrue(machines.basin_usable(m, basin))
        self.assertTrue(machines.wash(m, basin, d))
        self.assertEqual(d.germs, 0)
        self.assertFalse(d.needs_wash)
        self.assertGreater(m.networks.pipe_has(basin, "pipeOut", "polluted_water"), 0)


class BacklogTests(unittest.TestCase):
    def setUp(self):
        self.m = new_match()
        self.w = self.m.world
        self.gen = put(self.m, "manual_generator", 2)
        self.ox = put(self.m, "algae_oxygenator", 6)
        self.ox.store["algae"] = 50
        wires(self.m, [(3, 14), (4, 14), (5, 14), (6, 14)])
        # a sealed pocket: two cells, each a different gas, so oxygen has nowhere to go
        for i in range(self.w.w * self.w.h):
            if self.w.is_gas(i):
                self.w.set_cell(i, "sandstone", 1000, 20)
        self.w.set_cell(self.w.idx(6, 13), "carbon_dioxide", 1.0, 20)
        self.w.set_cell(self.w.idx(6, 14), "hydrogen", 1.0, 20)

    def test_output_with_no_room_is_kept_and_placed_later(self):
        run(self.m, 10, operate=[self.gen])
        p = self.ox.d["params"]
        backlog = self.ox.state["backlog"]
        kept = sum(e[1] for e in backlog)
        used = 50 - self.ox.store["algae"]
        self.assertGreater(kept, 0)
        self.assertAlmostEqual(kept, used * p["outRate"] / p["inRate"], places=6)
        self.assertEqual(self.ox.status, "Overpressure")
        self.assertEqual(total(self.m, "oxygen"), 0)
        run(self.m, 10, operate=[self.gen])  # blocked: consumes nothing more
        self.assertAlmostEqual(50 - self.ox.store["algae"], used, places=6)
        self.w.set_cell(self.w.idx(6, 14), "vacuum", 0, 20)
        run(self.m, 1, operate=[self.gen])
        self.assertNotIn("backlog", self.ox.state)
        self.assertGreaterEqual(total(self.m, "oxygen"), kept - 1e-6)
        run(self.m, 10, operate=[self.gen])
        self.assertLess(self.ox.store["algae"], 50 - used)


class StorageTests(unittest.TestCase):
    def test_storage_room(self):
        m = new_match()
        bin_ = put(m, "storage_bin", 4)
        box = put(m, "ration_box", 6)
        self.assertGreater(machines.storage_room(bin_, "dirt"), 0)
        self.assertEqual(machines.storage_room(box, "dirt"), 0)
        self.assertGreater(machines.storage_room(box, "nutrient_bar"), 0)
        bin_.store["dirt"] = bin_.d["capacity"]
        self.assertEqual(machines.storage_room(bin_, "dirt"), 0)


if __name__ == "__main__":
    unittest.main()
