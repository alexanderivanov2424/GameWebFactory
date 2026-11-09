"""Gilded Trail: Match, one game from start to finish (no lobby, network or members).

    match = Match({"p1": "Ann", "p2": "Bob"}, settings)   # names fixed at the start
    match.turn()                     # whose turn it is, or None once over
    match.move / pay / buy / play / trash / take / guide / end_turn   (pid first; LobbyError if illegal)
    match.remove(pid)                # pid left mid-game
    match.owned(pid)                 # {card id: copies} pid owns (shown as "view deck")
    match.public() / match.private(pid)
    match.result                     # None while playing; then {"winner", "winners", "reason"}

Turn flow: seats in random order, round-robin (TurnQueue, cost 1). During a turn the player
moves (movement.py), buys at most one card and plays action cards (actions.py) in any order;
End turn discards the played cards plus any cards from hand the player picks, then draws back
up to HAND_SIZE (the discard pile is reshuffled when the deck runs out).
The end: once a player's explorers have all arrived, the round is played out so everyone has
the same number of turns. Among the players who arrived, most blockades wins, then the
highest single blockade, then whoever arrived first. MAX_ROUNDS stops a stalled game (the
same ranking among arrived players; nobody wins if no one arrived).
"""

import random
from collections import Counter

from gamekit import Deck, LobbyError, TurnQueue

from . import actions, movement
from .board import Board
from .content import CARDS, MAPS
from .market import Market

START_DECK = ["porter"] * 3 + ["trader"] * 4 + ["boatman"]
HAND_SIZE = 4
MAX_ROUNDS = 100
COLORS = ["#e53935", "#1e88e5", "#fdd835", "#f5f5f5"]  # by seat
TWO_PLAYER_STARTS = [[0, 2], [1, 3]]  # 2 players: two explorers each, both must arrive


def make_board(settings, rng=random):
    """The board the host picked: a preset map, or a random one (seed 0 = a fresh seed)."""
    map_id = settings.get("map", "random")
    if map_id in MAPS:
        return Board(MAPS[map_id]), None
    seed = settings.get("seed") or rng.randrange(1, 1_000_000)
    return Board(None, seed, settings.get("tiles", 6)), seed


