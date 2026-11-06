"""Peruvian Silver: a push-your-luck card game in a silver mine.

Each player has a chest (silver they've banked), a backpack (silver carried during the
current expedition), a fountain pool, and a hand of cards. The game lasts a number of
expeditions (a host setting). Every expedition:

1. Reveal the top card of the deck onto a path and resolve it (see "Deck cards").
2. Everyone still exploring secretly plays a card from their hand. When all have played,
   the cards are revealed together (see "Hand cards"). Players at camp holding Seconds may
   also play it during this step; nobody waits for them.
3. If anyone is still exploring, go back to step 1. Otherwise the expedition is over.
The expedition also ends when a hazard strikes and nobody survives it, or when the deck
runs out (then everyone still inside returns safely as if they'd left together).

Paths: players explore along a path, the row of cards revealed for them. Everyone starts
on the main path. Treasure is split, and leftovers are collected, only within a path.
Hazards count across all paths and strike everyone exploring. Each turn, every open path
gets a card, even one nobody is on.

Forks: after the decision that follows a Fork, its path is closed: every card on it
except the Fork and hazards is discarded (silver left on them is lost; untaken relics stay
in the deck), and two cards are revealed to start a left and a right path. Everyone still
exploring that path then decides together: Stay = go left, Leave = go right. The cards
flip, then the first card of each new path resolves for whoever took it, and play goes on.

Deck cards (cards/deck/*.json, "type" field):
  treasure  Its value is split between everyone exploring that path (Gremlins count as
            extra people and keep their share on their card). The remainder stays on it.
  hazard    Harmless the first time. When another copy is revealed (on any path) it
            strikes: one copy leaves the deck for good, and everyone exploring loses their
            backpack, unless they spend a matching charm. If nobody does, the expedition ends.
  charm     A relic (see below) that protects against one hazard ("protects").
  idol      A relic worth its "value" at the end of the game.
  relic     A relic that puts a hand card ("gives") into your hand: Flee, Stash, Seconds,
            Guide Dog.
  mirror    Becomes a copy of the next card revealed on its path, and resolves as that card,
            right after it. It never copies a Fork: the Fork's split discards it first.
  gremlin   Shares in every treasure split on its path; its share stays on the card.
  fountain  Doubles the fountain pool of every player still exploring (any path; not those at
            camp or knocked out). Then everyone exploring that path
            secretly moves silver between their backpack and their stash.
  pot       Starts empty and gains "growth" silver every time a later card is revealed.
  fork      Splits its path in two (see "Forks").
  altar     Everyone exploring its path puts their whole backpack on it; leavers split it.
  blessing  Everyone exploring (any path) doubles their backpack.
  death     Unavoidable: everyone exploring (any path) loses their backpack; the expedition ends.
  robbery   The player(s) with the most silver in their chest each choose one held relic
            (charm, idol or relic card) to lose.
  gem       Auctioned at once: every player bids from their chest, in turn (see "Gems").
Cards with "blackSquare" show a black square on their back (Death, Blessing).

Gems: when a gem is revealed, every player gets one turn to bid, in seat order (the first
bidder rotates each auction). A bid must beat the highest so far, up to your chest; 0 passes.
The highest bidder pays (the silver is gone) and takes the gem; nobody else pays. If
everyone passes, the gem stays in the deck. At the end of the round, each gem is used and
gone (gems won in the last round do nothing):
  red   pick 3 of 5 random cards from cards/pool.json to add to the deck (secret).
  blue  pick any mark from cards/marks.json; it goes on the back of 3 random deck cards,
        and only you see which.
Relics stay on their card. Only a player who leaves *alone* takes them (along with every
other relic on their path); a taken relic leaves the deck. Who holds what is public.

Hand cards (cards/hand/*.json, "type" field), revealed together:
  stay    Keep exploring.
  stash   Keep exploring, but move your backpack into your chest first. Used up.
  guard   (Guide Dog) Keep exploring. If the next card makes a hazard strike, you leave
          with your backpack banked instead (no leftovers from the cards); otherwise you
          just stay. Used up.
  flee    Leave before the Leave players: fleers split the leftovers on their path first,
          and a lone fleer takes the relics first. Used up.
  leave   Leave: split what's left on your path, bank your backpack. A lone leaver takes
          the remaining relics.
  backstab  (Backstab) Leave, and rob everyone who plays Leave on your path that turn: their
          backpacks and leftover shares are split evenly between the back-stabbers (the
          remainder stays on the cards). Fleers have already gone and are safe. Used up.
  peek    (Crystal Ball) Use any time during the game, not as a turn: see the next 3 cards
          of the deck (only you). Used up.
  return  (Seconds) Only while at camp, during a turn while others are still exploring:
          go back in with an empty backpack when the cards are revealed. Used up. When
          several paths are open, you pick which one to join.

The deck carries over between expeditions and is reshuffled at the start of each one,
starting from cards/starting-deck.json. Each card in it is a separate instance that can
carry marks.

Marking (between expeditions): 3 emoji are drawn from cards/marks.json, the same for
everyone. Each player is privately shown 3 different random cards from the deck (faces,
without anyone's earlier marks) and secretly puts one of the emoji on the back of one of
them. Marks stay for the rest of the game; everyone sees the marks on the back of the top
card of the deck (and on revealed cards). Only you know which marks you placed.

Final score: chest + idol values + 5 for every other relic still held (unused charms and
relic cards). Silver left in a fountain pool doesn't count.

Settings:       {"expeditions": 5}
Game messages:  {"action": "play", "card": "<hand card id>"}       (choosing stage)
                {"action": "play", "card": "<seconds>", "path": n}  (Seconds, several paths)
                {"action": "play", "card": "<stay|leave>"}          (fork stage: left|right)
                {"action": "charm", "use": true|false}              (charm stage)
                {"action": "fountain", "amount": n}  (+ into the stash, - out of it)
                {"action": "mark", "uid": n, "emoji": "<one of markEmojis>"}  (marking stage)
                {"action": "rob", "kind": "charm|idol|relic", "card": "<card id>"}  (robbery stage)
                {"action": "bid", "amount": n}   (auction stage, your turn; 0 passes)
                {"action": "gem", "cards": [ids]} / {"action": "gem", "emoji": e}  (gem stage)
                {"action": "peek"}               (use a Crystal Ball, any time)
"""

import random

from gamekit import PLAYING, Int, LobbyError, LobbyGame, SecretChoices

