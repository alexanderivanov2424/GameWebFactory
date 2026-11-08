"""Bastion: Match, one game from start to finish (no lobby, network or members).

    match = Match({"p1": "Ann", "p2": "Bob"}, settings)   # names fixed at the start
    match.stage              "build" (build turns) or "market" (between levels)
    match.play(pid, uid, x=None, y=None)   play a hand card (a structure on x, y; an order)
    match.demolish(pid, x, y)              remove one of your structures (free)
    match.end_turn(pid, done=True)         build: done with this turn (False takes it back);
                                           when everyone is done the next turn starts, or the siege
    match.buy(pid, slot) / match.retire(pid, uid) / match.ready(pid, done=True)   market
    match.leave(pid)         pid left mid-game
    match.public()           JSON-safe state for everyone (server.py's game_state)
    match.private(pid)       pid's hand, owned cards, where each hand card may go (targets) and
                             tower ranges there (ranges)
    match.result             None while playing; then {"winner": None, "victory": bool, "reason", "level"}

Flow: level 1 build turn 1 ... last build turn -> siege (battle.py) -> market (unless it was
the last level or the keep fell) -> level 2 build turn 1 ... Holding the last level wins.
Each build turn every player discards their hand, draws HAND_SIZE, gets LABOR (+ quarries) and
gold from their farms. Holding a level pays its reward to every player; chapels then heal the
keep and repair walls next to them.
"""

import random

from gamekit import Deck, LobbyError

from . import cards as cards_module
from .battle import run_siege
from .board import Board, key
from .cards import CARDS, STARTING_DECK, stat
from .enemies import ENEMIES, LEVELS, public_level
from .maps import MAPS
from .market import RETIRE_COST, Market
from .orders import apply_order, check_target
from .seat import Seat

HAND_SIZE = 5
LABOR = 3
START_GOLD = 2
UPGRADE_LABOR = 1  # upgrading a structure by playing its card again costs +1 labor per level it has
MIN_DECK = 5  # retiring can't shrink a deck below this
DIFFICULTY = {"easy": 0.75, "normal": 1.0, "hard": 1.3}  # enemy health multiplier
PLAYER_SCALE = {1: 0.55, 2: 1.0, 3: 1.35, 4: 1.9}  # enemy health by players (files are for 2)
COLORS = ["#2f6fdf", "#d9482b", "#2f9e44", "#b8860b", "#8e44ad", "#00838f"]


