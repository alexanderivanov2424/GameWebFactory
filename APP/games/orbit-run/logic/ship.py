"""Orbit Run: the ship and the saved run (the host's progress, kept between games).

    Run.new()                 a fresh run: mission 0, START ship, nothing completed
    Run.load(saved)           a Run from saved data, or None if it's missing or unreadable
    run.save()                plain JSON for LobbyGame.save_data
    run.upkeep()              start of a mission: fuel and food -1 each (never below 0)
    run.apply(effects, mission) -> lines of what changed (task effects, see tasks.py)
    run.continuable()         a saved run can be continued unless it's over
    run.ship                  {"health", "fuel", "food", "science"}
    run.missions              missions played; run.completed: their ids, in order (the discard pile)
    run.over                  None, "destroyed" (hull at 0) or "complete" (every mission deck empty)
"""

START = {"health": 5, "fuel": 0, "food": 0, "science": 0}
CAPS = {"health": 5, "fuel": 3, "food": 3}  # science has no cap
SAVE_VERSION = 1
OVER = ("destroyed", "complete")


class Run:
    def __init__(self, missions, completed, ship, over=None):
        self.missions = missions
        self.completed = list(completed)
        self.ship = dict(ship)
        self.over = over

    @classmethod
    def new(cls):
        return cls(0, [], START)

    @classmethod
    def load(cls, saved):
        try:
            if saved.get("v") != SAVE_VERSION:
                return None
            ship = {k: saved["ship"][k] for k in START}
            if not all(type(v) is int and v >= 0 for v in ship.values()):
                return None
            completed = saved["completed"]
            missions = saved["missions"]
            if type(missions) is not int or not all(isinstance(c, str) for c in completed):
                return None
            over = saved.get("over")
            return cls(missions, completed, ship, over if over in OVER else None)
        except (AttributeError, KeyError, TypeError):
            return None

    def save(self):
        return {"v": SAVE_VERSION, "missions": self.missions, "completed": self.completed,
                "ship": dict(self.ship), "over": self.over}

    def continuable(self):
        return self.over is None

    def change(self, key, amount):
        before = self.ship[key]
        after = max(0, before + amount)
        if key in CAPS:
            after = min(CAPS[key], after)
        self.ship[key] = after
        return after - before

    def upkeep(self):
        return {key: self.change(key, -1) for key in ("fuel", "food")}

    def apply(self, effects, mission):
        lines = []
        for key, amount, label in (("fuel", mission["fuel"] if effects.get("fuel") else 0, "fuel"),
                                   ("food", mission["food"] if effects.get("food") else 0, "food"),
                                   ("health", -effects.get("damage", 0), "hull"),
                                   ("science", effects.get("science", 0), "science")):
            if amount:
                got = self.change(key, amount)
                capped = "" if got == amount else f" (capped at {CAPS[key]})" if amount > 0 else ""
                lines.append(f"{'+' if got >= 0 else ''}{got} {label}{capped}")
        return lines

    def public(self):
        return {"missions": self.missions, "completed": self.completed, "ship": dict(self.ship),
                "caps": CAPS, "over": self.over}
