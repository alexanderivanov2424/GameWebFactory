"""Snowbound economy: one Player per seat (wallet, machines, upgrades, supplies, needs).

Every player has their own cash, machines and upgrades; snow anyone clears pays whoever
cleared it ($1 per unit of snow): at once for your shovel and machines that don't haul, when it is
unloaded at a drop point for hauling machines (hauling.py), and processed snow pays when its goods
sell (factory.py). Shared upgrades (content.UPGRADES[...]["shared"]) are bought
once for the whole team and stored on the Match, not here.

Player fields: name, color, cash, earned (cash ever earned), cleared (snow ever cleared),
goods_sold ($ ever made from goods),
owned {machine id: count}, upgrades (set of ids), rations, diesel (litres), food 0-100,
warmth 0-100, frostbite / starving (bool), frenzy (seconds left of x FRENZY).
Character (avatars.py): x, y (world coordinates), keys (held: up/down/left/right), aim (lot
[x, y] under the mouse or None), dig (dig button held), swinging (s left of the swing
animation), rally (None, a lot index, or "follow": where your units look for work first).
"""

from gamekit import LobbyError

from .content import MACHINES, UNLOCK_SHARE, UPGRADES, machine_cost
from .world import WADE_LEVEL

PRICES = {"rations": 12, "diesel": 1.5, "logs": 8}
DELIVERY_FEE = 1.25
FRENZY = 5
MAX_OWNED = 250
START = {"cash": 0, "rations": 3, "diesel": 20}


class Player:
    def __init__(self, pid, name, color, x=0.0, y=0.0):
        self.id = pid
        self.x = x
        self.y = y
        self.keys = ()
        self.aim = None
        self.dig = False
        self.swinging = 0.0
        self.rally = None
        self.name = name
        self.color = color
        self.cash = START["cash"]
        self.earned = 0.0
        self.cleared = 0.0
        self.goods_sold = 0.0
        self.owned = {mid: 0 for mid in MACHINES}
        self.upgrades = set()
        self.rations = START["rations"]
        self.diesel = float(START["diesel"])
        self.food = 100.0
        self.warmth = 100.0
        self.frostbite = False
        self.starving = False
        self.frenzy = 0.0

    # --- multipliers -----------------------------------------------------------------

    def effect(self, kind, default=1):
        """Product of this player's own upgrades of a kind (multipliers)."""
        value = default
        for uid in self.upgrades:
            u = UPGRADES[uid]
            if u["kind"] == kind and not u["shared"]:
                value *= u["value"]
        return value

    def has(self, uid):
        """Does this player own upgrade uid (flags: rule changes checked by id)?"""
        return uid in self.upgrades

    def wade_level(self):
        """Deepest snow level this player can walk on (Snowshoes raise it)."""
        return max([WADE_LEVEL] + [UPGRADES[u]["value"] for u in self.upgrades if UPGRADES[u]["kind"] == "wade"])

    def has_auto(self, item):
        return any(UPGRADES[u]["kind"] == "auto" and UPGRADES[u]["value"] == item for u in self.upgrades)

    def machine_mult(self, mid):
        """Product of this player's machine_mult upgrades for one machine kind."""
        mult = 1.0
        for uid in self.upgrades:
            u = UPGRADES[uid]
            if u["kind"] == "machine_mult" and u["machine"] == mid:
                mult *= u["value"]
        return mult

    def carry_mult(self, mid):
        """Product of this player's carry_mult upgrades that apply to one machine kind."""
        mult = 1.0
        for uid in self.upgrades:
            u = UPGRADES[uid]
            if u["kind"] == "carry_mult" and u["machine"] in (None, mid):
                mult *= u["value"]
        return mult

    def unit_rate(self, mid):
        """About how much snow per second one of this player's machines clears (before weather)."""
        return MACHINES[mid]["nominal"] * self.machine_mult(mid)

    def machine_rate(self, mid):
        """Snow per second of all this player's machines of one kind (before weather)."""
        return self.owned[mid] * self.unit_rate(mid) if self.owned[mid] else 0.0

    def base_rate(self):
        return sum(self.machine_rate(mid) for mid in MACHINES)

    def work_mult(self, blizzard):
        """Multiplier on this player's machines right now."""
        mult = FRENZY if self.frenzy > 0 else 1
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

    def sell(self, snow):
        """Snow a hauling machine unloaded at a drop point ($1 each; counted as cleared when dug)."""
        self.cash += snow
        self.earned += snow

    def sell_goods(self, value):
        value *= self.effect("goods_mult")
        self.cash += value
        self.earned += value
        self.goods_sold += value

    def pay(self, cost):
        if cost > self.cash + 1e-9:
            raise LobbyError(f"Not enough cash (need ${cost:,.0f}).")
        self.cash -= cost

    def buy_machine(self, mid, count):
        if mid not in MACHINES:
            raise LobbyError("Unknown machine.")
        if MACHINES[mid]["unique"]:
            raise LobbyError("That one can't be bought: it's found buried in the valley.")
        if self.owned[mid] + count > MAX_OWNED:
            raise LobbyError(f"At most {MAX_OWNED} of each machine.")
        self.pay(machine_cost(mid, self.owned[mid], count))
        self.owned[mid] += count

    def upgrade_visible(self, uid, shared_owned):
        u = UPGRADES[uid]
        if uid in self.upgrades or uid in shared_owned:
            return False
        if u["machine"]:
            return self.owned[u["machine"]] >= 1
        return self.earned >= u["cost"] * UNLOCK_SHARE

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
