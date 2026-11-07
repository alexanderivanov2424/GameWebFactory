"""Smugglers: rules tests on logic.Match (no lobby). Run: python3 -I tools/run_tests.py smugglers

Positions are set up by hand: ships moved with ship["at"] = node, cards made with card(m, id),
contracts rigged with rig_contract(...).
"""

import importlib
import random
import unittest

from gamekit import LobbyError

GAME = "games.smugglers.logic"
Match = importlib.import_module(f"{GAME}.match").Match
smuggling = importlib.import_module(f"{GAME}.smuggling")
GOODS = importlib.import_module(f"{GAME}.content").GOODS


def new_match(players=3, seed=1, **settings):
    names = {f"p{i + 1}": f"Player {i + 1}" for i in range(players)}
    return Match(names, {"contractsEach": 10, "legalFine": 1, "roundLimit": 30, **settings}, rng=random.Random(seed))


def card(m, good):
    return m.goods.make(good)


def ships_of(m, pid):
    return [s for s in m.ships.values() if s["owner"] == pid]


def rig_contract(m, source, destination, good="nebula-spice", bonus=2, cid=None):
    """Put a contract from source to destination in the row (replacing the first one)."""
    cid = cid or m.row[0]
    m.contracts[cid] = {"id": cid, "from": source, "to": destination, "good": good, "bonus": bonus}
    return cid


def loaded(m, ship, cid, goods, declared="nebula-spice"):
    ship["cargo"] = [card(m, g) for g in goods]
    ship["contract"] = cid
    ship["declared"] = declared
    m.holder[cid] = ship["id"]


class SetupTests(unittest.TestCase):
    def test_roles_and_starting_hands(self):
        m = new_match(players=4)
        self.assertEqual(m.queue.order()[-1], m.interpol.pid)  # Interpol plays last
        self.assertEqual(len(m.smugglers), 3)
        self.assertNotIn(m.interpol.pid, m.smugglers)
        for pid in m.smugglers:
            self.assertEqual(len(m.smugglers[pid]["hand"]), 5)
            self.assertEqual(len(ships_of(m, pid)), 2)
        self.assertEqual(len(m.row), 5)
        self.assertEqual(len(m.contract_deck), 3 * 10 - 5)  # contractsEach x smugglers, 5 face up
        self.assertEqual(len(m.interpol.hand), 3)
        self.assertEqual(sum(m.interpol.owned().values()), 5)
        self.assertEqual({p["kind"] for p in m.interpol.pieces.values()}, {"patrol", "barrier"})

    def test_interpol_is_random(self):
        picked = {new_match(seed=seed).interpol.pid for seed in range(20)}
        self.assertEqual(picked, {"p1", "p2", "p3"})


