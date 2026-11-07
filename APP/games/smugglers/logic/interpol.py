"""Smugglers: Interpol's deck (deck-building, Dominion style) and pieces on the board.

Interpol owns a Deck of card instances (content/interpol/*.json). Each turn: 1 action,
1 buy, 0 budget, a hand of HAND_SIZE drawn at the end of the previous turn. Playing an
"action" card costs an action; "funding" cards are free. Effects (any mix):
    cards: draw N   actions: +N   budget: +N
    piece: "patrol" | "barrier" | "checkpoint"  (owning a copy = owning one such piece)
    move: N         (patrol: steps the patrol ship may move)
    repeat: true    (play the effect of an action card already played this turn, again)
Buying puts a new copy on the discard pile; a piece card also adds its piece (patrols start
at the board's Interpol home, barriers and checkpoints off the board until first played).

Piece targets, sent with the play: {"piece": id, "to": node}. Repeat also sends {"copy": uid
of the played card}. A patrol or checkpoint that lands on loaded ships inspects each of them
(inspection.check).
    barrier     onto a dot with no ship, barrier or checkpoint, as long as every planet and
                ship stays connected (ships can't enter or pass barriers)
    checkpoint  onto any spot with no barrier or checkpoint (loaded ships entering it stop)
    patrol      move up to `move` steps (ignores barriers) or stay (loaded ships entering its
                spot stop, as at a checkpoint)

    police = Interpol(pid, cards, board, rng)
    police.start_turn() / police.end_turn()
    police.play(m, uid, targets) / police.buy(card_id)
    police.nodes(kind)          set of nodes holding a piece of that kind
    police.public() / police.private(m)
"""

import itertools

from gamekit import Deck, LobbyError

from . import inspection

HAND_SIZE = 3