class Match:
    def __init__(self, names, settings, rng=random, levels=None, maps=None):
        self.names = dict(names)
        self.rng = rng
        self.levels = levels if levels is not None else LEVELS
        game_map = (maps or MAPS)[settings["map"]]
        self.board = Board(game_map)
        self.keep_max = settings["keepHealth"]
        self.keep = self.keep_max
        self.difficulty = settings["difficulty"]
        self.seats = {}
        for i, (pid, name) in enumerate(self.names.items()):
            seat = Seat(pid, name, COLORS[i % len(COLORS)], Deck(STARTING_DECK, rng), gold=START_GOLD)
            self.seats[pid] = seat
        self.order = list(self.seats)
        self.level = 0  # index into self.levels
        self.stage = "build"
        self.turn = 1
        self.market = Market(rng)
        self.log = []
        self.battle = None
        self.result = None
        self.step = 0  # bumped when a new turn or stage starts (client alerts)
        self.write(f"Level 1: {self.current()['name']}. Build your defences!")
        self.start_turn()

    # --- helpers ----------------------------------------------------------------------------

    def current(self):
        return self.levels[self.level]

    def write(self, text, pid=None):
        entry = {"text": text}
        if pid:
            entry["pid"] = pid
        self.log.append(entry)

    def seat(self, pid):
        seat = self.seats.get(pid)
        if seat is None:
            raise LobbyError("You're not in this game.")
        return seat

    def require(self, pid, stage):
        if self.result is not None:
            raise LobbyError("The game is over.")
        if self.stage != stage:
            raise LobbyError("You can't do that now." if stage == "build" else "The market is closed.")
        return self.seat(pid)

    def hp_scale(self):
        players = min(max(1, len(self.seats)), max(PLAYER_SCALE))
        return round(DIFFICULTY.get(self.difficulty, 1.0) * PLAYER_SCALE[players], 2)

    # --- build turns --------------------------------------------------------------------------

    def start_turn(self):
        self.step += 1
        paid = []
        for seat in self.seats.values():
            seat.refill(HAND_SIZE)
            seat.done = False
            seat.labor = LABOR + sum(stat(CARDS[s.card], "labor", s.level) for s in self.board.of_kind("quarry")
                                     if s.owner == seat.pid)
            gold = sum(stat(CARDS[s.card], "gold", s.level) for s in self.board.of_kind("farm") if s.owner == seat.pid)
            if gold:
                seat.gold += gold
                paid.append(f"{seat.name} +{gold}")
        turns = self.current()["buildTurns"]
        self.write(f"Build turn {self.turn} of {turns}." + (f" Farms paid: {', '.join(paid)}." if paid else ""))

    def play(self, pid, uid, x=None, y=None):
        seat = self.require(pid, "build")
        if seat.done:
            raise LobbyError("You've ended your turn (take it back to keep playing).")
        instance = seat.hand_card(uid)
        card = CARDS[instance["card"]]
        existing = None
        if card["kind"] == "order":
            check_target(self, card, x, y)
        else:
            if x is None:
                raise LobbyError(f"Pick where to build {card['name']}.")
            existing = self.board.check(card, x, y)
        labor = card["labor"] + (existing.level * UPGRADE_LABOR if existing else 0)
        if labor > seat.labor:
            what = "Upgrading it" if existing else card["name"]
            raise LobbyError(f"{what} needs {labor} labor; you have {seat.labor}.")
        seat.hand.remove(instance)
        seat.labor -= labor
        if card["kind"] == "order":
            notes = apply_order(self, seat, card, x, y)
            self.write(f"{seat.name} played {card['name']}" + (f": {', '.join(notes)}." if notes else "."), pid)
        else:
            what = self.board.place(card, x, y, pid)
            if what == "upgraded":
                level = self.board.at(x, y).level
                self.write(f"{seat.name} upgraded a {card['name']} to level {level}.", pid)
            else:
                self.write(f"{seat.name} built a {card['name']}.", pid)
        seat.deck.discard([instance])

    def demolish(self, pid, x, y):
        seat = self.require(pid, "build")
        structure = self.board.demolish(x, y, pid)
        self.write(f"{seat.name} demolished a {CARDS[structure.card]['name']}.", pid)

    def end_turn(self, pid, done=True):
        seat = self.require(pid, "build")
        seat.done = bool(done)
        self.check_all_done()

    def check_all_done(self):
        if self.result is not None or not self.seats or not all(s.done for s in self.seats.values()):
            return
        if self.stage == "market":
            self.next_level()
        elif self.turn < self.current()["buildTurns"]:
            self.turn += 1
            self.start_turn()
        else:
            self.siege()

    # --- the siege -----------------------------------------------------------------------------

    def siege(self):
        level = self.current()
        number = self.level + 1
        battle_id = (self.battle["id"] + 1) if self.battle else 1
        for seat in self.seats.values():
            seat.deck.discard(seat.hand)
            seat.hand = []
            seat.labor = 0
        outcome = run_siege(self.board, level, self.keep, self.hp_scale(), battle_id, number)
        self.battle = outcome.replay
        self.keep = max(0, outcome.keep)
        s = outcome.summary
        parts = [f"{s['kills']} slain"]
        if s["leaked"]:
            parts.append(f"{s['leaked']} reached the keep (-{s['keepDamage']} health)")
        if s["wallsLost"]:
            parts.append(f"{s['wallsLost']} wall{'s' if s['wallsLost'] > 1 else ''} destroyed")
        self.step += 1
        if not outcome.held:
            self.write(f"Siege {number}: {level['name']}. The keep has fallen! " + ", ".join(parts) + ".")
            self.end(False, f"The keep fell to {level['name']} (level {number}).")
            return
        self.write(f"Siege {number}: {level['name']} held! " + ", ".join(parts) + ".")
        if self.level + 1 >= len(self.levels):
            self.end(True, f"All {len(self.levels)} sieges held. The realm is saved!")
            return
        for seat in self.seats.values():
            seat.gold += level["reward"]
            seat.done = False
            seat.retired = False
        self.write(f"Everyone earns {level['reward']} gold.")
        self.bless()
        self.stage = "market"
        self.market.deal(number)
        self.write(f"The market is open. Next: level {number + 1}, {self.levels[self.level + 1]['name']}.")

    def bless(self):
        """Chapels: heal the keep and repair the walls next to them after a siege held."""
        healed = 0
        for chapel in self.board.of_kind("chapel"):
            card = CARDS[chapel.card]
            healed += stat(card, "keep", chapel.level)
            for wall in self.board.near(chapel.x, chapel.y, "wall"):
                wall.hp = min(wall.max_hp(), wall.hp + stat(card, "repair", chapel.level))
        if healed:
            before = self.keep
            self.keep = min(self.keep_max, self.keep + healed)
            if self.keep > before:
                self.write(f"Chapels restore {self.keep - before} keep health.")

    # --- the market ------------------------------------------------------------------------------

    def buy(self, pid, slot):
        seat = self.require(pid, "market")
        if seat.done:
            raise LobbyError("You're done shopping (take it back to keep buying).")
        card_id, cost = self.market.price(slot)
        if cost > seat.gold:
            raise LobbyError(f"{CARDS[card_id]['name']} costs {cost} gold; you have {seat.gold}.")
        seat.gold -= cost
        seat.deck.add(card_id)
        self.write(f"{seat.name} bought {CARDS[card_id]['name']}.", pid)

    def retire(self, pid, uid):
        seat = self.require(pid, "market")
        if seat.done:
            raise LobbyError("You're done shopping (take it back first).")
        if seat.retired:
            raise LobbyError("You can retire one card per market.")
        if seat.gold < RETIRE_COST:
            raise LobbyError(f"Retiring a card costs {RETIRE_COST} gold.")
        if len(seat.all_cards()) <= MIN_DECK:
            raise LobbyError(f"Your deck can't go below {MIN_DECK} cards.")
        for pile in (seat.deck.draw_pile, seat.deck.discard_pile, seat.hand):
            for instance in pile:
                if instance["uid"] == uid:
                    pile.remove(instance)
                    seat.gold -= RETIRE_COST
                    seat.retired = True
                    self.write(f"{seat.name} retired {CARDS[instance['card']]['name']} from their deck.", pid)
                    return
        raise LobbyError("You don't own that card.")

    def ready(self, pid, done=True):
        seat = self.require(pid, "market")
        seat.done = bool(done)
        self.check_all_done()

    def next_level(self):
        self.level += 1
        self.stage = "build"
        self.turn = 1
        self.write(f"Level {self.level + 1}: {self.current()['name']}. Build your defences!")
        self.start_turn()

    # --- leaving and the end -----------------------------------------------------------------------

    def leave(self, pid):
        seat = self.seats.pop(pid, None)
        if seat is None:
            return
        self.order.remove(pid)
        self.board.disown(pid, self.order[0] if self.order else None)
        self.write(f"{seat.name} left; their structures pass to {self.names[self.order[0]]}." if self.order
                   else f"{seat.name} left.")
        if not self.seats:
            self.end(False, "Everyone left.")
        else:
            self.check_all_done()

    def end(self, victory, reason):
        self.result = {"winner": None, "victory": victory, "reason": reason, "level": self.level + 1}

    # --- what clients see ------------------------------------------------------------------------------

    def catalog(self):
        if not hasattr(self, "_catalog"):
            self._catalog = {
                "cards": {c: cards_module.public(card) for c, card in CARDS.items()},
                "enemies": {e: {k: v for k, v in enemy.items() if k != "id"} for e, enemy in ENEMIES.items()},
                "map": self.board.map.public(),
                "levels": [public_level(level) for level in self.levels],
            }
        return self._catalog

    def public(self):
        state = {
            **self.catalog(),
            "rules": {"handSize": HAND_SIZE, "labor": LABOR, "upgradeLabor": UPGRADE_LABOR, "retireCost": RETIRE_COST, "minDeck": MIN_DECK},
            "names": self.names,
            "order": list(self.order),
            "seats": {pid: seat.public() for pid, seat in self.seats.items()},
            "stage": self.stage,
            "level": self.level + 1,
            "turn": self.turn,
            "step": self.step,
            "keep": self.keep,
            "keepMax": self.keep_max,
            "hpScale": self.hp_scale(),
            "structures": self.board.public(),
            "log": {str(i): entry for i, entry in enumerate(self.log)},
            "logCount": len(self.log),
        }
        if self.stage == "market" and self.result is None:
            state["market"] = self.market.public()
        if self.battle:
            state["battle"] = self.battle
        return state

    def targets(self, seat):
        """{card id: {"x,y": labor}} where each structure / targeted order in the hand may be played
        right now (labor includes the upgrade surcharge), so the client needs no placement rules."""
        result = {}
        if self.stage != "build" or self.result is not None:
            return result
        game_map = self.board.map
        for card_id in {c["card"] for c in seat.hand}:
            card = CARDS[card_id]
            if card["place"] is None:
                continue
            cells = {}
            for y in range(game_map.height):
                for x in range(game_map.width):
                    try:
                        if card["place"] == "structure":
                            check_target(self, card, x, y)
                            labor = card["labor"]
                        else:
                            existing = self.board.check(card, x, y)
                            labor = card["labor"] + (existing.level * UPGRADE_LABOR if existing else 0)
                    except LobbyError:
                        continue
                    cells[key(x, y)] = labor
            result[card_id] = cells
        return result

    def ranges(self, targets):
        """{tower card id: {"x,y": range there}} for the hover preview (level after the play,
        watchtower bonus included)."""
        result = {}
        for card_id, cells in targets.items():
            card = CARDS[card_id]
            if card["kind"] != "tower":
                continue
            result[card_id] = {}
            for cell_key in cells:
                x, y = map(int, cell_key.split(","))
                existing = self.board.at(x, y)
                level = existing.level + 1 if existing else 1
                result[card_id][cell_key] = stat(card, "range", level) + self.board.boost(x, y, "watch")
        return result

    def private(self, pid):
        seat = self.seats.get(pid)
        if seat is None:
            return None
        targets = self.targets(seat)
        return {**seat.private(), "targets": targets, "ranges": self.ranges(targets)}