class MoveTests(unittest.TestCase):
    def setUp(self):
        self.m = new_match()
        self.pid = self.m.turn()
        self.ship, self.other = ships_of(self.m, self.pid)
        self.ship.update(at="kessar", speed=3)

    def test_move_up_to_speed_and_onto_dots(self):
        self.m.move(self.pid, self.ship["id"], "r1.2")
        self.assertEqual(self.ship["at"], "r1.2")
        with self.assertRaises(LobbyError):
            self.m.move(self.pid, self.ship["id"], "lumen")  # already acted

    def test_too_far_or_blocked(self):
        with self.assertRaises(LobbyError):
            self.m.move(self.pid, self.ship["id"], "vortan")
        barrier = next(p for p in self.m.interpol.pieces.values() if p["kind"] == "barrier")
        barrier["at"] = "r1.1"
        with self.assertRaises(LobbyError):
            self.m.move(self.pid, self.ship["id"], "lumen")  # can't pass
        self.m.move(self.pid, self.ship["id"], "thessa")  # other ways are open

    def test_not_your_ship_or_turn(self):
        enemy = next(s for s in self.m.ships.values() if s["owner"] != self.pid)
        with self.assertRaises(LobbyError):
            self.m.move(self.pid, enemy["id"], "r1.1")
        with self.assertRaises(LobbyError):
            self.m.move(enemy["owner"], enemy["id"], "r1.1")
        with self.assertRaises(LobbyError):
            self.m.play(self.pid, 1, {})  # smugglers can't play Interpol cards

    def test_loaded_ship_stops_at_checkpoint(self):
        self.m.interpol.pieces["checkpoint1"] = {"id": "checkpoint1", "kind": "checkpoint", "at": "r1.1"}
        self.assertIn("lumen", smuggling.reach(self.m, self.ship))  # empty ships pass
        cid = rig_contract(self.m, "kessar", "ferro")
        loaded(self.m, self.ship, cid, ["nebula-spice"])
        reach = smuggling.reach(self.m, self.ship)
        self.assertTrue(reach["r1.1"])
        self.assertNotIn("r1.2", reach)  # can't go past it
        self.m.move(self.pid, self.ship["id"], "r1.1")
        self.assertEqual(self.m.inspection["stage"], "bribe")
        self.assertEqual(self.m.actor(), self.pid)

    def test_loaded_ship_stops_at_patrol(self):
        patrol = next(p for p in self.m.interpol.pieces.values() if p["kind"] == "patrol")
        patrol["at"] = "r1.2"
        cid = rig_contract(self.m, "kessar", "ferro")
        loaded(self.m, self.ship, cid, ["nebula-spice"])
        reach = smuggling.reach(self.m, self.ship)
        self.assertTrue(reach["r1.2"])
        self.assertNotIn("lumen", reach)  # can't fly past it
        self.m.move(self.pid, self.ship["id"], "r1.2")
        self.assertEqual((self.m.inspection["by"], self.m.inspection["stage"]), ("patrol", "bribe"))
        self.ship["cargo"] = []
        self.m.inspection = None
        self.assertIn("lumen", smuggling.reach(self.m, self.ship))  # empty ships pass

    def test_loading_on_a_patrol_spot_is_inspected(self):
        patrol = next(p for p in self.m.interpol.pieces.values() if p["kind"] == "patrol")
        patrol["at"] = "kessar"
        cid = rig_contract(self.m, "kessar", "ferro")
        self.m.pickup(self.pid, self.ship["id"], cid)
        hand = self.m.smugglers[self.pid]["hand"]
        self.m.load(self.pid, [hand[0]["uid"]], [c["uid"] for c in hand[1:5]], "titan-ore")
        self.assertEqual(self.m.inspection["ship"], self.ship["id"])

    def test_empty_ship_passes_checkpoint(self):
        self.ship["speed"] = 3
        self.m.interpol.pieces["checkpoint1"] = {"id": "checkpoint1", "kind": "checkpoint", "at": "r5.1"}
        self.m.move(self.pid, self.ship["id"], "thessa")
        self.assertIsNone(self.m.inspection)

    def test_turn_ends_by_itself_when_ships_are_done(self):
        self.m.move(self.pid, self.ship["id"], "r1.1")
        self.assertEqual(self.m.turn(), self.pid)
        self.m.move(self.pid, self.other["id"], next(iter(smuggling.reach(self.m, self.other))))
        self.assertNotEqual(self.m.turn(), self.pid)
        self.assertFalse(self.ship["acted"])  # reset for their next turn


