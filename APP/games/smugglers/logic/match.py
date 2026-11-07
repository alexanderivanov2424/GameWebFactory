"""Smugglers: Match, one game from start to finish (no lobby, network or members).

    match = Match({"p1": "Ann", "p2": "Bob"}, settings)   # names fixed at the start
    match.actor()            # who must act now (the turn's player, or an inspection's), or None
    match.turn()             # whose turn it is (None once over)
    match.end_turn(pid)
    smuggler actions (smuggling.py):  move, pickup, load, deliver
    Interpol actions (interpol.py):   play, buy
    inspections (inspection.py):      bribe, decide
    match.remove(pid)        # pid left mid-game
    match.public() / match.private(pid)
    match.result             # None while playing; then {"winner", "winners", "reason", ...}

Turn order: the smugglers in random order, then Interpol; a round ends after Interpol's turn.
The game ends when every contract is done (deck and row empty), or after `roundLimit`
rounds. The smuggler with the most credits wins, unless Interpol's score is higher.
"""

import random

from gamekit import Deck, LobbyError, TurnQueue

from . import inspection, smuggling
from .board import BOARDS
from .content import GOODS, INTERPOL_CARDS, SHIPS, goods_deck_ids, make_contracts, ship_tile_ids
from .interpol import Interpol

DEFAULT_BOARD = "outer-rim"
ROW_SIZE = 5          # face-up contracts
START_HAND = 5        # goods each smuggler starts with
SHIPS_EACH = 2
COLORS = ["#ff5252", "#40c4ff", "#69f0ae", "#ffd740", "#e040fb"]  # smuggler colors, by seat


