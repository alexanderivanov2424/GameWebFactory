"""Snowbound economy: one Player per seat (wallet, machines, upgrades, supplies, needs).

Every player has their own cash, machines and upgrades; snow anyone clears pays whoever
cleared it ($1 per unit of snow). Shared upgrades (content.UPGRADES[...]["shared"]) are bought
once for the whole team and stored on the Match, not here.

Player fields: name, color, cash, earned (cash ever earned), cleared (snow ever cleared),
owned {machine id: count}, upgrades (set of ids), rations, diesel (litres), food 0-100,
warmth 0-100, frostbite / starving (bool), frenzy (seconds left of x FRENZY), focus (lot
index the crews head for, or None), cursor ([x, y] or None), clicks (click budget, refilled
CLICKS_PER_SECOND per second).
"""

from gamekit import LobbyError

from .content import MACHINES, UPGRADES, machine_cost

PRICES = {"rations": 12, "diesel": 1.5, "logs": 8}
DELIVERY_FEE = 1.25
FRENZY = 5
CLICKS_PER_SECOND = 15
START = {"cash": 0, "rations": 3, "diesel": 20}


class Player:
    def __init__(self, pid, name, color):
        self.id = pid
        self.name = name
        self.color = color
        self.cash = START["cash"]
        self.earned = 0.0
        self.cleared = 0.0
        self.owned = {mid: 0 for mid in MACHINES}
        self.upgrades = set()
        self.rations = START["rations"]
        self.diesel = float(START["diesel"])
        self.food = 100.0
        self.warmth = 100.0
        self.frostbite = False
        self.starving = False
        self.frenzy = 0.0
        self.focus = None
        self.cursor = None
        self.clicks = CLICKS_PER_SECOND

    # --- multipliers -----------------------------------------------------------------

    def effect(self, kind, default=1):
        """Product of this player's own upgrades of a kind (multipliers)."""
        value = default
        for uid in self.upgrades:
            u = UPGRADES[uid]
            if u["kind"] == kind and not u["shared"]:
                value *= u["value"]
        return value

    def has_auto(self, item):
        return any(UPGRADES[u]["kind"] == "auto" and UPGRADES[u]["value"] == item for u in self.upgrades)

    def machine_rate(self, mid):
        """Snow per second of all this player's machines of one kind (before weather/needs)."""
        n = self.owned[mid]
        if not n:
            return 0.0
        rate = n * MACHINES[mid]["rate"]
        for uid in self.upgrades:
            u = UPGRADES[uid]
            if u["kind"] == "machine" and u["machine"] == mid:
                rate *= u["value"]
        return rate

    def base_rate(self):
        return sum(self.machine_rate(mid) for mid in MACHINES)

    def work_mult(self, blizzard):
        """Multiplier on this player's machines right now."""
        mult = FRENZY if self.frenzy > 0 else 1
        if self.frostbite:
            mult *= 0.5
        if blizzard:
            mult *= 0.75
        return mult

    def diesel_use(self):
        """Litres per second the machines burn."""
        return sum(n * MACHINES[mid]["diesel"] for mid, n in self.owned.items())

    def click_power(self):
        if self.frostbite:
            return 0.0
        power = self.effect("click_mult") + self.base_rate() * sum(
            UPGRADES[u]["value"] for u in self.upgrades if UPGRADES[u]["kind"] == "click_pct") / 100
        if self.frenzy > 0:
            power *= FRENZY
        if self.starving:
            power *= 0.2
        return power

    # --- money -----------------------------------------------------------------------

    def earn(self, snow):
        self.cash += snow
        self.earned += snow
        self.cleared += snow

    def pay(self, cost):
        if cost > self.cash + 1e-9:
            raise LobbyError(f"Not enough cash (need ${cost:,.0f}).")
        self.cash -= cost

    def buy_machine(self, mid, count):
        if mid not in MACHINES:
            raise LobbyError("Unknown machine.")
        self.pay(machine_cost(mid, self.owned[mid], count))
        self.owned[mid] += count

    def upgrade_visible(self, uid, shared_owned):
        u = UPGRADES[uid]
        if uid in self.upgrades or uid in shared_owned:
            return False
        if u["machine"]:
            return self.owned[u["machine"]] >= u["owned"]
        return self.earned >= u["cost"] * 0.25

    def buy_supply(self, item, qty, fee=1.0):
        """Buy qty of rations/diesel/logs; returns qty (logs go to the shared woodpile)."""
        if item not in PRICES:
            raise LobbyError("Unknown supply.")
        self.pay(PRICES[item] * qty * fee)
        if item == "rations":
            self.rations += qty
        elif item == "diesel":
            self.diesel += qty
        return qty