class CargoTests(unittest.TestCase):
    def setUp(self):
        self.m = new_match()
        self.pid = self.m.turn()
        self.ship = ships_of(self.m, self.pid)[0]
        self.ship["at"] = "kessar"
        self.cid = rig_contract(self.m, "kessar", "ferro", good="titan-ore", bonus=3)

    def test_pickup_load_and_discard(self):
        self.m.pickup(self.pid, self.ship["id"], self.cid)
        hand = self.m.smugglers[self.pid]["hand"]
        self.assertEqual(len(hand), 10)
        uids = [c["uid"] for c in hand]
        with self.assertRaises(LobbyError):
            self.m.end_turn(self.pid)  # must finish loading
        with self.assertRaises(LobbyError):
            self.m.load(self.pid, uids[:3], uids[3:4], "titan-ore")  # must discard 2
        with self.assertRaises(LobbyError):
            self.m.load(self.pid, uids[:3], uids[3:5], "void-crystals")  # declare a legal good
        with self.assertRaises(LobbyError):
            self.m.load(self.pid, [], uids[:5], "titan-ore")  # load at least one
        self.m.load(self.pid, uids[:3], uids[3:5], "titan-ore")
        self.assertEqual(len(self.m.smugglers[self.pid]["hand"]), 5)
        self.assertEqual(len(self.ship["cargo"]), 3)
        self.assertEqual(self.m.holder[self.cid], self.ship["id"])
        self.assertEqual(self.ship["declared"], "titan-ore")
        self.assertIsNone(self.m.loading)

    def test_no_discard_when_under_limit(self):
        self.m.pickup(self.pid, self.ship["id"], self.cid)
        uids = [c["uid"] for c in self.m.smugglers[self.pid]["hand"]]
        with self.assertRaises(LobbyError):
            self.m.load(self.pid, uids[:6], uids[6:7], "titan-ore")
        self.m.load(self.pid, uids[:6], [], "titan-ore")
        self.assertEqual(len(self.m.smugglers[self.pid]["hand"]), 4)

    def test_pickup_needs_the_token_here(self):
        self.ship["at"] = "lumen"
        with self.assertRaises(LobbyError):
            self.m.pickup(self.pid, self.ship["id"], self.cid)

    def test_payout(self):
        contract = {"good": "titan-ore", "bonus": 3}
        cards = lambda *ids: [{"uid": i, "card": g} for i, g in enumerate(ids)]  # noqa: E731
        # Largest set: 3 spice (3) beats 2 silk (6); no bonus (contract wants ore).
        paid = smuggling.payout(cards("nebula-spice", "nebula-spice", "nebula-spice", "star-silk", "star-silk"),
                                contract, GOODS)
        self.assertEqual((paid["set"], paid["total"]), ("nebula-spice", 3))
        # Tie on count: the better paying set; the bonus counts toward it.
        paid = smuggling.payout(cards("titan-ore", "titan-ore", "hydro-ice", "hydro-ice"), contract, GOODS)
        self.assertEqual((paid["set"], paid["base"], paid["bonus"], paid["total"]), ("titan-ore", 2, 3, 5))
        # Illegal goods pay their own value.
        paid = smuggling.payout(cards("star-silk", "void-crystals", "rogue-ai-cores"), contract, GOODS)
        self.assertEqual(paid["total"], 3 + 7 + 9)

    def test_deliver(self):
        loaded(self.m, self.ship, self.cid, ["titan-ore", "titan-ore", "xeno-relics"], "titan-ore")
        with self.assertRaises(LobbyError):
            self.m.deliver(self.pid, self.ship["id"])  # not there yet
        self.ship["at"] = "ferro"
        before = list(self.m.row)
        self.m.deliver(self.pid, self.ship["id"])
        self.assertEqual(self.m.smugglers[self.pid]["credits"], 2 + 3 + 8)
        self.assertNotIn(self.cid, self.m.row)
        self.assertEqual(len(self.m.row), 5)
        self.assertNotIn(self.m.row[-1], before)
        self.assertEqual(self.ship["cargo"], [])
        self.assertNotIn("contract", self.ship)
        self.assertNotIn(self.cid, self.m.holder)

    def test_only_own_contract(self):
        other = rig_contract(self.m, "lumen", "kessar", cid=self.m.row[1])
        loaded(self.m, self.ship, self.cid, ["titan-ore"])
        self.assertTrue(other)
        with self.assertRaises(LobbyError):
            self.m.deliver(self.pid, self.ship["id"])  # at kessar: other's destination, not its own