from .cards import DECK_CARDS, HAND_CARDS, MARK_CHOICES, MARKS, STARTING_DECK, random_pool_cards

RED_GEM_OFFER, RED_GEM_PICKS = 5, 3  # a Red Gem shows 5 pool cards; add 3
BLUE_GEM_CARDS = 3  # a Blue Gem's mark goes on 3 random deck cards
PEEK_CARDS = 3  # a Crystal Ball shows the next 3 cards
RELIC_TYPES = {"charm", "idol", "relic"}  # stay on the path; a player who leaves alone takes them
EXPLORER_PLAYS = {"stay", "leave", "flee", "stash", "guard", "backstab"}  # what someone exploring may play

REVEAL_DELAY = 2.5  # seconds to show the revealed cards before the next card is drawn
END_DELAY = 5  # seconds to show how an expedition ended before marking starts
OFFER_SIZE = 3  # deck cards each player is shown when marking
RELIC_BONUS = 5  # end-of-game value of each unused charm or relic card

# Seat statuses
EXPLORING, CAMP, BUSTED, GONE = "exploring", "camp", "busted", "gone"
# Stages within the "playing" phase
CHOOSING, REVEAL, OVER, MARKING = "choosing", "reveal", "over", "marking"
ROBBERY = "robbery"  # the richest player(s) choosing a relic to lose
AUCTION = "auction"  # players bidding for a gem, one at a time
GEM = "gem"  # between rounds: a gem holder using their gem
CHARM, SAVED = "charm", "saved"  # a hazard struck: charm holders deciding / survivors shown
FOUNTAIN = "fountain"  # explorers moving silver to or from their fountain pool
FORK, FORKED = "fork", "forked"  # explorers at a fork picking left/right / their picks shown
SIDES = ("left", "right")
FORK_PLAYS = {"stay": "left", "leave": "right"}  # at a fork, Stay goes left and Leave goes right
# How resolving a card went
NEXT, WAIT, ENDED = "next", "wait", "ended"


def starting_deck():
    return [card_id for card_id, copies in STARTING_DECK.items() for _ in range(copies)]


def starting_hand():
    return [card_id for card_id, card in HAND_CARDS.items() for _ in range(card["starting"])]


def effective(entry):
    """The card a path entry acts as: a Mirror that has copied a card acts as that card."""
    return entry.get("as") or entry["card"]


def kind(entry):
    return DECK_CARDS[effective(entry)]["type"]


