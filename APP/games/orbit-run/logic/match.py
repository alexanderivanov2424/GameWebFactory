"""Planet Jumpers: Match, one run of missions played in one game (no lobby, network or members).

    match = Match(names, run, rng)   names: {pid: name} in seat order (clockwise); run: ship.Run
    match.start_mission()           draw the next mission, upkeep, deal, find the captain, draft
    match.stage                     "draft" -> "play" <-> "collect" (a full trick stays on the table)
                                    -> "debrief" (mission over; next_mission() starts the next one)
    match.turn()                    whose turn (draft or play), or None
    match.take(pid, task_id) / match.pass_turn(pid)     the task draft (draft.py)
    match.play(pid, card)           play a card to the trick; a full trick goes to its winner and
                                    the stage becomes "collect" (server.py pauses, then collect())
    match.collect()                 clear the trick: the winner leads the next, or the mission ends
    match.can_end_early()           every task is done and none can fail any more, cards are left
    match.end_early()               end the mission now (the cards left are put away unplayed)
    match.mission_over              True once a mission ended (server.py saves the run)
    match.result                    None while the run goes on; then {"outcome": "destroyed" |
                                    "complete", "reason": ...} (server.py finishes the game)
    match.public() / match.private(pid)

Tricks: every player with cards plays one, clockwise from the leader (the captain leads the
first; then whoever won the last). A leader without cards hands the lead to the next player
clockwise who has some, so with uneven hands the last trick has fewer cards.
"""

import random

from gamekit import LobbyError

from . import cards, missions, tasks
from .draft import Draft

LOG_SIZE = 30