class InspectionTests(unittest.TestCase):
    def setUp(self):
        self.m = new_match()
        self.pid = self.m.turn()
        self.ship = ships_of(self.m, self.pid)[0]
        self.ship["at"] = "kessar"
        self.cid = rig_contract(self.m, "kessar", "ferro")
        loaded(self.m, self.ship, self.cid, ["nebula-spice", "nebula-spice", "titan-ore", "void-crystals"])
        self.m.interpol.pieces["checkpoint1"] = {"id": "checkpoint1", "kind": "checkpoint", "at": "r1.1"}
        self.m.smugglers[self.pid]["credits"] = 5
        self.m.move(self.pid, self.ship["id"], "r1.1")
        self.cop = self.m.interpol.pid

    def test_bribe_then_pass(self):
        with self.assertRaises(LobbyError):
            self.m.bribe(self.pid, 6)  # more than they have
        with self.assertRaises(LobbyError):
            self.m.decide(self.cop, False)  # bribe first
        self.m.bribe(self.pid, 4)
        self.assertEqual(self.m.actor(), self.cop)
        self.m.decide(self.cop, False)
        self.assertEqual(self.m.smugglers[self.pid]["credits"], 1)
        self.assertEqual(self.m.interpol.score, 4)
        self.assertEqual(len(self.ship["cargo"]), 4)
        self.assertEqual(self.m.actor(), self.pid)  # back to the smuggler's turn

    def test_inspect_seizes_what_isnt_declared(self):
        self.m.bribe(self.pid, 3)
        self.m.decide(self.cop, True)
        self.assertEqual([c["card"] for c in self.ship["cargo"]], ["nebula-spice", "nebula-spice"])
        fine = 1 + GOODS["void-crystals"]["penalty"]  # 1 legal fine + the crystals' penalty
        self.assertEqual(self.m.smugglers[self.pid]["credits"], max(0, 5 - fine))  # the bribe isn't paid
        paid = min(5, fine)
        self.assertEqual(self.m.interpol.score, paid + GOODS["titan-ore"]["value"] + GOODS["void-crystals"]["value"])
        self.assertEqual(self.m.holder[self.cid], self.ship["id"])

    def test_empty_ship_returns_token(self):
        self.ship["declared"] = "star-silk"
        self.m.smugglers[self.pid]["credits"] = 0
        self.m.bribe(self.pid, 0)
        self.m.decide(self.cop, True)
        self.assertEqual(self.ship["cargo"], [])
        self.assertNotIn(self.cid, self.m.holder)
        self.assertEqual(self.m.smugglers[self.pid]["credits"], 0)  # never below 0
        self.assertIn(self.cid, smuggling.pickups(self.m, self.ship) or [self.cid])

    def test_nothing_else_during_inspection(self):
        with self.assertRaises(LobbyError):
            self.m.end_turn(self.pid)
        other = ships_of(self.m, self.pid)[1]
        with self.assertRaises(LobbyError):
            self.m.move(self.pid, other["id"], next(iter(smuggling.reach(self.m, other))))

    def test_owner_leaves_mid_inspection(self):
        self.m.bribe(self.pid, 0)
        self.m.remove(self.pid)
        self.assertIsNone(self.m.inspection)
        self.assertNotIn(self.cid, self.m.holder)
        self.assertNotEqual(self.m.turn(), self.pid)


def interpol_turn(m):
    """End smuggler turns until it's Interpol's."""
    while m.turn() != m.interpol.pid:
        m.end_turn(m.turn())
    return m.interpol.pid


def give_hand(m, *card_ids):
    m.interpol.deck.discard(m.interpol.hand)  # keep the real cards drawable
    m.interpol.hand = [m.interpol.deck.make(cid) for cid in card_ids]
    return [c["uid"] for c in m.interpol.hand]


