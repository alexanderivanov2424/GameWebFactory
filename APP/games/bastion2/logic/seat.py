"""Bastion 2: Seat, one player's deck, hand, play area and resources.

    seat.deck        gamekit Deck of card instances {"uid", "card"} (+ "temp": True for cards made
                     by an action, which vanish instead of going to the discard pile)
    seat.hand        [instance]; kept cards stay here at the end of a turn
    seat.play        [instance] played this turn (shown in the play area, discarded at the end)
    seat.temp        {temporary resource: n} this turn's counters
    seat.food        permanent, at most food_cap(board)
    seat.population  permanent total; seat.pop_used is what this turn's builds took
    seat.actions     action points left this turn
    seat.used        cells of structures whose action was used this turn
    seat.pending     {cell: {"inst", "paid", "skip": set of optional add indexes}} builds played
                     this turn (on the board as pending structures)
    seat.setup       how many setup pieces are placed; seat.done: turn ended (play together)

    seat.missing(cost) -> reason or ""     seat.pay(cost)     seat.refund(cost)
    seat.gain(gains, food_cap)             seat.take(uid) -> instance (removed from the hand)
"""

from .content import ICONS, RESOURCES


class Seat:
    def __init__(self, pid, name, color, deck):
        self.pid = pid
        self.name = name
        self.color = color
        self.deck = deck
        self.hand = []
        self.play = []
        self.temp = {}
        self.food = 0
        self.population = 0
        self.pop_used = 0
        self.actions = 0
        self.used = set()
        self.pending = {}
        self.setup = 0
        self.done = False

    def available(self, key):
        if key == "population":
            return max(0, self.population - self.pop_used)
        if key == "food":
            return self.food
        return self.temp.get(key, 0)

    def missing(self, cost):
        short = [f"{n - self.available(k)}{ICONS.get(k, k)}" for k, n in cost.items() if self.available(k) < n]
        if not short:
            return ""
        names = [RESOURCES[k]["name"].lower() for k, n in cost.items() if self.available(k) < n]
        return f"Not enough {' and '.join(names)} (need {' '.join(short)} more)."

    def pay(self, cost):
        for key, n in cost.items():
            if key == "population":
                self.pop_used += n
            elif key == "food":
                self.food -= n
            else:
                self.temp[key] = self.temp.get(key, 0) - n

    def refund(self, cost):
        for key, n in cost.items():
            if key == "population":
                self.pop_used = max(0, self.pop_used - n)
            elif key == "food":
                self.food += n
            else:
                self.temp[key] = self.temp.get(key, 0) + n

    def gain(self, gains, food_cap):
        for key, n in gains.items():
            if key == "food":
                self.food = min(food_cap, self.food + n)
            else:
                self.temp[key] = self.temp.get(key, 0) + n

    def find(self, uid):
        return next((inst for inst in self.hand if inst["uid"] == uid), None)

    def take(self, uid):
        inst = self.find(uid)
        if inst is not None:
            self.hand.remove(inst)
        return inst