class Match:
    def __init__(self, names, settings, rng=random, cards=CARDS):
        self.names = dict(names)
        self.settings = dict(settings)
        self.rng = rng
        self.cards = cards
        self.board, self.seed = make_board(self.settings, rng)
        seats = list(self.names)
        rng.shuffle(seats)
        self.seats = seats
        self.queue = TurnQueue(seats)
        self.round = 1
        self.round_mark = 0  # everyone's TurnQueue value when the round started
        self.turn_number = 1
        self.final_round = False
        self.result = None
        self.log = []
        self.taken = {}  # blockade id -> pid who cleared it
        self.market = Market(cards)
        self.players = {}
        for i, pid in enumerate(seats):
            starts = TWO_PLAYER_STARTS[i] if len(seats) == 2 else [i]
            self.players[pid] = {
                "color": COLORS[i % len(COLORS)],
                "deck": Deck(START_DECK, rng),
                "hand": [],
                "removed": [],
                "explorers": [self.board.starts[s] for s in starts],
                "blockades": [],
            }
            self.draw(pid, HAND_SIZE)
        self.start_turn()
        where = self.board.name + (f" (seed {self.seed})" if self.seed else "")
        self.add_log(None, f"The expedition sets out on {where}. {self.names[seats[0]]} goes first.")

    # --- Helpers ---------------------------------------------------------------------------

    def add_log(self, pid, text):
        entry = {"text": text, "round": self.round}
        if pid:
            entry["pid"] = pid
        self.log.append(entry)

    def card_name(self, card_id):
        return self.cards[card_id]["name"]

    def draw(self, pid, count):
        player = self.players[pid]
        player["hand"].extend(player["deck"].draw(count))

    def hand_card(self, pid, uid):
        for card in self.players[pid]["hand"]:
            if card["uid"] == uid:
                return card
        raise LobbyError("That card isn't in your hand.")

    def take_from_hand(self, pid, uids):
        cards = [self.hand_card(pid, uid) for uid in uids]
        self.players[pid]["hand"] = [c for c in self.players[pid]["hand"] if c["uid"] not in uids]
        return cards

    def use_card(self, pid, card, single_removed, quiet=False):
        """A card was used: single-use cards used for their function leave the game."""
        if single_removed and self.cards[card["card"]]["single"]:
            self.players[pid]["removed"].append(card)
            if not quiet:
                self.add_log(pid, f"{self.names[pid]}'s {self.card_name(card['card'])} is used up.")
        else:
            self.played.append(card)

    def start_turn(self):
        self.moving = None    # {"uid", "card", "explorer", "kind", "left"}: the card moving now
        self.played = []      # cards played this turn (to the discard pile at the end)
        self.bought = False
        self.pending = None   # {"kind": "remove", "max": n} | {"kind": "free"} | {"kind": "guide"}

    def owned(self, pid):
        """{card id: copies} of every card pid still owns (hand, deck, discard, played this
        turn). Public: purchases and removals are all logged, so this hides only which cards
        are in hand."""
        p = self.players[pid]
        cards = p["hand"] + p["deck"].draw_pile + p["deck"].discard_pile
        if self.turn() == pid:
            cards = cards + self.played
        return dict(Counter(c["card"] for c in cards))

    def turn(self):
        return self.queue.current() if self.result is None else None

    def require_turn(self, pid, pending=None):
        if self.turn() != pid:
            raise LobbyError("It's not your turn.")
        if pending is None and self.pending:
            raise LobbyError("Finish the card you played first.")

    # --- Actions ---------------------------------------------------------------------------

    def move(self, pid, ei, to, uid=None):
        self.require_turn(pid)
        movement.move(self, pid, ei, to, uid)

    def pay(self, pid, ei, to, uids):
        self.require_turn(pid)
        movement.pay(self, pid, ei, to, uids)

    def buy(self, pid, card_id, uids):
        self.require_turn(pid)
        actions.buy(self, pid, card_id, uids)

    def play(self, pid, uid):
        self.require_turn(pid)
        actions.play(self, pid, uid)

    def trash(self, pid, uids):
        self.require_turn(pid, pending=True)
        actions.trash(self, pid, uids)

    def take(self, pid, card_id):
        self.require_turn(pid, pending=True)
        actions.take(self, pid, card_id)

    def guide(self, pid, ei, to):
        self.require_turn(pid, pending=True)
        actions.guide(self, pid, ei, to)

    def end_turn(self, pid, discard_uids):
        self.require_turn(pid)
        if len(set(discard_uids)) != len(discard_uids):
            raise LobbyError("Pick each card to discard once.")
        player = self.players[pid]
        discarded = self.take_from_hand(pid, discard_uids)
        player["deck"].discard(self.played + discarded)
        self.draw(pid, max(0, HAND_SIZE - len(player["hand"])))
        self.queue.advance(pid)
        self.next_turn()

    def next_turn(self):
        """After a turn ends or the current player leaves: start the next turn or end the game."""
        self.start_turn()
        if not self.queue.ids():
            return self.end("Everyone left.")
        if self.round_over():
            self.round_mark += 1
            if self.final_round:
                return self.end("The final round is over.")
            if self.round >= MAX_ROUNDS:
                return self.end(f"The expedition stalled after {MAX_ROUNDS} rounds.")
            self.round += 1
        self.turn_number += 1

    def remove(self, pid):
        if pid not in self.queue or self.result is not None:
            return
        current = self.turn() == pid
        self.queue.remove(pid)
        self.players[pid]["left"] = True
        self.players[pid]["explorers"] = ["" for _ in self.players[pid]["explorers"]]
        self.add_log(pid, f"{self.names[pid]} left the expedition.")
        if len(self.queue) == 1:
            winner = self.queue.current()
            self.result = {"winner": winner, "winners": [winner], "reason": "Everyone else left."}
            self.add_log(None, f"{self.names[winner]} wins: everyone else left.")
            return
        if current:
            self.next_turn()
        elif self.final_round and self.round_over():
            self.end("The final round is over.")

    def round_over(self):
        """True once every remaining player has taken their turn this round."""
        values = set(self.queue.values.values())
        return len(values) == 1 and values.pop() > self.round_mark

    def end(self, reason):
        arrived = [pid for pid, p in self.players.items() if "arrived" in p and not p.get("left")]
        best = None
        winners = []
        for pid in arrived:
            score = self.rank(pid)
            if best is None or score > best:
                best, winners = score, [pid]
            elif score == best:
                winners.append(pid)
        self.result = {"winner": winners[0] if len(winners) == 1 else None, "winners": winners, "reason": reason}
        names = " and ".join(self.names[p] for p in winners)
        self.add_log(None, f"Game over: {reason} " + (f"{names} win{'s' if len(winners) == 1 else ''}!"
                                                      if winners else "Nobody reached the golden city."))

    def rank(self, pid):
        """Tie-break key (bigger is better): blockades, highest blockade, earliest arrival."""
        values = [self.board.blockades[b]["v"] for b in self.players[pid]["blockades"]]
        return (len(values), max(values, default=0), -self.players[pid]["arrived"])

    # --- What clients see ------------------------------------------------------------------

    def public(self):
        state = {
            "names": self.names,
            "seats": self.seats,
            "turnOrder": self.queue.order(),
            "round": self.round,
            "turnNumber": self.turn_number,
            "finalRound": self.final_round,
            "handSize": HAND_SIZE,
            "board": self.board.public(),
            "blockades": {
                str(b["id"]): {**{k: b[k] for k in ("t", "v", "edges")},
                               **({"takenBy": self.taken[b["id"]]} if b["id"] in self.taken else {})}
                for b in self.board.blockades
            },
            "players": {
                pid: {
                    "color": p["color"],
                    "explorers": p["explorers"],
                    "blockades": p["blockades"],
                    "hand": len(p["hand"]),
                    "deck": len(p["deck"]),
                    "discard": len(p["deck"].discard_pile),
                    "removed": len(p["removed"]),
                    "owned": self.owned(pid),
                    "removedCards": dict(Counter(c["card"] for c in p["removed"])),
                    **({"arrived": True} if "arrived" in p else {}),
                    **({"left": True} if p.get("left") else {}),
                }
                for pid, p in self.players.items()
            },
            "market": self.market.public(),
            "cards": {cid: {**c, "coins": actions.coins(c)} for cid, c in self.cards.items()},
            "played": [c["card"] for c in self.played],
            "bought": self.bought,
            "log": {str(i): entry for i, entry in enumerate(self.log)},
            "logSize": len(self.log),
        }
        if self.turn() is not None:
            state["turn"] = self.turn()
        if self.moving:
            state["moving"] = {k: self.moving[k] for k in ("card", "explorer", "kind", "left")}
        if self.pending:
            state["pending"] = self.pending
        return state

    def private(self, pid):
        if pid not in self.players:
            return None
        mine = {"hand": self.players[pid]["hand"]}
        if self.moving and self.turn() == pid:
            mine["movingUid"] = self.moving["uid"]
        if self.turn() == pid:
            if not self.pending:
                mine["options"] = movement.options(self, pid)
            elif self.pending["kind"] == "guide":
                mine["guide"] = movement.guide_targets(self, pid)
        return mine
