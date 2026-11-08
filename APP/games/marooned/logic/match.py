"""Marooned: Match, one game from start to finish (no lobby, network or members).

    match = Match({"p1": "Ann", ...}, settings, rng)
    match.stage            # "objectives" -> "day" <-> "vote" -> "over"
    match.turn()           # whose day turn it is (None outside the day)
    match.actor()          # who the game is waiting on right now (a pending roll, a check
                           # step, or the turn player); None during simultaneous stages
    match.<action>(pid, ...)   # see the "Actions" section; LobbyError if not allowed
    match.remove(pid)      # pid left mid-game
    match.public() / match.private(pid)
    match.result           # None while playing; then the end-of-game summary (see end())

A day: everyone takes one turn in turn_list (rotated by one seat each day) spending energy
on actions; after the last turn comes the night: the raft leaves if it's due, otherwise the
vote (night.py), then hunger and sleep, then dawn of the next day, or the monsoon.
The day actions themselves are in actions.py (island) and people.py (items, camp, players).
"""

import random

from gamekit import Deck, LobbyError, SecretChoices

from . import actions, night, objectives, people, scoring, view
from .camp import Camp
from .checks import CheckDeck
from .content import CHECKS, FINDS, card_list
from .island import Island
from .survivor import Survivor

MIN_LEFT = 3   # fewer players than this and the game ends
SUPPLIES_PER_PLAYER = {"food": 1}   # crash supplies in the stockpile at the start
SMALL, LARGE = 7, 9


def map_size(setting, players):
    if setting == "small":
        return SMALL
    if setting == "large":
        return LARGE
    return SMALL if players <= 5 else LARGE


