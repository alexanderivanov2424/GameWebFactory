"""Orbit Run: the card deck and trick rules (no game state here).

Cards are ids: a suit letter and a value, e.g. "r3" (red 3) or "k4" (black 4).
    SUITS            {"r": "Red", ...}: four colour suits 1-9 and black trumps 1-4
    deck()           all 40 card ids
    suit(card), value(card)
    sort_key(card)   hand order: suit order of SUITS, then value
    deal(order, rng) {pid: sorted hand}: the shuffled deck dealt round-robin from order[0]
                     (players early in `order` may get 1 card more)
    playable(hand, led)        the cards in `hand` that may be played when `led` is the suit led
                               (None when leading): follow suit if you can, otherwise anything
    trick_winner(plays)        plays = [(pid, card), ...] in play order (first led): highest black
                               if any black was played, else the highest card of the suit led
"""

TRUMP = "k"
CAPTAIN_CARD = "k4"  # whoever holds it is the captain
SUITS = {"r": "Red", "b": "Blue", "y": "Yellow", "g": "Green", TRUMP: "Black"}
TOP = {"r": 9, "b": 9, "y": 9, "g": 9, TRUMP: 4}  # highest value per suit (all start at 1)
_ORDER = {s: i for i, s in enumerate(SUITS)}


def deck():
    return [f"{s}{v}" for s, top in TOP.items() for v in range(1, top + 1)]


def suit(card):
    return card[0]


def value(card):
    return int(card[1:])


def name(card):
    return f"{SUITS[suit(card)]} {value(card)}"


def sort_key(card):
    return (_ORDER[suit(card)], value(card))


def deal(order, rng):
    cards = deck()
    rng.shuffle(cards)
    hands = {pid: [] for pid in order}
    for i, card in enumerate(cards):
        hands[order[i % len(order)]].append(card)
    return {pid: sorted(hand, key=sort_key) for pid, hand in hands.items()}


def playable(hand, led):
    if led is not None:
        following = [c for c in hand if suit(c) == led]
        if following:
            return following
    return list(hand)


def trick_winner(plays):
    led = suit(plays[0][1])
    trumps = [p for p in plays if suit(p[1]) == TRUMP]
    pool = trumps or [p for p in plays if suit(p[1]) == led]
    return max(pool, key=lambda p: value(p[1]))[0]
