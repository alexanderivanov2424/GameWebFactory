"""Weather, the shared cabin stove, and each player's food and warmth.

Weather cycles clear -> warning (WARNING s) -> blizzard -> clear. During a blizzard: machines
work at 75%, the stove burns BLIZZARD_BURN x logs, warmth drops faster with the stove out,
deliveries stop, and every second snow falls back on some reached lots (DUST_SHARE of them,
DUST_FRACTION of their starting depth, x the team's dust upgrades).

Stove: burns STOVE_BURN logs/s (+50% per extra player) from the shared woodpile. Lit: everyone
warms WARM_UP/s. Out: everyone loses COLD/s (BLIZZARD_COLD in a blizzard; x the survival
setting and Thermal Suit), STARVING_COLD more while starving.
Food: drops FOOD_DRAIN/s and CLICK_FOOD per click (x setting, x Big Thermos). At or below
EAT_AT a ration is eaten automatically (+RATION_FOOD).
Needs: warmth 0 -> frostbite (no clicking, machines at half speed) until warmth is back to
THAW_AT; food 0 -> starving (clicks at 20%, colder).
Deliveries (upgrades, 25% fee, not in blizzards): rations kept at 5, a minute of diesel when
under 30 s, the woodpile kept at 20 logs.
"""

from gamekit import LobbyError

from .content import UPGRADES
from .economy import DELIVERY_FEE

WARNING = 20
FIRST_CLEAR = (240, 360)
CLEAR = (150, 300)
BLIZZARD = (40, 70)
BLIZZARD_BURN = 2.5
DUST_SHARE = 0.003
DUST_FRACTION = 0.15
STOVE_BURN = 0.04
START_LOGS = 30
WARM_UP = 1.5
COLD = 0.6
BLIZZARD_COLD = 1.5
STARVING_COLD = 0.3
FOOD_DRAIN = 0.25
CLICK_FOOD = 0.02
EAT_AT = 70
RATION_FOOD = 30
THAW_AT = 20
HARSHNESS = {"easy": 0.5, "normal": 1.0, "harsh": 1.8}


class Weather:
    def __init__(self, rng):
        self.rng = rng
        self.kind = "clear"
        self.left = rng.uniform(*FIRST_CLEAR)
        self.dust_timer = 0.0

    @property
    def blizzard(self):
        return self.kind == "blizzard"

    def step(self, dt):
        """Advance the clock; returns the new kind when it changes, else None."""
        self.left -= dt
        if self.left > 0:
            return None
        if self.kind == "clear":
            self.kind, self.left = "warning", WARNING
        elif self.kind == "warning":
            self.kind, self.left = "blizzard", self.rng.uniform(*BLIZZARD)
        else:
            self.kind, self.left = "clear", self.rng.uniform(*CLEAR)
        return self.kind

    def public(self):
        return {"kind": self.kind, "left": int(self.left)}


def shared_mult(match, kind):
    value = 1.0
    for uid in match.shared_upgrades:
        if UPGRADES[uid]["kind"] == kind:
            value *= UPGRADES[uid]["value"]
    return value


def stove_burn(match):
    burn = STOVE_BURN * (1 + 0.5 * (len(match.players) - 1)) * shared_mult(match, "stove")
    return burn * (BLIZZARD_BURN if match.weather.blizzard else 1)


def step(match, dt):
    harsh = match.harshness
    blizzard = match.weather.blizzard
    match.woodpile = max(0.0, match.woodpile - stove_burn(match) * dt)
    lit = match.woodpile > 0
    for p in match.players.values():
        p.frenzy = max(0.0, p.frenzy - dt)
        p.diesel = max(0.0, p.diesel - p.diesel_use() * dt)
        p.food = max(0.0, p.food - FOOD_DRAIN * harsh * p.effect("food_drain") * dt)
        if p.food <= EAT_AT and p.rations > 0:
            p.rations -= 1
            p.food = min(100.0, p.food + RATION_FOOD)
        p.starving = p.food <= 0
        if lit:
            p.warmth += WARM_UP * dt
        else:
            p.warmth -= (BLIZZARD_COLD if blizzard else COLD) * harsh * p.effect("warm_loss") * dt
        if p.starving:
            p.warmth -= STARVING_COLD * harsh * dt
        p.warmth = max(0.0, min(100.0, p.warmth))
        if p.warmth <= 0 and not p.frostbite:
            p.frostbite = True
            match.say(f"{p.name} has frostbite! Keep the stove burning.")
        elif p.frostbite and p.warmth >= THAW_AT:
            p.frostbite = False


def clicked(match, player):
    player.food = max(0.0, player.food - CLICK_FOOD * match.harshness * player.effect("food_drain"))


def dust(match):
    """One second of blizzard snowfall on cleared ground."""
    world = match.world
    lots = world.reached_list
    if not lots:
        return
    fraction = DUST_FRACTION * shared_mult(match, "dust")
    for _ in range(max(2, int(len(lots) * DUST_SHARE * match.harshness))):
        world.dust(match.rng.choice(lots), fraction)


def deliveries(match):
    """Once a second outside blizzards: automatic purchases from delivery upgrades."""
    for p in match.players.values():
        if p.has_auto("rations") and p.rations < 5:
            _try(p.buy_supply, "rations", 5 - p.rations)
        use = p.diesel_use()
        if p.has_auto("diesel") and use > 0 and p.diesel < 30 * use:
            _try(p.buy_supply, "diesel", round(60 * use - p.diesel, 1))
        if p.has_auto("logs") and match.woodpile < 20:
            match.woodpile += _try(p.buy_supply, "logs", 20 - int(match.woodpile))


def _try(buy, item, qty):
    """Buy with the delivery fee; 0 if the player can't afford it right now."""
    try:
        return buy(item, qty, DELIVERY_FEE)
    except LobbyError:
        return 0
