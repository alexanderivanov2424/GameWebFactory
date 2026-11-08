"""Marooned: survive a deserted island, build a raft and escape, while one of you is the Imposter.

Rules (the full design is in NOTES.md; constants live in logic/):
- 4-8 players. One is secretly the Imposter; the rest are castaways. Everyone scores on their
  own and the highest total wins. Each player is dealt secret objectives and keeps some.
- The island is a 7x7 (4-5 players) or 9x9 grid, face down except Camp, where everyone starts.
  Exploring a square draws 2 tile cards; the explorer places 1, the other goes under the deck.
- Days: everyone takes one turn (the first seat rotates daily), spending energy (5, less when
  hungry, wounded, Sick or Tired) on: move, explore, gather (a secret d6: the gatherer may
  announce a worse face than they rolled, never better, and gets what they announce),
  search, deposit/take items, build at camp, craft a tool, eat, heal with herbs, give,
  attack (wound + steal an item), launch the finished raft.
- Camp projects: the shelter (3 levels, 2 sleepers each) and the raft (4 stages). A full stage
  gets a build check: the builder picks a helper first, then draws 3 check cards, discards 1
  and hands 2 to the helper, who reveals 1 (Solid / Shaky / Snapped).
- Nights: everyone secretly votes for a suspect (only the tally is shown; it changes no
  rules), then hunger +1 and sleep (sheltered heals a wound; unsheltered = Tired, twice in a
  row = Sick).
- A launched raft leaves at the end of the next day with everyone at camp. The game also ends
  when the monsoon arrives (nobody escapes) or fewer than 3 players are left.

Settings:  monsoon (last day), objectivesDealt, objectivesKept, mapSize (auto/small/large).
Game messages ({"action": ..., ...}):
    keep {"objectives": [id, ...]}            objectives stage
    move {"cell": [r, c]}   explore {"cell": [r, c]}   place {"uid": n}
    gather {"item": "wood"}  report {"face": n}  search {}
    deposit / take {"item", "count"}   build {"project": "shelter"|"raft"}
    craft {"tool"}   eat {"from": "pack"|"camp"}   heal {}
    give {"player", "item"}   attack {"player", "steal": item or absent}   launch {}
    helper {"player"}   discard {"uid"}   reveal {"uid"}       build checks
    end_turn {}   vote {"player": public id or "nobody"}

Code: this file connects the game to the lobby; the rules live in logic/ (see
logic/__init__.py). State goes out as patches (SYNC = PatchState): the map is big.
"""

from gamekit import Choice, Int, LobbyError, LobbyGame, PatchState
from gamekit.validate import cell, one_of, whole_number

from .logic.content import ITEMS
from .logic.match import Match
from .logic.night import NOBODY
from .logic.survivor import TOOLS


class Game(LobbyGame):
    MIN_PLAYERS = 4
    MAX_PLAYERS = 8
    SYNC = PatchState
    SETTINGS = {
        "monsoon": Int("Days until the monsoon", default=14, low=8, high=20),
        "objectivesDealt": Int("Objectives dealt", default=3, low=1, high=4),
        "objectivesKept": Int("Objectives kept", default=2, low=1, high="objectivesDealt"),
        "mapSize": Choice("Map size", default="auto", options={
            "auto": "By player count", "small": "Small (7×7)", "large": "Large (9×9)"}),
    }
    ACTIONS = {
        "keep": "on_keep", "move": "on_move", "explore": "on_explore", "place": "on_place",
        "gather": "on_gather", "report": "on_report", "search": "on_search",
        "deposit": "on_deposit", "take": "on_take", "build": "on_build", "craft": "on_craft",
        "eat": "on_eat", "heal": "on_heal", "give": "on_give", "attack": "on_attack",
        "launch": "on_launch", "helper": "on_helper", "discard": "on_discard",
        "reveal": "on_reveal", "end_turn": "on_end_turn", "vote": "on_vote",
    }

    def __init__(self, room):
        super().__init__(room)
        self.reset_game()

    def reset_game(self):
        self.match = None

    def start_game(self):
        self.match = Match({p.id: p.name for p in self.players}, self.settings)

    def game_state(self):
        return self.match.public()

    def private_state(self, member):
        return self.match.private(member.id) if member.playing and self.match else None

    async def on_game_message(self, member, data):
        if member.id not in self.match.order:
            raise LobbyError("You're not on the island.")
        await self.dispatch(member, data)
        self.check_over()

    def on_player_removed(self, member):
        self.match.remove(member.id)
        self.check_over()

    def check_over(self):
        if self.match.result is not None and self.phase != "finished":
            self.finish(self.match.result)

    # --- Field helpers ----------------------------------------------------------------

    def _cell(self, data):
        return cell(data.get("cell"), self.match.island.size)

    def _item(self, data, key="item"):
        return one_of(data.get(key), ITEMS, "Unknown item.")

    def _count(self, data):
        return whole_number(data.get("count", 1), "Count", 1, 99, clamp=False)

    def _uid(self, data):
        return whole_number(data.get("uid"), "Card", 0, None, clamp=False)

    def _player(self, data):
        return one_of(data.get("player"), self.match.names, "Unknown player.")

    # --- Actions: unpack, then let Match apply the rules --------------------------------

    def on_keep(self, member, data):
        kept = data.get("objectives")
        if not isinstance(kept, list) or not all(isinstance(oid, str) for oid in kept):
            raise LobbyError("Pick objectives to keep.")
        self.match.pick_objectives(member.id, kept)

    def on_move(self, member, data):
        self.match.move(member.id, self._cell(data))

    def on_explore(self, member, data):
        self.match.explore(member.id, self._cell(data))

    def on_place(self, member, data):
        self.match.place(member.id, self._uid(data))

    def on_gather(self, member, data):
        self.match.gather(member.id, self._item(data))

    def on_report(self, member, data):
        self.match.report(member.id, whole_number(data.get("face"), "Face", 1, 6, clamp=False))

    def on_search(self, member, data):
        self.match.search(member.id)

    def on_deposit(self, member, data):
        self.match.deposit(member.id, self._item(data), self._count(data))

    def on_take(self, member, data):
        self.match.take(member.id, self._item(data), self._count(data))

    def on_build(self, member, data):
        self.match.build(member.id, one_of(data.get("project"), ("shelter", "raft"), "Unknown project."))

    def on_craft(self, member, data):
        self.match.craft(member.id, one_of(data.get("tool"), TOOLS, "Unknown tool."))

    def on_eat(self, member, data):
        self.match.eat(member.id, one_of(data.get("from", "pack"), ("pack", "camp"), "Eat from where?"))

    def on_heal(self, member, data):
        self.match.heal(member.id)

    def on_give(self, member, data):
        self.match.give(member.id, self._player(data), self._item(data))

    def on_attack(self, member, data):
        steal = self._item(data, "steal") if data.get("steal") is not None else None
        self.match.attack(member.id, self._player(data), steal)

    def on_launch(self, member, data):
        self.match.launch(member.id)

    def on_helper(self, member, data):
        self.match.choose_helper(member.id, self._player(data))

    def on_discard(self, member, data):
        self.match.discard_check(member.id, self._uid(data))

    def on_reveal(self, member, data):
        self.match.reveal_check(member.id, self._uid(data))

    def on_end_turn(self, member, data):
        self.match.end_turn(member.id)

    def on_vote(self, member, data):
        choice = data.get("player")
        if choice != NOBODY:
            choice = self._player(data)
        self.match.vote(member.id, choice)