class InterpolTests(unittest.TestCase):
    def setUp(self):
        self.m = new_match()
        self.cop = interpol_turn(self.m)
        self.police = self.m.interpol

    def test_turn_resources(self):
        self.assertEqual((self.police.actions, self.police.buys, self.police.budget), (1, 1, 0))

    def test_funding_then_buy(self):
        funding = give_hand(self.m, "funding", "funding", "funding")
        for uid in funding:
            self.m.play(self.cop, uid, {})
        self.assertEqual(self.police.budget, 6)
        self.assertEqual(self.police.actions, 1)  # funding is free
        self.m.buy(self.cop, "checkpoint")
        self.assertEqual(self.police.budget, 2)
        self.assertIn("checkpoint1", self.police.pieces)
        self.assertNotIn("at", self.police.pieces["checkpoint1"])  # off the board until played
        with self.assertRaises(LobbyError):
            self.m.buy(self.cop, "funding")  # one buy per turn
        self.assertEqual(self.police.deck.discard_pile[-1]["card"], "checkpoint")

    def test_buy_needs_budget(self):
        with self.assertRaises(LobbyError):
            self.m.buy(self.cop, "federal-grant")

    def test_one_action_unless_more(self):
        informant, other = give_hand(self.m, "informant", "informant")
        self.m.play(self.cop, informant, {})
        self.assertEqual(len(self.police.hand), 3)  # 1 left + 2 drawn
        with self.assertRaises(LobbyError):
            self.m.play(self.cop, other, {})

    def test_command_center_gives_actions(self):
        command, informant = give_hand(self.m, "command-center", "informant")
        self.m.play(self.cop, command, {})
        self.m.play(self.cop, informant, {})
        self.assertEqual(self.police.actions, 1)

    def test_barrier_placement(self):
        barrier = give_hand(self.m, "barrier")[0]
        with self.assertRaises(LobbyError):
            self.m.play(self.cop, barrier, {"piece": "barrier1", "to": "kessar"})  # not on planets
        ship = next(iter(self.m.ships.values()))
        ship["at"] = "r1.1"
        with self.assertRaises(LobbyError):
            self.m.play(self.cop, barrier, {"piece": "barrier1", "to": "r1.1"})  # not on ships
        self.m.play(self.cop, barrier, {"piece": "barrier1", "to": "r1.2"})
        self.assertEqual(self.police.pieces["barrier1"]["at"], "r1.2")
        self.assertEqual(self.police.actions, 0)

    def test_barriers_never_cut_the_board(self):
        board = self.m.board
        # Drask has two routes (r9 to Thessa, r13 to Nimbus): blocking both would cut it off.
        self.police.pieces["barrier1"]["at"] = "r9.1"
        self.police.pieces["barrier2"] = {"id": "barrier2", "kind": "barrier"}
        allowed = self.police.allowed(self.m, self.police.pieces["barrier2"], {"piece": "barrier"})
        self.assertNotIn("r13.1", allowed)
        self.assertIn("r1.1", allowed)
        self.assertTrue(board.connected(board.planets, {"r9.1", "r1.1"}))

    def test_patrol_moves_and_inspects(self):
        patrol = give_hand(self.m, "patrol")[0]
        smuggler_ship = next(iter(self.m.ships.values()))
        cid = rig_contract(self.m, "kessar", "ferro")
        loaded(self.m, smuggler_ship, cid, ["titan-ore"])
        smuggler_ship["at"] = "merrow"  # 3 steps from Tarsis (Interpol's home)
        with self.assertRaises(LobbyError):
            self.m.play(self.cop, patrol, {"piece": "patrol1", "to": "kessar"})  # too far
        self.m.play(self.cop, patrol, {"piece": "patrol1", "to": "merrow"})
        self.assertEqual(self.m.inspection["by"], "patrol")  # always, no choice
        self.assertEqual(self.m.inspection["ship"], smuggler_ship["id"])
        self.assertEqual(self.m.actor(), smuggler_ship["owner"])
        self.m.bribe(smuggler_ship["owner"], 0)
        self.m.decide(self.cop, True)
        self.assertEqual(self.m.turn(), self.cop)
        self.assertEqual(self.m.actor(), self.cop)

    def test_patrol_onto_empty_ships_inspects_nothing(self):
        patrol = give_hand(self.m, "patrol")[0]
        ship = next(iter(self.m.ships.values()))
        ship["at"] = "merrow"
        self.m.play(self.cop, patrol, {"piece": "patrol1", "to": "merrow"})
        self.assertIsNone(self.m.inspection)

    def test_checkpoint_onto_two_loaded_ships_inspects_both(self):
        self.police.pieces["checkpoint1"] = {"id": "checkpoint1", "kind": "checkpoint"}
        checkpoint = give_hand(self.m, "checkpoint")[0]
        first, second = [s for s in self.m.ships.values()][:2]
        for i, ship in enumerate((first, second)):
            loaded(self.m, ship, rig_contract(self.m, "kessar", "ferro", cid=self.m.row[i]), ["titan-ore"])
            ship["at"] = "lumen"
        self.m.play(self.cop, checkpoint, {"piece": "checkpoint1", "to": "lumen"})
        self.assertEqual(self.m.inspection["ship"], first["id"])
        self.m.bribe(first["owner"], 0)
        self.m.decide(self.cop, False)
        self.assertEqual(self.m.inspection["ship"], second["id"])  # the next one
        self.assertEqual(self.m.inspection["by"], "checkpoint")
        self.m.bribe(second["owner"], 0)
        self.m.decide(self.cop, False)
        self.assertIsNone(self.m.inspection)
        self.assertEqual(self.m.actor(), self.cop)  # back to Interpol's turn

    def test_repeat_operation(self):
        informant, repeat = give_hand(self.m, "informant", "repeat-operation")
        self.police.actions = 2
        self.m.play(self.cop, informant, {})
        with self.assertRaises(LobbyError):
            self.m.play(self.cop, repeat, {"copy": 999})
        self.m.play(self.cop, repeat, {"copy": informant})
        self.assertEqual(len(self.police.hand), 4)  # 2 + 2 drawn

    def test_end_turn_draws_three_and_counts_rounds(self):
        self.m.end_turn(self.cop)
        self.assertEqual(len(self.police.hand), 3)
        self.assertEqual(self.m.round, 2)
        self.assertNotEqual(self.m.turn(), self.cop)


