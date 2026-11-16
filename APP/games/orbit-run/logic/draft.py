"""Orbit Run: drafting a mission's tasks around the table, starting with the captain.

Players take turns in seat order from the captain, in laps that always restart at the captain.
On your turn you take one of the tasks left, or pass if there are more players left in this lap
(you included) than tasks left: with 5 players and 2 tasks the first three may pass; with 7 tasks
the first lap can't pass (5 tasks are taken), then the next lap may.

    draft = Draft(order, task_ids)   order: seat order starting with the captain
    draft.turn()                     whose turn, or None once every task is taken
    draft.can_pass()
    draft.take(pid, task_id) / draft.pass_turn(pid)    raise LobbyError if not allowed
    draft.owners                     {task id: pid}
    draft.left                       task ids not taken yet, in mission order
"""

from gamekit import LobbyError


class Draft:
    def __init__(self, order, task_ids):
        self.order = list(order)
        self.left = list(task_ids)
        self.owners = {}
        self.position = 0  # index in order within the current lap

    def turn(self):
        return self.order[self.position] if self.left else None

    def can_pass(self):
        return bool(self.left) and len(self.order) - self.position > len(self.left)

    def _check_turn(self, pid):
        if self.turn() != pid:
            raise LobbyError("It's not your turn to pick a task.")

    def take(self, pid, task_id):
        self._check_turn(pid)
        if task_id not in self.left:
            raise LobbyError("That task is already taken.")
        self.left.remove(task_id)
        self.owners[task_id] = pid
        self._advance()

    def pass_turn(self, pid):
        self._check_turn(pid)
        if not self.can_pass():
            raise LobbyError("You can't pass: there are as many tasks left as players left this lap.")
        self._advance()

    def _advance(self):
        self.position = (self.position + 1) % len(self.order)

    def public(self):
        return {"turn": self.turn(), "canPass": self.can_pass(), "left": list(self.left)}
