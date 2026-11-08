"""Schedules: what colonists do in each hour of a cycle (24 hours per cycle).

Three shared schedules, "1"-"3", each a 24-character string of blocks:
    "w" work (jobs and orders), "d" downtime (only needs; stress recovers faster),
    "s" sleep (go to a free Cot, or sleep on the floor)
Every colonist follows one schedule (Dupe.schedule, default "1"). Any player may edit a
schedule or move a colonist to another one (logged).

    schedules = Schedules(match)          match.schedules
    schedules.set_blocks(pid, sid, text)  raises LobbyError on bad input
    schedules.assign(pid, dupe_id, sid)
    schedules.block_for(dupe) -> "w" | "d" | "s" for the current hour
    schedules.hour() -> 0-23
    schedules.public() -> {sid: {"name", "blocks"}}
"""

from gamekit import LobbyError

HOURS = 24
BLOCKS = "wds"
DEFAULT = "w" * 17 + "ddd" + "ssss"


class Schedules:
    def __init__(self, match):
        self.match = match
        self.blocks = {sid: DEFAULT for sid in ("1", "2", "3")}

    def hour(self):
        m = self.match
        return int((m.time % m.cycle_length) / m.cycle_length * HOURS) % HOURS

    def block_for(self, dupe):
        return self.blocks.get(getattr(dupe, "schedule", "1"), DEFAULT)[self.hour()]

    def set_blocks(self, pid, sid, text):
        if sid not in self.blocks:
            raise LobbyError("Unknown schedule.")
        if not isinstance(text, str) or len(text) != HOURS or any(c not in BLOCKS for c in text):
            raise LobbyError("A schedule is 24 blocks of work, downtime or sleep.")
        if text != self.blocks[sid]:
            self.blocks[sid] = text
            self.match.log(f"{self.match.names.get(pid, pid)} changed Schedule {sid}.")

    def assign(self, pid, dupe_id, sid):
        d = self.match.dupes.get(dupe_id)
        if d is None:
            raise LobbyError("Unknown colonist.")
        if sid not in self.blocks:
            raise LobbyError("Unknown schedule.")
        if getattr(d, "schedule", "1") != sid:
            d.schedule = sid
            self.match.log(f"{self.match.names.get(pid, pid)} moved {d.name} to Schedule {sid}.")

    def public(self):
        return {sid: {"name": f"Schedule {sid}", "blocks": text} for sid, text in self.blocks.items()}