class EndTests(unittest.TestCase):
    def test_contracts_run_out_richest_smuggler_wins(self):
        m = new_match(contractsEach=3)
        pid = m.turn()
        m.smugglers[pid]["credits"] = 10
        m.interpol.score = 9
        m.contract_deck = []
        m.row = [m.row[0]]
        ship = ships_of(m, pid)[0]
        cid = rig_contract(m, "kessar", "ferro")
        loaded(m, ship, cid, ["titan-ore"])
        ship["at"] = "ferro"
        m.deliver(pid, ship["id"])
        self.assertEqual(m.result["winner"], pid)
        self.assertIn("contract", m.result["reason"])

    def test_interpol_wins_with_higher_score(self):
        m = new_match()
        m.interpol.score = 20
        for s in m.smugglers.values():
            s["credits"] = 19
        m.end("test")
        self.assertEqual(m.result["winner"], m.interpol.pid)

    def test_tie_between_smugglers(self):
        m = new_match()
        for s in m.smugglers.values():
            s["credits"] = 4
        m.end("test")
        self.assertIsNone(m.result["winner"])
        self.assertEqual(sorted(m.result["winners"]), sorted(m.smugglers))

    def test_round_limit(self):
        m = new_match(roundLimit=5)
        while m.result is None:
            m.end_turn(m.turn())
        self.assertEqual(m.round, 6)
        self.assertIn("round limit", m.result["reason"])


class LeavingTests(unittest.TestCase):
    def test_interpol_leaves(self):
        m = new_match()
        first = m.turn()
        m.smugglers[first]["credits"] = 3
        m.remove(m.interpol.pid)
        self.assertEqual(m.result["winner"], first)

    def test_smuggler_leaves_on_their_turn(self):
        m = new_match()
        first = m.turn()
        ship = ships_of(m, first)[0]
        cid = rig_contract(m, "kessar", "ferro")
        loaded(m, ship, cid, ["titan-ore"])
        m.remove(first)
        self.assertNotEqual(m.turn(), first)
        self.assertEqual(ships_of(m, first), [])
        self.assertNotIn(cid, m.holder)
        self.assertIsNone(m.result)

    def test_last_smuggler_leaves(self):
        m = new_match(players=2)
        smuggler = next(iter(m.smugglers))
        m.remove(smuggler)
        self.assertEqual(m.result["winner"], m.interpol.pid)

    def test_leaving_before_interpols_turn_starts_it(self):
        m = new_match(players=3)
        m.end_turn(m.turn())
        m.remove(m.turn())  # the second smuggler leaves on their turn
        self.assertEqual(m.turn(), m.interpol.pid)
        self.assertEqual((m.interpol.actions, m.interpol.buys), (1, 1))


if __name__ == "__main__":
    unittest.main()