class Match:
    def __init__(self, names, settings, rng=random, board=DEFAULT_BOARD,
                 goods=GOODS, ships=SHIPS, cards=INTERPOL_CARDS):
        self.names = dict(names)
        self.settings = dict(settings)
        self.legal_fine = self.settings.get("legalFine", 1)
        self.round_limit = self.settings.get("roundLimit", 40)
        self.rng = rng
        self.board = BOARDS[board]
        self.goods_defs = goods
        self.cards = cards
        order = list(self.names)
        rng.shuffle(order)
        interpol_id = order.pop(rng.randrange(len(order)))
        self.queue = TurnQueue(order + [interpol_id])
        self.round = 1
        self.turn_number = 1
        self.result = None
        self.log = []
        self.inspection = None
        self.inspection_queue = []  # ship ids waiting for an inspection (inspection.check)
        self.loading = None

        self.goods = Deck(goods_deck_ids(goods), rng)
        self.smugglers = {
            pid: {"credits": 0, "hand": self.goods.draw(START_HAND), "color": COLORS[i % len(COLORS)]}
            for i, pid in enumerate(order)
        }
        tiles = ship_tile_ids(ships)
        rng.shuffle(tiles)
        self.ships = {}
        for pid in order:
            for _ in range(SHIPS_EACH):
                tile = ships[tiles.pop()] if tiles else next(iter(ships.values()))
                sid = f"s{len(self.ships) + 1}"
                self.ships[sid] = {"id": sid, "owner": pid, "name": tile["name"], "speed": tile["speed"],
                                   "at": rng.choice(self.board.starts), "cargo": [], "acted": False}
        total = self.settings.get("contractsEach", 5) * len(order)
        self.contracts = {c["id"]: c for c in make_contracts(self.board, goods, total, rng)}
        self.contract_deck = list(self.contracts)
        self.row = []
        self.holder = {}  # contract id -> ship id carrying its cargo token
        self.done = []
        self.interpol = Interpol(interpol_id, cards, self.board, rng)
        self.reveal_contracts(log=False)
        self.add_log(None, f"{self.names[interpol_id]} is Interpol. Smugglers: "
                           f"{', '.join(self.names[p] for p in order)}.")

    # --- Helpers ---------------------------------------------------------------------------

    def add_log(self, pid, text, cards=None):
        entry = {"text": text}
        if pid:
            entry["pid"] = pid
        if cards:
            entry["cards"] = cards
        self.log.append(entry)

    def label(self, node):
        if self.board.is_planet(node):
            return self.board.planets[node]["name"]
        x, y = self.board.nodes[node]
        near = min(self.board.planets.values(), key=lambda p: (p["x"] - x) ** 2 + (p["y"] - y) ** 2)
        return f"deep space near {near['name']}"

    def number(self, contract_id):
        return contract_id[1:]

    def clear_cargo(self, ship):
        ship["cargo"] = []
        ship.pop("contract", None)
        ship.pop("declared", None)

    def reveal_contracts(self, log=True):
        while len(self.row) < ROW_SIZE and self.contract_deck:
            cid = self.contract_deck.pop(0)
            self.row.append(cid)
            if log:
                c = self.contracts[cid]
                self.add_log(None, f"New contract #{self.number(cid)}: {self.goods_defs[c['good']]['name']} "
                                   f"from {self.label(c['from'])} to {self.label(c['to'])}.")
        if not self.row and not self.contract_deck:
            self.end("Every contract has been delivered.")

    def turn(self):
        return self.queue.current() if self.result is None else None

    def actor(self):
        if self.result is not None:
            return None
        if self.inspection:
            return self.inspection["owner"] if self.inspection["stage"] == "bribe" else self.interpol.pid
        return self.queue.current()

    def is_interpol(self, pid):
        return pid == self.interpol.pid

    def _require_turn(self, pid, role):
        if self.actor() != pid or self.inspection:
            raise LobbyError("It's not your turn.")
        if (role == "interpol") != self.is_interpol(pid):
            raise LobbyError("Only Interpol can do that." if role == "interpol" else "Only smugglers can do that.")
        if self.loading and role != "load":
            raise LobbyError("Finish loading your cargo first.")

    # --- Actions ---------------------------------------------------------------------------

    def move(self, pid, ship_id, to):
        self._require_turn(pid, "smuggler")
        smuggling.move(self, pid, ship_id, to)
        self.after_smuggler_action(pid)

    def pickup(self, pid, ship_id, contract_id):
        self._require_turn(pid, "smuggler")
        smuggling.pickup(self, pid, ship_id, contract_id)

    def load(self, pid, load_uids, discard_uids, declare):
        self._require_turn(pid, "load")
        smuggling.load(self, pid, load_uids, discard_uids, declare)
        self.after_smuggler_action(pid)

    def deliver(self, pid, ship_id):
        self._require_turn(pid, "smuggler")
        smuggling.deliver(self, pid, ship_id)
        self.after_smuggler_action(pid)

    def play(self, pid, uid, targets):
        self._require_turn(pid, "interpol")
        self.interpol.play(self, uid, targets)

    def buy(self, pid, card_id):
        self._require_turn(pid, "interpol")
        card = self.interpol.buy(card_id)
        self.add_log(pid, f"Interpol bought {card['name']}.")

    def bribe(self, pid, amount):
        inspection.bribe(self, pid, amount)

    def decide(self, pid, search):
        inspection.decide(self, pid, search)
        inspection.next_inspection(self)
        current = self.turn()
        if current and not self.is_interpol(current):
            self.after_smuggler_action(current)

    def after_smuggler_action(self, pid):
        """End the smuggler's turn by itself once none of their ships can do anything more."""
        if self.result or self.inspection or self.loading or self.turn() != pid:
            return
        ships = [s for s in self.ships.values() if s["owner"] == pid]
        if not any(smuggling.can_act(self, s) or smuggling.can_deliver(self, s) for s in ships):
            self.end_turn(pid)

    def end_turn(self, pid):
        if self.inspection:
            raise LobbyError("Wait for the inspection to finish.")
        if self.turn() != pid:
            raise LobbyError("It's not your turn.")
        if self.loading:
            raise LobbyError("Finish loading your cargo first.")
        if self.is_interpol(pid):
            self.interpol.end_turn()
            self.round += 1
            if self.round > self.round_limit:
                self.end(f"The round limit ({self.round_limit}) was reached.")
                return
        else:
            for ship in self.ships.values():
                if ship["owner"] == pid:
                    ship["acted"] = False
        self.queue.advance(pid)
        self._start_turn()

    def _start_turn(self):
        self.turn_number += 1
        current = self.queue.current()
        if current and self.is_interpol(current):
            self.interpol.start_turn()

    def remove(self, pid):
        if self.result is not None or pid not in self.queue:
            return
        if self.is_interpol(pid):
            self.queue.remove(pid)
            self.end("Interpol left the game.")
            return
        was_turn = self.turn() == pid
        if self.inspection and self.inspection["owner"] == pid:
            inspection.cancel(self)
        if self.loading and self.loading["pid"] == pid:
            self.loading = None
        for sid in [sid for sid, s in self.ships.items() if s["owner"] == pid]:
            ship = self.ships.pop(sid)
            self.holder.pop(ship.get("contract"), None)
            self.goods.discard(ship["cargo"])
        self.goods.discard(self.smugglers[pid]["hand"])
        self.smugglers[pid]["hand"] = []
        self.smugglers[pid]["left"] = True
        self.queue.remove(pid)
        self.add_log(pid, f"{self.names[pid]} left the game; their ships are gone.")
        if not any(p in self.queue for p in self.smugglers):
            self.end("Every smuggler left.")
            return
        if was_turn:
            self._start_turn()
        inspection.next_inspection(self)  # their ships are gone from the queue

    def end(self, reason):
        if self.result is not None:
            return
        self.inspection = None
        self.inspection_queue = []
        self.loading = None
        playing = {p: s["credits"] for p, s in self.smugglers.items() if not s.get("left")}
        best = max(playing.values(), default=None)
        interpol_in = self.interpol.pid in self.queue
        if best is None or (interpol_in and self.interpol.score > best):
            winners = [self.interpol.pid] if interpol_in else []
        else:
            winners = [p for p, credits in playing.items() if credits == best]
        self.result = {
            "winner": winners[0] if len(winners) == 1 else None,
            "winners": winners,
            "reason": reason,
            "credits": {p: s["credits"] for p, s in self.smugglers.items()},
            "interpolScore": self.interpol.score,
        }
        self.add_log(None, f"Game over: {reason}")

    # --- What clients see ------------------------------------------------------------------

    def public_ship(self, ship):
        info = {key: ship[key] for key in ("owner", "name", "speed", "at", "acted")}
        info["cargo"] = len(ship["cargo"])
        for key in ("contract", "declared"):
            if key in ship:
                info[key] = ship[key]
        if self.result is not None:
            info["contents"] = [card["card"] for card in ship["cargo"]]
        return info

    def public(self):
        state = {
            "names": self.names,
            "interpol": self.interpol.pid,
            "turnOrder": self.queue.order(),
            "round": self.round,
            "roundLimit": self.round_limit,
            "turnNumber": self.turn_number,
            "legalFine": self.legal_fine,
            "smugglers": {
                pid: {key: value for key, value in (("credits", s["credits"]), ("hand", len(s["hand"])),
                                                    ("color", s["color"]), ("left", s.get("left"))) if value is not None}
                for pid, s in self.smugglers.items()
            },
            "ships": {sid: self.public_ship(ship) for sid, ship in self.ships.items()},
            "contracts": {cid: self.contracts[cid] for cid in self.row},
            "row": self.row,
            "holders": self.holder,
            "contractsLeft": len(self.contract_deck),
            "contractsDone": len(self.done),
            "goodsDeck": self.goods.counts(),
            "goods": self.goods_defs,
            "cards": self.cards,
            "police": self.interpol.public(),
            "board": self.board.public(),
            "log": {str(i): entry for i, entry in enumerate(self.log)},
            "logSize": len(self.log),
        }
        for key, value in (("turn", self.turn()), ("actor", self.actor()),
                           ("inspection", self.inspection), ("loading", self.loading)):
            if value is not None:
                state[key] = value
        return state

    def private(self, pid):
        if self.is_interpol(pid):
            return {"role": "interpol", **self.interpol.private(self)}
        if pid not in self.smugglers:
            return None
        mine = [s for s in self.ships.values() if s["owner"] == pid]
        my_turn = self.actor() == pid and not self.inspection and not self.loading
        return {
            "role": "smuggler",
            "hand": self.smugglers[pid]["hand"],
            "cargo": {s["id"]: s["cargo"] for s in mine},
            "reach": {s["id"]: smuggling.reach(self, s) for s in mine if my_turn and not s["acted"]},
            "pickups": {s["id"]: smuggling.pickups(self, s) for s in mine if my_turn and not s["acted"]},
        }