class Game(LobbyGame):
    MIN_PLAYERS = 2
    MAX_PLAYERS = 8
    SETTINGS = {"expeditions": Int("Expeditions", default=5, low=1, high=10)}
    ACTIONS = {
        "play": "on_play", "charm": "on_charm", "fountain": "on_fountain", "mark": "on_mark",
        "rob": "on_rob", "bid": "on_bid", "gem": "on_gem", "peek": "on_peek",
    }

    def __init__(self, room):
        super().__init__(room)
        self.reset_game()

    # --- Lobby -----------------------------------------------------------------

    def start_check(self):
        if not STARTING_DECK:
            return "This game's cards aren't set up (empty starting deck). Ask the site admin to check cards/starting-deck.json."
        types = {HAND_CARDS[c]["type"] for c in starting_hand()}
        if not {"stay", "leave"} <= types:
            return "This game's cards aren't set up (no Stay or Leave card). Ask the site admin to check the card files."
        return None

    # --- Game state ------------------------------------------------------------

    def reset_game(self):
        self.order = []  # public ids in seat order
        self.seats = {}  # public id -> public seat info (see start_game)
        self.hands = {}  # public id -> [hand card ids]  (private)
        self.expedition = 0
        self.expeditions = 0
        # Card instances: {"uid", "card", "marks": [emoji]}. deck_list is every card in the deck
        # (it carries over between expeditions); deck is this expedition's draw pile (top = end).
        self.deck_list = []
        self.deck = []
        self.next_uid = 0
        self.offers = {}  # public id -> instance uids shown while marking (private)
        self.mark_emojis = []  # the emoji everyone may use this marking round
        self.my_marks = {}  # public id -> [{"card", "emoji"}] marks you placed (private)
        self.robbery = None  # {"card", "choosers"} while the richest choose what to lose
        self.auction = None  # see start_auction (public)
        self.auctions_held = 0  # rotates who bids first
        self.gem_queue = []  # (pid, gem card id) still to use at the end of the round
        self.gem_turn = None  # {"player", "gem", "color"} using a gem now (public)
        self.gem_options = []  # Red Gem: pool cards offered to the holder (private)
        self.peeks = {}  # pid -> [uids] seen with a Crystal Ball this expedition (private)
        self.paths = []  # see new_path(); entry: {"card", "as", "left", "step", "resolved"?, "taken"?}
        self.fork_options = {}  # forked path id -> [child path ids] while explorers pick a side
        self.return_paths = {}  # Seconds players -> the path they asked to join (secret until reveal)
        self.queue = []  # (path id, entry) still to resolve after the latest reveal
        self.stage = None
        self.step = 0  # counts revealed cards over the whole game (for client animations)
        self.choices = SecretChoices()
        self.ending = None  # how the current expedition ended
        self.strike = None  # the hazard that struck: {"card", "holders", then "users", "lost", "removed"}
        self.fountain_path = None  # path whose explorers are using a fountain
        self.guarded = set()  # played a Guide Dog this turn: a strike sends them home safely
        self.log = []

    def start_game(self):
        players = self.players
        self.order = [p.id for p in players]
        self.seats = {
            p.id: {
                "name": p.name,
                "chest": 0,
                "backpack": 0,
                "fountain": 0,  # fountain pool: doubles at every fountain
                "status": EXPLORING,
                "path": 0,
                "charms": [],  # charm deck card ids held
                "idols": [],  # idol deck card ids held
                "relics": [],  # relic deck card ids held (their hand cards are in the hand)
                "gems": [],  # gem deck card ids won at auction; used at the end of the round
            }
            for p in players
        }
        self.hands = {p.id: starting_hand() for p in players}
        self.my_marks = {p.id: [] for p in players}
        self.expeditions = self.settings["expeditions"]
        self.deck_list = [self.new_instance(card_id) for card_id in starting_deck()]
        self.begin_expedition(1)

    def game_state(self):
        return {
            "expedition": self.expedition,
            "expeditions": self.expeditions,
            "stage": self.stage,
            "step": self.step,
            "deckCount": len(self.deck),
            "deckSize": len(self.deck_list),
            # Only the back of the top card is public: its back design, player marks and black square.
            "deckTop": self.back_of(self.deck[-1]) if self.deck else None,
            "markEmojis": self.mark_emojis if self.stage == MARKING else [],
            "markPool": MARKS,
            "explorerPlays": sorted(EXPLORER_PLAYS),  # the client reads this rather than keeping its own copy
            "robbery": self.robbery if self.stage == ROBBERY else None,
            "auction": self.auction if self.stage == AUCTION else None,
            "gemTurn": self.gem_turn if self.stage == GEM else None,
            "paths": self.paths,
            "order": self.order,
            "seats": {
                pid: {**seat, "handSize": len(self.hands.get(pid, []))} for pid, seat in self.seats.items()
            },
            "plays": self.choices.public(),
            "ending": self.ending,
            "strike": self.strike,
            "fountainPath": self.fountain_path if self.stage == FOUNTAIN else None,
            "forkOptions": self.fork_options if self.stage == FORK else {},
            "log": self.log,
            "deckCards": DECK_CARDS,
            "handCards": HAND_CARDS,
            "timing": {"reveal": REVEAL_DELAY, "end": END_DELAY},
        }

    def private_state(self, member):
        if member.id not in self.seats:
            return None
        pick = self.choices.choice(member.id)
        return {
            "hand": self.hands.get(member.id, []),
            "played": pick if self.stage in (CHOOSING, REVEAL) else None,  # your hand card this turn
            "charmChoice": pick if self.stage == CHARM else None,  # True/False once you've decided
            "fountainChoice": pick if self.stage == FOUNTAIN else None,  # amount once you've decided
            "forkChoice": pick if self.stage == FORK else None,  # "left"/"right" once you've decided
            "returnPath": self.return_paths.get(member.id) if self.stage == CHOOSING else None,
            # Cards you may mark: faces only, never anyone's marks.
            "offers": [
                {"uid": uid, "card": self.instance(uid)["card"]} for uid in self.offers.get(member.id, [])
            ] if self.stage == MARKING else [],
            "picked": pick if self.stage == MARKING else None,  # {"uid", "emoji"} once you've marked
            "robChoice": pick if self.stage == ROBBERY else None,
            "gemOptions": self.gem_options if self.stage == GEM and (self.gem_turn or {}).get("player") == member.id else [],
            # Crystal Ball: the cards you foresaw that haven't been drawn yet, next first.
            "vision": [self.deck_card_at(uid) for uid in self.peeks.get(member.id, []) if self.in_draw_pile(uid)],
            "myMarks": self.my_marks.get(member.id, []),
        }

    def explorers(self, path=None):
        return [
            pid for pid in self.order
            if self.seats[pid]["status"] == EXPLORING and (path is None or self.seats[pid]["path"] == path)
        ]

    def new_instance(self, card_id):
        self.next_uid += 1
        return {"uid": self.next_uid, "card": card_id, "marks": []}

    def instance(self, uid):
        return next((i for i in self.deck_list if i["uid"] == uid), None)

    def remove_instance(self, uid=None, card_id=None):
        """Take a card out of the deck for good: that exact instance, or else any copy of card_id."""
        found = self.instance(uid) if uid is not None else None
        if found is None or (card_id is not None and found["card"] != card_id):
            found = next((i for i in self.deck_list if i["card"] == card_id), None)
        if found is not None:
            self.deck_list.remove(found)
        return found is not None

    def in_draw_pile(self, uid):
        return any(i["uid"] == uid for i in self.deck)

    def deck_card_at(self, uid):
        return next((i["card"] for i in self.deck if i["uid"] == uid), None)

    @staticmethod
    def back_of(inst):
        card = DECK_CARDS[inst["card"]]
        return {"back": card["back"], "marks": list(inst["marks"]), "blackSquare": card["blackSquare"]}

    def active(self):
        return [pid for pid in self.order if self.seats[pid]["status"] != GONE]

    def path_cards(self, path):
        return self.paths[path]["cards"]

    def new_path(self, parent=None, side=None):
        """Paths are numbered by position in self.paths. A forked path is closed: no more draws."""
        path = {"id": len(self.paths), "cards": [], "parent": parent, "side": side, "closed": False, "forking": False}
        self.paths.append(path)
        return path

    def open_paths(self):
        """Paths that haven't forked, in order. Each turn every one of them gets a card, even
        with nobody on it (treasure then stays on the card; hazards still count for everyone)."""
        return [p["id"] for p in self.paths if not p["closed"]]

    # --- Expeditions -------------------------------------------------------------

    def begin_expedition(self, number):
        self.expedition = number
        self.deck = list(self.deck_list)
        random.shuffle(self.deck)  # Reshuffled every expedition.
        self.paths = []
        self.new_path()
        self.fork_options = {}
        self.return_paths = {}
        self.peeks = {}
        self.queue = []
        self.ending = None
        self.strike = None
        self.guarded = set()
        for pid in self.active():
            seat = self.seats[pid]
            seat["status"] = EXPLORING
            seat["backpack"] = 0
            seat["path"] = 0
        self.log.append({"type": "expedition", "number": number})
        self.draw()

    def draw(self):
        """Reveal the next card, resolve it, then let explorers choose (unless it ended things)."""
        self.choices = SecretChoices()
        if not self.deck:
            groups = []
            for path in [p["id"] for p in self.paths]:
                pids = self.explorers(path)
                if pids:
                    share, banked, relics = self.return_to_camp(pids, path)
                    groups.append({"players": pids, "share": share, "banked": banked, "relics": relics})
            self.log.append({"type": "empty", "groups": groups})
            self.end_expedition({"reason": "empty"})
            return
        # Every open path gets a card, in path order, while the deck lasts.
        self.queue = []
        for path in self.open_paths():
            if not self.deck:
                break
            self.reveal_onto(path)
        self.continue_resolving()

    def reveal_onto(self, path):
        """Turn the top card onto `path` and queue it (and any waiting Mirrors) to resolve."""
        cards = self.path_cards(path)
        for entry in cards:  # Pots grow every turn.
            if kind(entry) == "pot":
                entry["left"] += DECK_CARDS[effective(entry)]["growth"]
        inst = self.deck.pop()
        card_id = inst["card"]
        self.step += 1
        entry = {"card": card_id, "uid": inst["uid"], "marks": list(inst["marks"]), "as": None, "left": 0, "step": self.step}
        waiting_mirrors = [e for e in cards if DECK_CARDS[e["card"]]["type"] == "mirror" and e["as"] is None]
        cards.append(entry)
        self.queue.append((path, entry))
        if DECK_CARDS[card_id]["type"] not in ("mirror", "fork"):
            # Waiting Mirrors become copies of this card and resolve right after it (the card
            # itself always resolves first). A Fork is never copied: its split discards the Mirror.
            for mirror in waiting_mirrors:
                mirror["as"] = card_id
                self.queue.append((path, mirror))

    def continue_resolving(self):
        """Resolve queued path entries. Stops if one needs a decision or ends the expedition."""
        while self.queue:
            path, entry = self.queue.pop(0)
            outcome = self.resolve(path, entry)
            if outcome != NEXT:
                if outcome == ENDED:
                    self.queue = []
                return
        self.start_choosing()

    def start_choosing(self):
        explorers = self.explorers()
        if not explorers:
            self.end_expedition({"reason": "camp"})
            return
        self.stage = CHOOSING
        self.guarded = set()  # A Guide Dog only covers the card(s) revealed right after it.
        # Players at camp holding Seconds may play it, but nobody waits for them.
        returners = [
            pid for pid in self.active()
            if self.seats[pid]["status"] == CAMP and any(HAND_CARDS[c]["type"] == "return" for c in self.hands[pid])
        ]
        self.choices = SecretChoices(explorers, optional_ids=returners)

    def charm_for(self, pid, hazard):
        """The charm pid holds that protects against `hazard`, or None."""
        return next((c for c in self.seats[pid]["charms"] if DECK_CARDS[c]["protects"] == hazard), None)

    def resolve(self, path, entry):
        """Apply a revealed (or newly mirrored) path entry. Returns NEXT, WAIT or ENDED."""
        entry["resolved"] = True
        card_id = effective(entry)
        card = DECK_CARDS[card_id]
        mirrored = entry["as"] is not None
        logged = {"card": card_id, "mirror": mirrored}
        cards = self.path_cards(path)
        kind_ = card["type"]

        if kind_ == "treasure":
            explorers = self.explorers(path)
            gremlins = [e for e in cards if e is not entry and e.get("resolved") and kind(e) == "gremlin"]
            sharers = len(explorers) + len(gremlins)
            if not sharers:
                entry["left"] = card["value"]
                share, left = 0, card["value"]
            else:
                share, left = divmod(card["value"], sharers)
                for pid in explorers:
                    self.seats[pid]["backpack"] += share
                for gremlin in gremlins:
                    gremlin["left"] += share
                entry["left"] = left
            self.log.append({"type": "treasure", **logged, "share": share, "left": left, "gremlins": len(gremlins)})
            return NEXT

        if kind_ == "hazard":
            copies = sum(
                1 for p in self.paths for e in p["cards"] if e.get("resolved") and effective(e) == card_id
            )
            if copies < 2:
                self.log.append({"type": "hazard", **logged})
                return NEXT
            explorers = self.explorers()  # Hazards strike every path.
            # Guide Dog players leave safely, so they're not asked about charms.
            holders = [pid for pid in explorers if pid not in self.guarded and self.charm_for(pid, card_id)]
            self.strike = {"card": card_id, "uid": entry.get("uid"), "holders": holders}
            if holders:
                self.stage = CHARM
                self.choices = SecretChoices(holders)
                return WAIT
            return self.resolve_strike([])

        if kind_ == "fountain":
            doubled = {}
            for pid in self.explorers():  # Only players still in the round (any path) double.
                seat = self.seats[pid]
                if seat["fountain"]:
                    doubled[pid] = seat["fountain"]
                    seat["fountain"] *= 2
            self.log.append({"type": "fountain", **logged, "doubled": doubled})
            deciders = [pid for pid in self.explorers(path) if self.seats[pid]["backpack"] or self.seats[pid]["fountain"]]
            if deciders:
                self.stage = FOUNTAIN
                self.fountain_path = path
                self.choices = SecretChoices(deciders)
                return WAIT
            return NEXT

        if kind_ == "altar":
            given = {}
            for pid in self.explorers(path):
                seat = self.seats[pid]
                given[pid] = seat["backpack"]
                entry["left"] += seat["backpack"]
                seat["backpack"] = 0
            self.log.append({"type": "altar", **logged, "given": given})
            return NEXT

        if kind_ == "blessing":
            doubled = {}
            for pid in self.explorers():
                seat = self.seats[pid]
                doubled[pid] = seat["backpack"]
                seat["backpack"] *= 2
            self.log.append({"type": "blessing", **logged, "doubled": doubled})
            return NEXT

        if kind_ == "death":  # Unavoidable: no charm or Guide Dog helps.
            lost = {}
            for pid in self.explorers():
                seat = self.seats[pid]
                lost[pid] = seat["backpack"]
                seat["backpack"] = 0
                seat["status"] = BUSTED
            self.log.append({"type": "death", **logged, "lost": lost})
            self.end_expedition({"reason": "death", "card": card_id, "lost": lost})
            return ENDED

        if kind_ == "robbery":
            active = self.active()
            richest = max((self.seats[pid]["chest"] for pid in active), default=0)
            leaders = [pid for pid in active if richest > 0 and self.seats[pid]["chest"] == richest]
            choosers = [pid for pid in leaders if self.losable(pid)]
            self.log.append({"type": "robbery", **logged, "leaders": leaders, "choosers": choosers})
            if not choosers:
                return NEXT
            self.stage = ROBBERY
            self.robbery = {"card": card_id, "leaders": leaders, "choosers": choosers}
            self.choices = SecretChoices(choosers)
            return WAIT

        if kind_ == "gem":
            self.log.append({"type": "gem", **logged})
            return self.start_auction(entry)

        if kind_ == "fork":
            self.paths[path]["forking"] = True  # Splits after the coming decision.
            self.log.append({"type": "fork", **logged, "path": path})
            return NEXT
        if kind_ in RELIC_TYPES:
            self.log.append({"type": "relic", **logged})
        elif kind_ in ("mirror", "gremlin", "pot"):
            self.log.append({"type": kind_, **logged})
        return NEXT

    # --- Gem auctions ------------------------------------------------------------------

    def start_auction(self, entry):
        """Every player bids once from their chest, in seat order (rotating first bidder)."""
        active = self.active()
        if not active:
            return NEXT
        first = self.auctions_held % len(active)
        self.auctions_held += 1
        self.auction = {
            "card": effective(entry), "uid": entry.get("uid"), "step": entry["step"],
            "order": active[first:] + active[:first], "turn": 0, "bids": {}, "high": 0, "leader": None,
        }
        self.stage = AUCTION
        self.choices = SecretChoices()
        self.skip_hopeless_bidders()
        return WAIT if self.auction else NEXT

    def bidder(self):
        a = self.auction
        return a["order"][a["turn"]] if a and a["turn"] < len(a["order"]) else None

    def skip_hopeless_bidders(self):
        """Players who can't beat the highest bid pass automatically; finish when everyone's done."""
        a = self.auction
        while a["turn"] < len(a["order"]):
            pid = a["order"][a["turn"]]
            seat = self.seats[pid]
            if seat["status"] != GONE and seat["chest"] > a["high"]:
                return
            a["bids"][pid] = 0
            a["turn"] += 1
        self.finish_auction()

    def place_bid(self, pid, amount):
        if self.stage != AUCTION or self.bidder() != pid:
            raise LobbyError("It's not your turn to bid.")
        a = self.auction
        chest = self.seats[pid]["chest"]
        if type(amount) is not int or amount < 0 or amount > chest:
            raise LobbyError(f"You can bid at most {chest} (your chest), or pass.")
        if amount and amount <= a["high"]:
            raise LobbyError(f"Bid more than {a['high']}, or pass.")
        a["bids"][pid] = amount
        if amount:
            a["high"], a["leader"] = amount, pid
        a["turn"] += 1
        self.skip_hopeless_bidders()

    def finish_auction(self):
        a = self.auction
        winner = a["leader"]
        if winner:
            self.seats[winner]["chest"] -= a["high"]  # The winning bid is gone; losers keep theirs.
            self.seats[winner]["gems"].append(a["card"])
            entry = next((e for p in self.paths for e in p["cards"] if e["step"] == a["step"]), None)
            if entry is not None:
                entry["taken"] = winner
                self.remove_instance(entry.get("uid"))
        self.log.append({"type": "auction", "card": a["card"], "bids": a["bids"], "winner": winner, "price": a["high"]})
        self.auction = None
        self.continue_resolving()

    def resolve_strike(self, users):
        """A hazard struck. `users` spent a charm and survive; other explorers lose their backpack."""
        card_id = self.strike["card"]
        users = [pid for pid in users if self.seats[pid]["status"] == EXPLORING and self.charm_for(pid, card_id)]
        lost = {}
        guided = {}
        for pid in self.explorers():
            seat = self.seats[pid]
            if pid in self.guarded:  # Guide Dog: home safely with the backpack, no leftovers.
                guided[pid] = seat["backpack"]
                seat["chest"] += seat["backpack"]
                seat["backpack"] = 0
                seat["status"] = CAMP
                continue
            if pid in users:
                seat["charms"].remove(self.charm_for(pid, card_id))
                continue
            lost[pid] = seat["backpack"]
            seat["backpack"] = 0
            seat["status"] = BUSTED
        # The hazard that struck loses one copy from the deck for later expeditions.
        removed = self.remove_instance(self.strike.get("uid"), card_id)
        self.strike.update({"users": users, "lost": lost, "removed": removed, "guided": guided})
        self.choices = SecretChoices()
        if users:
            self.stage = SAVED
            self.log.append({"type": "saved", "card": card_id, "users": users, "lost": lost, "removed": removed, "guided": guided})
            self.schedule(REVEAL_DELAY, self.after_saved)
            return WAIT
        self.log.append({"type": "bust", "card": card_id, "lost": lost, "removed": removed, "guided": guided})
        self.end_expedition({"reason": "bust", "card": card_id, "lost": lost, "removed": removed, "guided": guided})
        return ENDED

    def after_saved(self):
        if self.phase != PLAYING or self.stage != SAVED:
            return
        self.strike = None
        self.continue_resolving()

    def finish_fountain(self):
        moves = {}
        for pid, amount in self.choices.reveal().items():
            seat = self.seats[pid]
            amount = max(-seat["fountain"], min(amount, seat["backpack"]))  # still in range
            seat["backpack"] -= amount
            seat["fountain"] += amount
            moves[pid] = amount
        self.log.append({"type": "fountain-moves", "moves": moves})
        self.fountain_path = None
        self.choices = SecretChoices()
        self.continue_resolving()

    def take_leftovers(self, count, path):
        """Split the silver left on a path's cards `count` ways. Returns each share (taken off the cards)."""
        cards = self.path_cards(path)
        share = sum(e["left"] for e in cards) // count
        to_take = share * count
        for entry in cards:
            taken = min(entry["left"], to_take)
            entry["left"] -= taken
            to_take -= taken
        return share

    def bank(self, pid, extra=0):
        """pid goes to camp: backpack (+ extra) into the chest. Returns the amount banked."""
        seat = self.seats[pid]
        seat["backpack"] += extra
        banked = seat["backpack"]
        seat["chest"] += banked
        seat["backpack"] = 0
        seat["status"] = CAMP
        return banked

    def return_to_camp(self, pids, path):
        """pids split the silver left on their path, then bank their backpacks.

        A player who returns alone also takes every relic still on the path.
        Returns (share each took from the path, {pid: amount banked}, [relic ids taken]).
        """
        if not pids:
            return 0, {}, []
        share = self.take_leftovers(len(pids), path)
        banked = {pid: self.bank(pid, share) for pid in pids}
        return share, banked, self.take_relics(pids, path)

    def back_stab(self, victims, stabbers, path):
        """Leave players are robbed: their backpacks and leftover shares go to the back-stabbers."""
        share = self.take_leftovers(len(victims) + len(stabbers), path)
        robbed = {}
        for pid in victims:
            seat = self.seats[pid]
            robbed[pid] = seat["backpack"] + share
            seat["backpack"] = 0
            seat["status"] = CAMP
        each, remainder = divmod(sum(robbed.values()), len(stabbers))
        if remainder:
            self.path_cards(path)[-1]["left"] += remainder  # The remainder stays on the cards.
        banked = {pid: self.bank(pid, share + each) for pid in stabbers}
        return {
            "type": "backstab", "players": stabbers, "victims": victims, "share": share, "each": each,
            "robbed": robbed, "banked": banked, "relics": [],
        }

    def take_relics(self, pids, path):
        """A player who leaves alone takes every relic on their path."""
        cards = self.path_cards(path)
        relics = []
        if len(pids) == 1:
            pid = pids[0]
            seat = self.seats[pid]
            for entry in cards:
                if not entry.get("resolved") or kind(entry) not in RELIC_TYPES or "taken" in entry:
                    continue
                card_id = effective(entry)
                entry["taken"] = pid
                relics.append(card_id)
                relic_kind = DECK_CARDS[card_id]["type"]
                if relic_kind == "charm":
                    seat["charms"].append(card_id)
                elif relic_kind == "idol":
                    seat["idols"].append(card_id)
                else:
                    seat["relics"].append(card_id)
                    self.hands[pid].append(DECK_CARDS[card_id]["gives"])
                    self.sort_hand(pid)
                self.remove_instance(entry.get("uid"))  # The physical card (maybe a Mirror) leaves the deck.
        return relics

    def sort_hand(self, pid):
        self.hands[pid].sort(key=lambda c: (HAND_CARDS[c]["order"], c))

    def use_relic(self, pid, hand_card):
        """A relic's hand card was played: it no longer shows as held."""
        relics = self.seats[pid]["relics"]
        held = next((r for r in relics if DECK_CARDS[r]["gives"] == hand_card), None)
        if held:
            relics.remove(held)

    def reveal(self):
        """Everyone exploring has played: reveal all cards together and apply them."""
        picks = self.choices.reveal()
        self.stage = REVEAL
        types = {pid: HAND_CARDS[card]["type"] for pid, card in picks.items()}

        self.guarded = {pid for pid, kind_ in types.items() if kind_ == "guard"}
        stashed = {}
        for pid, kind_ in types.items():
            if kind_ == "stash":
                seat = self.seats[pid]
                stashed[pid] = seat["backpack"]
                seat["chest"] += seat["backpack"]
                seat["backpack"] = 0

        groups = []
        for path in range(len(self.paths)):
            here = self.explorers(path)
            fleers = [pid for pid in here if types.get(pid) == "flee"]
            leavers = [pid for pid in here if types.get(pid) == "leave"]
            stabbers = [pid for pid in here if types.get(pid) == "backstab"]
            if fleers:  # Fleers go first, and Backstab can't touch them.
                share, banked, relics = self.return_to_camp(fleers, path)
                groups.append({"type": "flee", "players": fleers, "share": share, "banked": banked, "relics": relics})
            if stabbers and leavers:
                groups.append(self.back_stab(leavers, stabbers, path))
            elif leavers or stabbers:  # Nobody to stab: back-stabbers just leave.
                pids = leavers + stabbers
                share, banked, relics = self.return_to_camp(pids, path)
                groups.append({"type": "leave", "players": pids, "share": share, "banked": banked, "relics": relics})

        returned = []
        open_ids = [p["id"] for p in self.paths if not p["closed"]]
        for pid, kind_ in types.items():
            if kind_ == "return" and self.seats[pid]["status"] == CAMP:
                seat = self.seats[pid]
                seat["status"] = EXPLORING
                seat["backpack"] = 0
                chosen = self.return_paths.get(pid)
                seat["path"] = chosen if chosen in open_ids else open_ids[0]
                returned.append(pid)
        self.return_paths = {}

        for pid, card in picks.items():
            if pid not in self.hands:
                continue
            if HAND_CARDS[card]["reusable"]:
                self.hands[pid].append(card)
                self.sort_hand(pid)
            else:
                self.use_relic(pid, card)

        self.log.append({
            "type": "reveal",
            "stay": [pid for pid, k in types.items() if k == "stay"],
            "stash": stashed,
            "guard": sorted(self.guarded, key=self.order.index),
            "groups": groups,
            "returned": returned,
            "paths": {pid: self.seats[pid]["path"] for pid in returned},
        })
        self.schedule(REVEAL_DELAY, self.after_reveal)

    def after_reveal(self):
        if self.phase != PLAYING or self.stage != REVEAL:
            return
        if not self.explorers():
            self.end_expedition({"reason": "camp"})
            return
        forking = [p for p in self.paths if p["forking"] and not p["closed"]]
        for path in forking:
            path["forking"] = False
        forking = [p for p in forking if self.explorers(p["id"])]
        if forking and self.deck:
            self.split(forking)
        else:
            self.draw()

    def split(self, forking):
        """Close each forked path: discard all but the Fork and hazards, and reveal two new paths."""
        self.fork_options = {}
        self.queue = []
        for path in forking:
            kept = [e for e in path["cards"] if kind(e) in ("fork", "hazard")]
            discarded = len(path["cards"]) - len(kept)
            lost = sum(e["left"] for e in path["cards"] if e not in kept)
            path["cards"] = kept
            path["closed"] = True
            children = []
            for side in SIDES:
                if not self.deck:
                    break
                child = self.new_path(parent=path["id"], side=side)
                self.step += 1
                inst = self.deck.pop()
                child["cards"].append({
                    "card": inst["card"], "uid": inst["uid"], "marks": list(inst["marks"]),
                    "as": None, "left": 0, "step": self.step,
                })
                children.append(child["id"])
            self.fork_options[path["id"]] = children
            self.log.append({"type": "split", "path": path["id"], "children": children, "discarded": discarded, "lost": lost})
        deciders = [
            pid for parent, children in self.fork_options.items() if len(children) > 1 for pid in self.explorers(parent)
        ]
        if deciders:
            self.stage = FORK
            self.choices = SecretChoices(deciders)
        else:
            self.finish_fork({})

    def finish_fork(self, picks):
        """Move everyone at a fork onto the side they picked; then show the picks."""
        sides = {}
        for parent, children in self.fork_options.items():
            for pid in self.explorers(parent):
                side = picks.get(pid, "left")
                index = SIDES.index(side) if len(children) > 1 else 0
                self.seats[pid]["path"] = children[index]
                sides[pid] = SIDES[index]
        self.log.append({"type": "fork-choice", "sides": sides})
        self.stage = FORKED
        self.schedule(REVEAL_DELAY, self.after_fork)

    def after_fork(self):
        """The first card of each new path resolves for whoever took that path."""
        if self.phase != PLAYING or self.stage != FORKED:
            return
        new_paths = [child for children in self.fork_options.values() for child in children]
        self.queue = [(child, self.path_cards(child)[0]) for child in new_paths]
        self.fork_options = {}
        # Players on other paths get their usual card this turn too.
        for path in self.open_paths():
            if path not in new_paths and self.deck:
                self.reveal_onto(path)
        self.continue_resolving()

    def end_expedition(self, ending):
        self.stage = OVER
        self.choices = SecretChoices()
        self.queue = []
        self.strike = None
        self.fountain_path = None
        self.fork_options = {}
        self.return_paths = {}
        self.robbery = None
        self.auction = None
        self.ending = ending
        if self.expedition >= self.expeditions:
            self.finish_game()
        else:
            self.schedule(END_DELAY, self.begin_gems)

    # --- Between expeditions -------------------------------------------------------

    def begin_gems(self):
        """Each gem won this round is used now, one at a time; then marking."""
        if self.phase != PLAYING or self.stage != OVER:
            return
        self.gem_queue = []
        for pid in self.active():
            self.gem_queue += [(pid, gem) for gem in self.seats[pid]["gems"]]
            self.seats[pid]["gems"] = []
        self.next_gem()

    def next_gem(self):
        while self.gem_queue:
            pid, gem = self.gem_queue.pop(0)
            if self.seats[pid]["status"] == GONE:
                continue
            color = DECK_CARDS[gem]["color"]
            if color == "red":
                self.gem_options = random_pool_cards(RED_GEM_OFFER)
                if not self.gem_options:
                    continue
            elif not MARKS or not self.deck_list:
                continue
            self.gem_turn = {"player": pid, "gem": gem, "color": color}
            self.stage = GEM
            self.choices = SecretChoices([pid])
            return
        self.gem_turn = None
        self.gem_options = []
        self.stage = OVER
        self.begin_marking()

    def use_gem(self, pid, data):
        turn = self.gem_turn
        if self.stage != GEM or not turn or turn["player"] != pid:
            raise LobbyError("You don't have a gem to use right now.")
        if turn["color"] == "red":
            cards = data.get("cards")
            picks = min(RED_GEM_PICKS, len(self.gem_options))
            if (not isinstance(cards, list) or len(cards) != picks or len(set(map(str, cards))) != picks
                    or any(c not in self.gem_options for c in cards)):
                raise LobbyError(f"Pick {picks} different cards.")
            self.deck_list += [self.new_instance(c) for c in cards]  # Secret: the log doesn't say which.
            self.log.append({"type": "red-gem", "player": pid, "added": len(cards), "deckSize": len(self.deck_list)})
        else:
            emoji = data.get("emoji")
            if emoji not in MARKS:
                raise LobbyError("Pick one of the marks.")
            for inst in random.sample(self.deck_list, min(BLUE_GEM_CARDS, len(self.deck_list))):
                inst["marks"].append(emoji)
                self.my_marks.setdefault(pid, []).append({"card": inst["card"], "emoji": emoji})
            self.log.append({"type": "blue-gem", "player": pid})
        self.choices = SecretChoices()
        self.next_gem()

    # --- Crystal Ball ----------------------------------------------------------------

    def peek(self, pid):
        hand = self.hands.get(pid, [])
        ball = next((c for c in hand if HAND_CARDS[c]["type"] == "peek"), None)
        if ball is None:
            raise LobbyError("You don't have a Crystal Ball.")
        if self.stage in (OVER, MARKING, GEM) or not self.deck:
            raise LobbyError("The Crystal Ball can't be used between expeditions or when the deck is empty.")
        hand.remove(ball)
        self.use_relic(pid, ball)
        self.peeks[pid] = [i["uid"] for i in reversed(self.deck[-PEEK_CARDS:])]  # next first
        self.log.append({"type": "peek", "player": pid})

    def begin_marking(self):
        """Everyone secretly marks the back of one of 3 deck cards with one of 3 shared emoji."""
        if self.phase != PLAYING or self.stage != OVER:
            return
        active = self.active()
        if not MARKS or not self.deck_list or not active:
            self.begin_expedition(self.expedition + 1)
            return
        self.mark_emojis = random.sample(MARKS, MARK_CHOICES)
        self.offers = {
            pid: [i["uid"] for i in random.sample(self.deck_list, min(OFFER_SIZE, len(self.deck_list)))]
            for pid in active
        }
        self.stage = MARKING
        self.choices = SecretChoices(active)

    def finish_marking(self):
        picks = self.choices.peek()  # Never revealed: only you know what your mark means.
        for pid, pick in picks.items():
            inst = self.instance(pick["uid"])
            if inst is not None:
                inst["marks"].append(pick["emoji"])
                self.my_marks.setdefault(pid, []).append({"card": inst["card"], "emoji": pick["emoji"]})
        self.log.append({"type": "marked", "players": list(picks)})
        self.offers = {}
        self.mark_emojis = []
        self.begin_expedition(self.expedition + 1)

    def finish_game(self, reason=None):
        active = self.active()
        chests = {pid: self.seats[pid]["chest"] for pid in active}
        idols = {pid: sum(DECK_CARDS[c]["value"] for c in self.seats[pid]["idols"]) for pid in active}
        # Every other relic still held at the end (unused charms and relic cards) is worth RELIC_BONUS.
        bonus = {pid: RELIC_BONUS * (len(self.seats[pid]["charms"]) + len(self.seats[pid]["relics"])) for pid in active}
        scores = {pid: chests[pid] + idols[pid] + bonus[pid] for pid in active}
        best = max(scores.values(), default=0)
        winners = [pid for pid in active if scores[pid] == best]
        self.finish({
            "winners": winners, "scores": scores, "chests": chests, "idols": idols, "bonus": bonus, "reason": reason,
        })

    # --- Messages ----------------------------------------------------------------

    # Thin wrappers: unpack the message and call the rule methods below.
    def on_play(self, member, data):
        self.play_card(member.id, data.get("card"), data.get("path"))

    def on_charm(self, member, data):
        self.decide_charm(member.id, data.get("use"))

    def on_fountain(self, member, data):
        self.decide_fountain(member.id, data.get("amount"))

    def on_mark(self, member, data):
        self.mark_card(member.id, data.get("uid"), data.get("emoji"))

    def on_rob(self, member, data):
        self.choose_loss(member.id, data.get("kind"), data.get("card"))

    def on_bid(self, member, data):
        self.place_bid(member.id, data.get("amount"))

    def on_gem(self, member, data):
        self.use_gem(member.id, data)

    def on_peek(self, member, data):
        self.peek(member.id)

    def play_card(self, pid, card, path=None):
        if self.stage == FORK:
            self.pick_side(pid, card)
            return
        if self.stage != CHOOSING or not self.choices.can_choose(pid):
            raise LobbyError("You can't play a card right now.")
        if self.choices.chosen(pid):
            raise LobbyError("You've already played a card.")
        hand = self.hands.get(pid, [])
        if not isinstance(card, str) or card not in hand:
            raise LobbyError("That card isn't in your hand.")
        kind_ = HAND_CARDS[card]["type"]
        exploring = self.seats[pid]["status"] == EXPLORING
        if kind_ == "peek":
            raise LobbyError("The Crystal Ball doesn't use your turn: select it and press USE.")
        if exploring and kind_ not in EXPLORER_PLAYS:
            raise LobbyError(f"{HAND_CARDS[card]['name']} can only be played from camp.")
        if not exploring and kind_ != "return":
            raise LobbyError("You're at camp. Only Seconds can be played from there.")
        if kind_ == "return":
            joinable = self.open_paths()
            if len(joinable) > 1:
                if path not in joinable:
                    raise LobbyError("Click a path in the mine to choose where to rejoin.")
                self.return_paths[pid] = path
        hand.remove(card)
        self.choices.choose(pid, card)
        if self.choices.complete():
            self.reveal()

    def pick_side(self, pid, card):
        """At a fork: Stay = left, Leave = right. The card stays in your hand."""
        if not self.choices.can_choose(pid):
            raise LobbyError("You're not at the fork.")
        if self.choices.chosen(pid):
            raise LobbyError("You've already picked a path.")
        if not isinstance(card, str) or card not in self.hands.get(pid, []):
            raise LobbyError("That card isn't in your hand.")
        side = FORK_PLAYS.get(HAND_CARDS[card]["type"])
        if side is None:
            raise LobbyError("At the fork, play Go Left or Go Right.")
        self.choices.choose(pid, side)
        if self.choices.complete():
            self.finish_fork(self.choices.reveal())

    def decide_charm(self, pid, use):
        if self.stage != CHARM or not self.choices.can_choose(pid):
            raise LobbyError("You can't use a charm right now.")
        if self.choices.chosen(pid):
            raise LobbyError("You've already decided.")
        if type(use) is not bool:
            raise LobbyError("Use your charm or pass.")
        self.choices.choose(pid, use)
        if self.choices.complete():
            self.resolve_strike([p for p, used in self.choices.reveal().items() if used])

    def decide_fountain(self, pid, amount):
        if self.stage != FOUNTAIN or not self.choices.can_choose(pid):
            raise LobbyError("You can't use the fountain right now.")
        if self.choices.chosen(pid):
            raise LobbyError("You've already decided.")
        seat = self.seats[pid]
        if type(amount) is not int or not -seat["fountain"] <= amount <= seat["backpack"]:
            raise LobbyError(f"You can put in up to {seat['backpack']} or take out up to {seat['fountain']}.")
        self.choices.choose(pid, amount)
        if self.choices.complete():
            self.finish_fountain()

    def mark_card(self, pid, uid, emoji):
        if self.stage != MARKING or not self.choices.can_choose(pid):
            raise LobbyError("You can't mark a card right now.")
        if self.choices.chosen(pid):
            raise LobbyError("You've already marked a card.")
        if type(uid) is not int or uid not in self.offers.get(pid, []):
            raise LobbyError("That card wasn't shown to you.")
        if emoji not in self.mark_emojis:
            raise LobbyError("Pick one of the three marks shown.")
        self.choices.choose(pid, {"uid": uid, "emoji": emoji})
        if self.choices.complete():
            self.finish_marking()

    def losable(self, pid):
        """Relics pid could lose to a Robbery: [(kind, card id)]."""
        seat = self.seats[pid]
        return (
            [("charm", c) for c in seat["charms"]]
            + [("idol", c) for c in seat["idols"]]
            + [("relic", c) for c in seat["relics"]]
        )

    def choose_loss(self, pid, kind_, card):
        if self.stage != ROBBERY or not self.choices.can_choose(pid):
            raise LobbyError("You're not being robbed.")
        if self.choices.chosen(pid):
            raise LobbyError("You've already chosen.")
        if (kind_, card) not in self.losable(pid):
            raise LobbyError("You don't have that card.")
        self.choices.choose(pid, {"kind": kind_, "card": card})
        if self.choices.complete():
            self.finish_robbery()

    def finish_robbery(self):
        losses = {}
        for pid, pick in self.choices.reveal().items():
            if (pick["kind"], pick["card"]) not in self.losable(pid):
                continue
            seat = self.seats[pid]
            seat[pick["kind"] + "s"].remove(pick["card"])
            if pick["kind"] == "relic":
                gives = DECK_CARDS[pick["card"]]["gives"]
                if gives in self.hands.get(pid, []):
                    self.hands[pid].remove(gives)
            losses[pid] = pick
        self.log.append({"type": "robbed", "losses": losses})
        self.robbery = None
        self.choices = SecretChoices()
        self.continue_resolving()

    def on_player_removed(self, member):
        pid = member.id
        seat = self.seats.get(pid)
        if seat is None:
            return
        seat["status"] = GONE
        seat["backpack"] = 0
        self.hands.pop(pid, None)
        self.offers.pop(pid, None)
        self.log.append({"type": "gone", "player": pid})
        if not self.active():
            return  # LobbyGame returns to the lobby when no players are left.
        self.choices.remove(pid)
        self.return_paths.pop(pid, None)
        everyone_in = self.choices.complete() or not self.choices.pending
        if self.stage == CHOOSING:
            if not self.explorers():
                self.end_expedition({"reason": "camp"})
            elif everyone_in:
                self.reveal()
        elif self.stage == MARKING and everyone_in:
            self.finish_marking()
        elif self.stage == ROBBERY and everyone_in:
            self.finish_robbery()
        elif self.stage == AUCTION and self.auction:
            self.auction["order"] = [x for x in self.auction["order"] if x != pid or x in self.auction["bids"]]
            if self.auction["leader"] == pid:  # A leaver's bid no longer counts.
                bids = {x: b for x, b in self.auction["bids"].items() if x != pid and b}
                self.auction["leader"] = max(bids, key=bids.get) if bids else None
                self.auction["high"] = bids.get(self.auction["leader"], 0)
            self.skip_hopeless_bidders()
        elif self.stage == GEM and self.gem_turn and self.gem_turn["player"] == pid:
            self.next_gem()
        elif self.stage == CHARM and everyone_in:
            self.resolve_strike([p for p, used in self.choices.reveal().items() if used])
        elif self.stage == FOUNTAIN and everyone_in:
            self.finish_fountain()
        elif self.stage == FORK and everyone_in:
            self.finish_fork(self.choices.reveal())
