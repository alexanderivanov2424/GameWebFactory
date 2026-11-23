"""Snowbound economy: one Player per seat (a character and its needs) and the team's shared Stores.

The team shares one Stores: cash, earned (cash ever earned: unlocks upgrades), diesel (one tank
for every machine), rations (whoever gets hungry eats from it), owned (the team's machines: one
fleet and one price curve, whoever pays) and upgrades (bought once, they apply to everyone).
Player.cash / earned / diesel / rations / owned / upgrades read and write the team's Stores, so
every rate, price and upgrade check is the same whichever player asks. Each player keeps only
their character: position, controls, food, warmth, frostbite/frenzy and their own stats.
Snow pays the team $1 per unit: at once for your shovel and machines that don't haul, when it is
unloaded at a drop point for hauling machines (hauling.py), and processed snow pays when its goods
sell (factory.py).

Player fields: name, color, stores (the team's Stores), cleared (snow this player and their
machines ever cleared), goods_sold ($ this player's sleds made from goods),
food 0-100,
warmth 0-100, frostbite / starving (bool), frenzy (seconds left of x FRENZY), clicks (swing
budget, refilled CLICKS_PER_SECOND per second).
Character (avatars.py): x, y (world coordinates), keys (held: up/down/left/right), aim (lot
[x, y] under the mouse or None), dig (dig button held), swing_cd, swinging (s left of the swing
animation).
"""

from gamekit import LobbyError

from .content import MACHINES, UNLOCK_SHARE, UPGRADES, machine_cost
from .world import WADE_LEVEL

PRICES = {"rations": 12, "diesel": 1.5, "logs": 8}
DELIVERY_FEE = 1.25
FRENZY = 5
CLICKS_PER_SECOND = 15
MAX_OWNED = 250
START = {"cash": 0, "rations": 3, "diesel": 20}


class Stores:
    """What the whole team shares. Each Player adds its START rations and diesel."""

    def __init__(self):
        self.cash = 0.0
        self.earned = 0.0
        self.diesel = 0.0
        self.rations = 0
        self.owned = {mid: 0 for mid in MACHINES}
        self.upgrades = set()


def _shared(name):
    return property(lambda self: getattr(self.stores, name), lambda self, value: setattr(self.stores, name, value))


class Player:
    cash = _shared("cash")
    earned = _shared("earned")
    diesel = _shared("diesel")
    rations = _shared("rations")
    owned = _shared("owned")
    upgrades = _shared("upgrades")

    def __init__(self, pid, name, color, x=0.0, y=0.0, stores=None):
        self.stores = stores if stores is not None else Stores()
        self.id = pid
        self.x = x
        self.y = y
        self.keys = ()
        self.aim = None
        self.dig = False
        self.swing_cd = 0.0
        self.swinging = 0.0
        self.name = name
        self.color = color
        self.cash += START["cash"]
        self.cleared = 0.0
        self.goods_sold = 0.0
        self.rations += START["rations"]
        self.diesel += float(START["diesel"])
        self.food = 100.0
        self.warmth = 100.0
        self.frostbite = False
        self.starving = False
        self.frenzy = 0.0
        self.clicks = CLICKS_PER_SECOND

    # --- multipliers -----------------------------------------------------------------

    def effect(self, kind, default=1):
        """Product of the team's upgrades of a kind (multipliers)."""
        value = default
        for uid in self.upgrades:
            u = UPGRADES[uid]
            if u["kind"] == kind:
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
            if u["kind"] == "carry_mult" and u["machine"] in (None, mid) and (
                    u["machine"] or MACHINES[mid]["kind"] != "sled"):
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
        """Litres per second the team's machines burn."""
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

    def upgrade_visible(self, uid):
        u = UPGRADES[uid]
        if uid in self.upgrades:
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
