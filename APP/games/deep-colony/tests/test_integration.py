"""Deep Colony: colonists working with the real machines and networks (no monkeypatching).
Each test is a tiny hand-made world stepped until a condition holds.
Run: cd APP && python3 -B -m unittest discover -s games/deep-colony/tests -p test_integration.py
"""

import importlib
import unittest

content = importlib.import_module("games.deep-colony.logic.content")
dupes = importlib.import_module("games.deep-colony.logic.dupes")
Match = importlib.import_module("games.deep-colony.logic.match").Match

FLOOR_Y = 15


def new_match(w=30):
    m = Match.blank(w, 20, "oxygen")
    for x in range(w):
        m.world.set_cell(m.world.idx(x, FLOOR_Y), "sandstone", 1000, 20)
    return m


def put(m, kind, x, **state):
    """A finished building standing on the floor (bottom row 14)."""
    d = content.BUILDINGS[kind]
    b = m.buildings.place(kind, x, FLOOR_Y - d["h"], "p1", built=True)
    b.state.update(state)
    return b


def wire(m, *cells, kind="wire"):
    for x, y in cells:
        m.buildings.place(kind, x, y, "p1", built=True)


def colonist(m, x, **fields):
    d = dupes.spawn(m, 1, x, FLOOR_Y - 1)[0]
    for k, v in fields.items():
        setattr(d, k, v)
    return d


def run(m, cond, steps=600, dt=0.1):
    for _ in range(steps):
        m.step(dt)
        if cond():
            return True
    return False


class IntegrationTests(unittest.TestCase):
    def test_colonist_runs_generator_to_power_oxygenator(self):
        m = new_match()
        gen = put(m, "manual_generator", 3)
        oxy = put(m, "algae_oxygenator", 8)
        oxy.store["algae"] = 5.0
        wire(m, *[(x, FLOOR_Y - 1) for x in range(gen.port_cell("powerPort")[0], oxy.port_cell("powerPort")[0] + 1)])
        colonist(m, 5)
        self.assertTrue(run(m, lambda: oxy.store["algae"] < 4.0), (gen.status, oxy.status))
        self.assertEqual(oxy.status, "Working")  # it only burns algae (making oxygen) while powered

    def test_colonist_supplies_algae_from_debris_and_storage(self):
        for from_store in (False, True):
            m = new_match()
            oxy = put(m, "algae_oxygenator", 8)
            cap = oxy.d["accepts"]["algae"]
            if from_store:
                bin_ = put(m, "storage_bin", 2)
                bin_.store["algae"] = 20.0
            else:
                m.items.add("algae", 20.0, 2, FLOOR_Y - 1)
            colonist(m, 4)
            self.assertTrue(run(m, lambda: oxy.store.get("algae", 0.0) >= 10.0), from_store)
            self.assertLessEqual(oxy.store["algae"], cap)

    def test_toilet_then_wash_basin(self):
        m = new_match()
        out = put(m, "outhouse", 3)
        dirt = content.BUILDINGS["outhouse"]["params"]["dirtPerUse"]
        out.store["dirt"] = dirt * 2
        basin = put(m, "wash_basin", 8)
        pi, po = basin.port_cell("pipeIn"), basin.port_cell("pipeOut")
        wire(m, pi, kind="liquid_pipe")
        wire(m, po, kind="liquid_pipe")
        m.networks.step(0.1)
        m.networks.pipe_put(basin, "pipeIn", "water", 50.0, 20.0, 0.0)
        d = colonist(m, 5, bladder=100.0)
        self.assertTrue(run(m, lambda: d.needs_wash), d.task)
        self.assertEqual(d.bladder, 0)
        self.assertGreater(d.germs, 0)
        self.assertEqual(out.state["uses"], 1)
        self.assertTrue(run(m, lambda: not d.needs_wash and d.germs == 0), d.task)
        self.assertLess(m.networks.pipe_has(basin, "pipeIn", "water"), 50.0)

    def test_full_outhouse_emptied_and_hauled_to_storage(self):
        m = new_match()
        p = content.BUILDINGS["outhouse"]["params"]
        out = put(m, "outhouse", 3, uses=p["uses"])
        out.store["polluted_dirt"] = 100.0
        bin_ = put(m, "storage_bin", 10)
        colonist(m, 6)
        self.assertTrue(run(m, lambda: bin_.store.get("polluted_dirt", 0.0) >= 99.0, steps=1500),
                        (out.state, bin_.store, list(m.items)))
        self.assertEqual(out.state["uses"], 0)

    def test_ripe_fungus_harvested_into_ration_box(self):
        m = new_match()
        bed = put(m, "fungus_bed", 3)
        bed.state["growth"] = bed.d["params"]["growTime"]
        box = put(m, "ration_box", 9)
        colonist(m, 6)
        self.assertTrue(run(m, lambda: box.store.get("fungus", 0.0) > 0, steps=1200), (bed.state, list(m.items)))
        self.assertEqual(bed.state["growth"] < bed.d["params"]["growTime"], True)

    def test_hungry_colonist_eats_from_ration_box(self):
        m = new_match()
        box = put(m, "ration_box", 9)
        box.store["fungus"] = 5.0
        d = colonist(m, 5, kcal=1000.0)
        self.assertTrue(run(m, lambda: d.kcal > 1500))
        self.assertLess(box.store.get("fungus", 0.0), 5.0)

    def test_colonist_operates_nutrient_press(self):
        m = new_match()
        gen = put(m, "manual_generator", 2)
        press = put(m, "nutrient_press", 9)
        p = press.d["params"]
        press.store["dirt"] = p["dirt"] * 2
        gp, pp = gen.port_cell("powerPort"), press.port_cell("powerPort")
        wire(m, *[(x, gp[1]) for x in range(gp[0], pp[0] + 1)])
        pi = press.port_cell("pipeIn")
        wire(m, pi, kind="liquid_pipe")
        m.networks.step(0.1)
        m.networks.pipe_put(press, "pipeIn", "water", p["water"] * 3, 20.0, 0.0)
        colonist(m, 6)
        colonist(m, 7)
        self.assertTrue(run(m, lambda: m.items.totals().get(p["product"], 0.0) > 0,
                            steps=3000), (press.status, gen.status, press.state))


if __name__ == "__main__":
    unittest.main()