class Match:
    def __init__(self, names, run, rng=random):
        self.names = dict(names)
        self.seats = list(self.names)
        self.run = run
        self.rng = rng
        self.result = None
        self.log = []
        self.mission = None
        self.stage = None

    def say(self, line):
        self.log.append(line)
        del self.log[:-LOG_SIZE]

    # --- Mission flow ------------------------------------------------------------------

    def start_mission(self):
        mission_id = missions.draw(self.run.completed, self.rng)
        if mission_id is None:
            return self.end("complete", "Every mission deck is empty: the run is complete!")
        self.mission = missions.MISSIONS[mission_id]
        self.mission_over = False
        self.debrief = None
        number = self.run.missions + 1
        self.say(f"Mission {number}: {self.mission['name']}.")
        lost = self.run.upkeep()
        self.say(f"Upkeep: {lost['fuel']} fuel, {lost['food']} food.")
        self.hands = cards.deal(self.seats, self.rng)
        self.captain = next(pid for pid, hand in self.hands.items() if cards.CAPTAIN_CARD in hand)
        self.say(f"{self.names[self.captain]} holds the black {cards.value(cards.CAPTAIN_CARD)} and is captain.")
        self.won = {pid: [] for pid in self.seats}  # pid -> tricks won (lists of cards)
        self.trick = []  # [(pid, card)] in play order
        self.trick_order = []
        self.trick_number = 0
        self.trick_winner = None
        start = self.seats.index(self.captain)
        self.draft = Draft(self.seats[start:] + self.seats[:start], self.mission["tasks"])
        self.stage = "draft"
        self._after_draft()

    def _after_draft(self):
        if self.draft.turn() is None:
            self.stage = "play"
            self._new_trick(self.captain)

    def _new_trick(self, leader):
        start = self.seats.index(leader)
        clockwise = self.seats[start:] + self.seats[:start]
        self.trick_order = [pid for pid in clockwise if self.hands[pid]]
        self.trick = []
        self.trick_winner = None
        self.trick_number += 1

    def turn(self):
        if self.result is not None:
            return None
        if self.stage == "draft":
            return self.draft.turn()
        if self.stage == "play":
            return self.trick_order[len(self.trick)]
        return None

    def _check_turn(self, pid, stage):
        if self.stage != stage:
            raise LobbyError("You can't do that right now.")
        if self.turn() != pid:
            raise LobbyError("It's not your turn.")

    # --- Draft -------------------------------------------------------------------------

    def take(self, pid, task_id):
        self._check_turn(pid, "draft")
        if task_id not in self.mission["tasks"]:
            raise LobbyError("That task isn't on this mission.")
        self.draft.take(pid, task_id)
        self.say(f"{self.names[pid]} takes {tasks.TASKS[task_id]['name']}.")
        self._after_draft()

    def pass_turn(self, pid):
        self._check_turn(pid, "draft")
        self.draft.pass_turn(pid)
        self.say(f"{self.names[pid]} passes.")

    # --- Tricks ------------------------------------------------------------------------

    def led(self):
        return cards.suit(self.trick[0][1]) if self.trick else None

    def playable(self, pid):
        return cards.playable(self.hands[pid], self.led())

    def play(self, pid, card):
        self._check_turn(pid, "play")
        if card not in self.hands[pid]:
            raise LobbyError("That card isn't in your hand.")
        if card not in self.playable(pid):
            raise LobbyError(f"You must follow suit ({cards.SUITS[self.led()]}).")
        self.hands[pid].remove(card)
        self.trick.append((pid, card))
        if len(self.trick) == len(self.trick_order):
            self.trick_winner = cards.trick_winner(self.trick)
            self.won[self.trick_winner].append([c for _, c in self.trick])
            self.say(f"{self.names[self.trick_winner]} wins trick {self.trick_number}.")
            self.stage = "collect"

    def collect(self):
        if self.stage != "collect":
            return
        if any(self.hands.values()):
            self.stage = "play"
            self._new_trick(self.trick_winner)
        else:
            self.end_mission()

    # --- Tasks and the end of a mission ------------------------------------------------

    def _chances(self, owner):
        in_trick = self.stage == "play" and any(pid == owner for pid, _ in self.trick)
        return len(self.hands[owner]) + (1 if in_trick else 0)

    def task_status(self, task_id):
        owner = self.draft.owners.get(task_id)
        if owner is None:
            return "open"
        theirs = {c for pid, tricks in self.won.items() if pid != owner for t in tricks for c in t}
        return tasks.status(tasks.TASKS[task_id], self.won[owner], theirs, self._chances(owner))

    def task_secured(self, task_id):
        owner = self.draft.owners.get(task_id)
        if owner is None:
            return False
        return tasks.secured(tasks.TASKS[task_id], self.task_status(task_id), self._chances(owner))

    def can_end_early(self):
        return (self.result is None and self.stage in ("play", "collect") and any(self.hands.values())
                and all(self.task_status(t) == "done" and self.task_secured(t) for t in self.mission["tasks"]))

    def end_early(self):
        if not self.can_end_early():
            raise LobbyError("The mission can only end early once every task is done and can't fail any more.")
        self.say("Every task is done and can't fail any more: the mission ends early.")
        for hand in self.hands.values():
            hand.clear()
        self.end_mission()

    def end_mission(self):
        self.stage = "debrief"
        self.mission_over = True
        self.trick = []
        report = []
        for task_id in self.mission["tasks"]:
            task = tasks.TASKS[task_id]
            done = self.task_status(task_id) == "done"
            lines = self.run.apply(task["success" if done else "failure"], self.mission)
            report.append({"id": task_id, "status": "done" if done else "failed", "effects": lines})
            self.say(f"{task['name']}: {'done' if done else 'failed'}{': ' + ', '.join(lines) if lines else ''}.")
        self.run.missions += 1
        self.run.completed.append(self.mission["id"])
        self.debrief = report
        if self.run.ship["health"] <= 0:
            self.end("destroyed", "The ship's hull is gone: the run is over.")
        elif missions.draw(self.run.completed, self.rng) is None:
            self.end("complete", "Every mission deck is empty: the run is complete!")

    def next_mission(self):
        if self.stage != "debrief" or self.result is not None:
            raise LobbyError("The mission isn't over yet.")
        self.start_mission()

    def end(self, outcome, reason):
        self.run.over = outcome
        self.result = {"outcome": outcome, "reason": reason, "missions": self.run.missions}
        self.say(reason)

    # --- What clients see ----------------------------------------------------------------

    def public(self):
        state = {
            "names": self.names,
            "seats": self.seats,
            "stage": self.stage,
            "turn": self.turn(),
            "run": self.run.public(),
            "decks": missions.deck_left(self.run.completed),
            "log": list(self.log),
        }
        if self.mission is None:
            return state
        mission = self.mission
        state.update({
            "mission": {
                "id": mission["id"], "name": mission["name"], "deck": mission["deck"],
                "fuel": mission["fuel"], "food": mission["food"], "setup": mission["setup"],
                "number": self.run.missions + (0 if self.mission_over else 1),
                "tasks": [{**tasks.public(tasks.TASKS[t]), "owner": self.draft.owners.get(t),
                           "status": self.task_status(t), "secured": self.task_secured(t)}
                          for t in mission["tasks"]],
            },
            "canEndEarly": self.can_end_early(),
            "captain": self.captain,
            "draft": self.draft.public() if self.stage == "draft" else None,
            "handSizes": {pid: len(hand) for pid, hand in self.hands.items()},
            "tricksWon": {pid: len(tricks) for pid, tricks in self.won.items()},
            "trick": {"number": self.trick_number, "plays": [{"pid": p, "card": c} for p, c in self.trick],
                      "winner": self.trick_winner if self.stage == "collect" else None},
            "debrief": self.debrief,
        })
        return state

    def private(self, pid):
        if self.mission is None or pid not in self.hands:
            return None
        return {"hand": list(self.hands[pid]),
                "playable": self.playable(pid) if self.turn() == pid and self.stage == "play" else []}