class Match:
    def __init__(self, names, settings, rng=random):
        self.names = dict(names)
        self.settings = dict(settings)
        self.rng = rng
        self.seats = list(self.names)
        rng.shuffle(self.seats)
        self.order = list(self.seats)        # still in the game, in seat order
        supplies = {item: n * len(self.seats) for item, n in SUPPLIES_PER_PLAYER.items()}
        self.island = Island(map_size(self.settings.get("mapSize", "auto"), len(self.seats)), rng, supplies)
        self.camp = Camp(len(self.seats))
        self.checks = CheckDeck(rng)
        self.finds = Deck(card_list(FINDS), rng=rng)
        self._arrivals = 0
        self.people = {}
        for pid in self.seats:
            self.people[pid] = Survivor(pid, self.island.camp)
            self.people[pid].arrived = self._next_arrival()
        self.imposter = rng.choice(self.seats)
        dealt, self.keep = self.settings.get("objectivesDealt", 3), self.settings.get("objectivesKept", 2)
        self.dealt = {pid: objectives.deal(rng, "imposter" if pid == self.imposter else "castaway", dealt)
                      for pid in self.seats}
        self.keep = min(self.keep, dealt)
        self.objectives = {}
        self.picks = SecretChoices(list(self.seats))
        self.monsoon = self.settings.get("monsoon", 14)
        self.day = 1
        self.stage = "objectives"
        self.turn_list, self.turn_pos = [], 0
        self.pending = None     # a roll or tile choice waiting for its second message
        self.check = None       # a build check in progress
        self.votes = None
        self.vote_history = {}
        self.launch_day = None
        self.escaped = set()
        self.snapped = 0
        self.result = None
        self.logs = {}
        self.log("You wake up on the beach. One of you is not what they seem...")

    def _next_arrival(self):
        self._arrivals += 1
        return self._arrivals

    def log(self, text):
        self.logs[len(self.logs)] = text

    def arrive(self, s, cell):
        s.pos = tuple(cell)
        s.arrived = self._next_arrival()
        s.stats["visited"].add(s.pos)

    # --- Whose move ------------------------------------------------------------------------

    def turn(self):
        if self.stage != "day" or self.turn_pos >= len(self.turn_list):
            return None
        return self.turn_list[self.turn_pos]

    def actor(self):
        if self.stage != "day":
            return None
        if self.check:
            return self.check.actor()
        if self.pending:
            return self.pending["player"]
        return self.turn()

    def _require_free(self, pid):
        """pid may start a new day action: their turn, nothing half done."""
        if self.stage != "day":
            raise LobbyError("Not now.")
        if self.turn() != pid:
            raise LobbyError("It's not your turn.")
        if self.check or self.pending:
            raise LobbyError("Finish what's in progress first.")
        return self.people[pid]

    def _require_pending(self, pid, kind):
        if self.stage != "day" or not self.pending or self.pending["player"] != pid or self.pending["kind"] != kind:
            raise LobbyError("Not now.")

    def _require_check(self, pid, step):
        if self.stage != "day" or not self.check or self.check.step != step or self.check.actor() != pid:
            raise LobbyError("Not now.")

    # --- Objectives (first stage) ------------------------------------------------------------

    def pick_objectives(self, pid, kept):
        if self.stage != "objectives":
            raise LobbyError("Objectives are already picked.")
        dealt = self.dealt.get(pid, [])
        if len(set(kept)) != self.keep or any(oid not in dealt for oid in kept):
            raise LobbyError(f"Keep {self.keep} of the objectives you were dealt.")
        if not self.picks.choose(pid, list(kept)):
            raise LobbyError("You've already picked.")
        self._after_picks()

    def _after_picks(self):
        if self.stage == "objectives" and self.picks.complete():
            self.objectives = self.picks.peek()
            self.picks = None
            self.stage = "day"
            self._start_day()

    # --- Actions: island (actions.py) -----------------------------------------------------------

    def move(self, pid, cell):
        self._require_free(pid)
        actions.move(self, pid, cell)

    def explore(self, pid, cell):
        self._require_free(pid)
        actions.explore(self, pid, cell)

    def place(self, pid, uid):
        self._require_pending(pid, "explore")
        actions.place(self, pid, uid)

    def gather(self, pid, item):
        self._require_free(pid)
        actions.gather(self, pid, item)

    def report(self, pid, face):
        self._require_pending(pid, "gather")
        actions.report(self, pid, face)

    def search(self, pid):
        self._require_free(pid)
        actions.search(self, pid)

    # --- Actions: items, camp, players (people.py) -------------------------------------------------

    def deposit(self, pid, item, count):
        self._require_free(pid)
        people.deposit(self, pid, item, count)

    def take(self, pid, item, count):
        self._require_free(pid)
        people.take(self, pid, item, count)

    def build(self, pid, project):
        self._require_free(pid)
        people.build(self, pid, project)

    def craft(self, pid, tool):
        self._require_free(pid)
        people.craft(self, pid, tool)

    def eat(self, pid, source):
        self._require_free(pid)
        people.eat(self, pid, source)

    def heal(self, pid):
        self._require_free(pid)
        people.heal(self, pid)

    def give(self, pid, target, item):
        self._require_free(pid)
        people.give(self, pid, target, item)

    def attack(self, pid, target, steal):
        self._require_free(pid)
        people.attack(self, pid, target, steal)

    def launch(self, pid):
        self._require_free(pid)
        people.launch(self, pid)

    # --- Build checks (checks.py) --------------------------------------------------------------

    def choose_helper(self, pid, helper):
        self._require_check(pid, "helper")
        if helper == pid or helper not in self.order:
            raise LobbyError("Pick another player who's still in the game.")
        self.checks.start(self.check, helper)
        self.log(f"{self.names[pid]} asked {self.names[helper]} to help check the build.")

    def discard_check(self, pid, uid):
        self._require_check(pid, "discard")
        self.checks.discard(self.check, uid)

    def reveal_check(self, pid, uid):
        self._require_check(pid, "reveal")
        self._resolve_check(self.checks.reveal(self.check, uid))

    def _resolve_check(self, card_id):
        check, self.check = self.check, None
        project = self.camp.project(check.project)
        stage = project.stage()["name"]
        outcome = CHECKS[card_id]["outcome"]
        self.log(f"Build check on the {stage}: {CHECKS[card_id]['name']}.")
        if outcome == "solid":
            people.finish_stage(self, project, check.builder)
        elif outcome == "shaky":
            item = project.patch(self.rng)
            self.log(f"The {stage} needs 1 more {item} to hold.")
        else:
            project.snap()
            self.snapped += 1
            self.log(f"Half of the {stage}'s materials are ruined.")

    # --- Turns, nights and days -------------------------------------------------------------------

    def end_turn(self, pid):
        self._require_free(pid)
        self.log(f"{self.names[pid]} ended their turn.")
        self.turn_pos += 1
        self._after_turn()

    def _after_turn(self):
        if self.turn_pos < len(self.turn_list) or self.stage != "day":
            return
        if self.launch_day is not None and self.launch_day <= self.day:
            self._escape()
            return
        self.stage = "vote"
        night.start_vote(self)

    def vote(self, pid, choice):
        if self.stage != "vote":
            raise LobbyError("Voting happens at night.")
        night.vote(self, pid, choice)
        self._after_votes()

    def _after_votes(self):
        if self.stage != "vote" or not self.votes.complete():
            return
        night.tally(self)
        night.sleep(self)
        if self.day >= self.monsoon:
            self.log("The monsoon arrives. Nobody is getting off this island now.")
            self.end("The monsoon arrived before the raft left.")
            return
        self.day += 1
        self.stage = "day"
        self._start_day()

    def _start_day(self):
        start = (self.day - 1) % len(self.seats)
        rotated = self.seats[start:] + self.seats[:start]
        self.turn_list = [pid for pid in rotated if pid in self.order]
        self.turn_pos = 0
        for pid in self.order:
            self.people[pid].energy = self.people[pid].max_energy()
        self.log(f"Day {self.day} of {self.monsoon}.")

    def _escape(self):
        self.escaped = {pid for pid in self.order if self.people[pid].pos == self.island.camp}
        names = [self.names[pid] for pid in self.order if pid in self.escaped]
        self.log(f"The raft sails away with {', '.join(names) if names else 'nobody aboard'}!")
        self.end("The raft left the island.")

    def remove(self, pid):
        if pid not in self.order or self.result is not None:
            return
        s = self.people[pid]
        pile = self.island.pile(s.pos)
        for item, count in s.pack.items():
            pile[item] = pile.get(item, 0) + count
        s.pack = {}
        if self.pending and self.pending["player"] == pid:
            if self.pending["kind"] == "explore":
                actions.place(self, pid, self.pending["cards"][0]["uid"])
            self.pending = None
        if self.check and pid in (self.check.builder, self.check.helper):
            if self.check.step == "helper":
                self.checks.start(self.check, None)
            self._resolve_check(self.checks.pick_any(self.check))
        was_turn = self.turn() == pid
        self.order.remove(pid)
        if pid in self.turn_list:
            index = self.turn_list.index(pid)
            self.turn_list.remove(pid)
            if index < self.turn_pos:
                self.turn_pos -= 1
        self.log(f"{self.names[pid]} left the island.")
        if len(self.order) < MIN_LEFT:
            self.end("Too few players are left.")
            return
        if self.stage == "objectives":
            self.picks.remove(pid)
            self._after_picks()
        elif self.stage == "vote":
            self.votes.remove(pid)
            self._after_votes()
        elif was_turn or self.turn_pos >= len(self.turn_list):
            self._after_turn()

    def end(self, reason):
        self.stage = "over"
        self.pending = None
        self.check = None
        scores = scoring.final(self)
        self.result = {
            "reason": reason,
            "winners": scoring.winners(scores, self.order),
            "imposter": self.imposter,
            "escaped": sorted(self.escaped),
            "scores": scores,
            "lies": {pid: s.stats["lies"] for pid, s in self.people.items()},
        }

    # --- What clients see (view.py) ---------------------------------------------------------

    def public(self):
        return view.public(self)

    def private(self, pid):
        return view.private(self, pid)
