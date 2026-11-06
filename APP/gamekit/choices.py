"""Hidden simultaneous choices: everyone picks in secret, then all picks are revealed at once.

    choices = SecretChoices(player_ids)   # who must choose this time
    choices = SecretChoices(player_ids, optional_ids=ids)  # ids may also choose; nobody waits for them
    choices.can_choose(pid)     # is pid choosing (required or optional)?
    choices.choose(pid, value)  # record pid's pick; False if pid can't choose or already chose
    choices.chosen(pid)         # has pid picked?
    choices.choice(pid)         # pid's pick (keep it private until revealed)
    choices.complete()          # has everyone required picked? Then reveal.
    choices.remove(pid)         # pid left; they no longer hold anyone up
    choices.reveal()            # mark revealed; returns {pid: value} (optional picks included)
    choices.peek()              # {pid: value} without revealing (picks that stay secret forever)
    choices.public()            # {pid: {"chosen": bool, "choice": value if revealed else None}}

Before the reveal, public() only says *who* has picked, so clients can show face-down
cards. Optional choosers only appear in public() once they've picked, so nobody learns
who could have. Send a player their own pick through private_state.
"""


class SecretChoices:
    def __init__(self, player_ids=(), optional_ids=()):
        self.pending = list(player_ids)
        self.optional = [pid for pid in optional_ids if pid not in self.pending]
        self.picks = {}
        self.revealed = False

    def can_choose(self, pid):
        return pid in self.pending or pid in self.optional

    def choose(self, pid, value):
        if self.revealed or not self.can_choose(pid) or pid in self.picks:
            return False
        self.picks[pid] = value
        return True

    def chosen(self, pid):
        return pid in self.picks

    def choice(self, pid):
        return self.picks.get(pid)

    def complete(self):
        return bool(self.pending) and all(pid in self.picks for pid in self.pending)

    def remove(self, pid):
        if pid in self.pending:
            self.pending.remove(pid)
        if pid in self.optional:
            self.optional.remove(pid)
        self.picks.pop(pid, None)

    def reveal(self):
        self.revealed = True
        return dict(self.picks)

    def peek(self):
        return dict(self.picks)

    def public(self):
        shown = self.pending + [pid for pid in self.optional if pid in self.picks]
        return {
            pid: {"chosen": pid in self.picks, "choice": self.picks.get(pid) if self.revealed else None}
            for pid in shown
        }