class Interpol:
    def __init__(self, pid, cards, board, rng):
        self.pid = pid
        self.cards = cards
        self.board = board
        start = [cid for cid, card in cards.items() for _ in range(card["start"])]
        self.deck = Deck(start, rng)
        self.supply = {cid: card["supply"] for cid, card in cards.items() if card["supply"] > 0}
        self.pieces = {}
        self._numbers = {}
        for cid in start:
            self._gain_piece(cid)
        self.hand = self.deck.draw(HAND_SIZE)
        self.played = []
        self.actions = self.buys = self.budget = 0
        self.score = 0

    def _gain_piece(self, card_id):
        kind = self.cards[card_id]["effects"].get("piece")
        if kind:
            number = next(self._numbers.setdefault(kind, itertools.count(1)))
            piece = {"id": f"{kind}{number}", "kind": kind}
            if kind == "patrol":
                piece["at"] = self.board.interpol_home
            self.pieces[piece["id"]] = piece

    def nodes(self, kind):
        return {p["at"] for p in self.pieces.values() if p["kind"] == kind and "at" in p}

    # --- Turn ------------------------------------------------------------------------------

    def start_turn(self):
        self.actions, self.buys, self.budget = 1, 1, 0
        self.played = []

    def end_turn(self):
        self.deck.discard(self.hand + self.played)
        self.hand = self.deck.draw(HAND_SIZE)
        self.played = []
        self.actions = self.buys = self.budget = 0

    def buy(self, card_id):
        card = self.cards.get(card_id)
        if card is None or self.supply.get(card_id, 0) <= 0:
            raise LobbyError("That card isn't for sale.")
        if self.buys < 1:
            raise LobbyError("You have no buys left this turn.")
        if self.budget < card["cost"]:
            raise LobbyError(f"{card['name']} costs {card['cost']}; you have {self.budget}.")
        self.budget -= card["cost"]
        self.buys -= 1
        self.supply[card_id] -= 1
        self.deck.add(card_id)
        self._gain_piece(card_id)
        return card

    def play(self, m, uid, targets):
        instance = next((c for c in self.hand if c["uid"] == uid), None)
        if instance is None:
            raise LobbyError("That card isn't in your hand.")
        card = self.cards[instance["card"]]
        if card["kind"] == "action" and self.actions < 1:
            raise LobbyError("You have no actions left this turn.")
        effects, source = card["effects"], card
        if effects.get("repeat"):
            copy = next((c for c in self.played if c["uid"] == targets.get("copy")), None)
            if copy is None or self.cards[copy["card"]]["kind"] != "action" or \
                    self.cards[copy["card"]]["effects"].get("repeat"):
                raise LobbyError("Pick an action card you played this turn to repeat.")
            source = self.cards[copy["card"]]
            effects = source["effects"]
        plan = self._check_piece(m, effects, targets)  # validate everything before changing anything
        if card["kind"] == "action":
            self.actions -= 1
        self.hand.remove(instance)
        self.played.append(instance)
        self.actions += effects.get("actions", 0)
        self.budget += effects.get("budget", 0)
        self.hand.extend(self.deck.draw(effects.get("cards", 0)))
        what = card["name"] + (f" (as {source['name']})" if source is not card else "")
        if plan is None:
            m.add_log(self.pid, f"Interpol played {what}.")
            return
        piece, to = plan
        piece["at"] = to
        m.add_log(self.pid, f"Interpol played {what}: {piece['kind']} to {m.label(to)}.")
        inspection.check(m, sorted(sid for sid, ship in m.ships.items() if ship["at"] == to))

    def _check_piece(self, m, effects, targets):
        kind = effects.get("piece")
        if not kind:
            return None
        piece = self.pieces.get(targets.get("piece"))
        if piece is None or piece["kind"] != kind:
            raise LobbyError(f"Pick one of your {kind} pieces.")
        to = targets.get("to")
        if to not in self.allowed(m, piece, effects):
            raise LobbyError(f"The {kind} can't go there.")
        return piece, to

    def allowed(self, m, piece, effects):
        """Nodes this piece may go to with these effects (sorted list)."""
        kind = piece["kind"]
        if kind == "patrol":
            reach = self.board.reach(piece["at"], effects.get("move", 0))
            return sorted(set(reach) | {piece["at"]})
        barriers = self.nodes("barrier") - {piece.get("at")}
        checkpoints = self.nodes("checkpoint") - {piece.get("at")}
        if kind == "checkpoint":
            return sorted(n for n in self.board.nodes if n not in barriers and n not in checkpoints)
        ships = {ship["at"] for ship in m.ships.values()}
        keep = list(self.board.planets) + sorted(ships)
        return sorted(
            n for n in self.board.nodes
            if not self.board.is_planet(n) and n not in ships and n not in barriers
            and n not in checkpoints and self.board.connected(keep, barriers | {n})
        )

    # --- What clients see ------------------------------------------------------------------

    def owned(self):
        counts = {}
        for card in self.deck.draw_pile + self.deck.discard_pile + self.hand + self.played:
            counts[card["card"]] = counts.get(card["card"], 0) + 1
        return counts

    def public(self):
        return {
            "pid": self.pid,
            "score": self.score,
            "actions": self.actions,
            "buys": self.buys,
            "budget": self.budget,
            "played": [card["card"] for card in self.played],
            "hand": len(self.hand),
            "deck": self.deck.counts(),
            "owned": self.owned(),
            "supply": self.supply,
            "pieces": self.pieces,
        }

    def private(self, m):
        """Hand, played instances (Repeat names one by uid) and, per piece card in hand or
        played, where each piece may go: {"hand", "played", "targets": {card id: {piece id: [nodes]}}}."""
        targets = {}
        for instance in self.hand + self.played:
            effects = self.cards[instance["card"]]["effects"]
            if effects.get("piece") and instance["card"] not in targets:
                targets[instance["card"]] = {
                    pid: self.allowed(m, piece, effects)
                    for pid, piece in self.pieces.items() if piece["kind"] == effects["piece"]
                }
        return {"hand": self.hand, "played": self.played, "targets": targets}
