"""Planet Jumpers: a co-op trick-taking game for 3-5 players, played as a run of missions.

Cards: four colour suits (red, blue, yellow, green) 1-9 and black trumps 1-4 (40 cards).
Each mission deals every card out (some players may get 1 more). The player holding the black 4
is the captain. You must follow the suit led if you can, otherwise play anything. A trick goes to
the highest black played, else the highest card of the suit led; its winner leads the next. The
captain leads the first trick. Players are seated in join order (clockwise).

A run: missions are drawn from mission deck 1 until it's empty, then deck 2, then deck 3 (played
missions are discarded). At the start of each mission the ship loses 1 fuel and 1 food (never
below 0; fuel and food are capped at 3). The ship starts with 5 hull, 0 fuel, 0 food, 0 science.
A mission card (missions/<id>.json) gives its name, what its fuel and food tasks add, its
tasks (tasks/<id>.json) and any special setup. Tasks are drafted before the first trick,
starting with the captain and going clockwise in laps from the captain: take one of the tasks
left, or pass if more players are left in this lap (you included) than tasks (logic/draft.py).
Once every card is played, done tasks give their success effects and the rest their failure
effects, then the host starts the next mission. A task's "done" is final unless its file sets
"can_fail_when_done" (e.g. win 0 tricks): once every task is done and none can fail any more, the
host may end the mission early (the cards left aren't played). The run ends when the hull reaches 0
("destroyed") or every mission deck is empty ("complete").

Saved run: one per player (the host's is used). It's saved when a new run starts and after every mission
({"v", "missions", "completed", "ship", "over"}, logic/ship.py) to whoever was host when the
game started. The "run" setting picks a new run or continuing the saved one.
A player leaving mid-run ends the game (the run stays saved as of its last finished mission).

Player options:  none
Settings:        {"run": "new" | "continue"}
Game messages:   {"action": "take", "task": task id}     draft: take a task on your turn
                 {"action": "pass"}                      draft: pass (only when allowed)
                 {"action": "play", "card": "r3"}        play a card on your turn
                 {"action": "end"}                       host: end the mission early (every task
                                                         done and none can fail any more)
                 {"action": "next"}                      host, after a mission: start the next one
State (lobby):   state.game = {"save": saved run summary of the host, or None}
State (playing): logic/match.py public(); state.private = {"hand", "playable"}

Code: this file connects the game to the lobby (settings, messages, timers, saved run).
The rules live in logic/ (see logic/__init__.py for its modules).
"""

from gamekit import PLAYING, Choice, LobbyError, LobbyGame

from .logic.match import Match
from .logic.ship import Run

TRICK_PAUSE = 1.5  # seconds a full trick stays on the table


class Game(LobbyGame):
    MIN_PLAYERS = 3
    MAX_PLAYERS = 5
    SETTINGS = {
        "run": Choice("Run", default="new", options={"new": "Start a new run", "continue": "Continue the host's saved run"}),
    }
    ACTIONS = {"take": "take", "pass": "pass_turn", "play": "play", "end": "end_early",
               "next": "next_mission"}

    def __init__(self, room):
        super().__init__(room)
        self.reset_game()

    # --- Lobby ---------------------------------------------------------------------------

    def host(self):
        return self.member_by_id(self.host_id) if self.host_id else None

    def saved_run(self, member):
        return Run.load(self.load_data(member)) if member else None

    def lobby_game_state(self):
        run = self.saved_run(self.host())
        return {"save": run.public() if run else None}

    def start_check(self):
        if self.settings["run"] == "continue":
            run = self.saved_run(self.host())
            if run is None:
                return "The host has no saved run to continue."
            if not run.continuable():
                return "The host's saved run is over: start a new run."
        return None

    # --- Game ----------------------------------------------------------------------------

    def reset_game(self):
        self.match = None
        self.owner = None

    def start_game(self):
        self.owner = self.host()
        run = self.saved_run(self.owner) if self.settings["run"] == "continue" else None
        if run is None:  # a new run replaces the saved one at once (there's only one save)
            run = Run.new()
            self.save_data(self.owner, run.save())
        self.match = Match({p.id: p.name for p in self.players}, run)
        self.match.start_mission()
        self.check_over()

    def game_state(self):
        return self.match.public()

    def private_state(self, member):
        return self.match.private(member.id) if member.playing else None

    def take(self, member, data):
        task = data.get("task")
        if not isinstance(task, str):
            raise LobbyError("Pick a task.")
        self.match.take(member.id, task)

    def pass_turn(self, member, data):
        self.match.pass_turn(member.id)

    def play(self, member, data):
        card = data.get("card")
        if not isinstance(card, str):
            raise LobbyError("Pick a card.")
        self.match.play(member.id, card)
        if self.match.stage == "collect":
            self.schedule(TRICK_PAUSE, self.collect)

    def collect(self):
        if self.phase != PLAYING or self.match is None or self.match.stage != "collect":
            return
        self.match.collect()
        if self.match.mission_over:
            self.save_run()
        self.check_over()

    def end_early(self, member, data):
        if member.id != self.host_id:
            raise LobbyError("Only the host can end the mission early.")
        self.match.end_early()
        self.cancel_timers()  # a full trick waiting to be collected
        self.save_run()
        self.check_over()

    def next_mission(self, member, data):
        if member.id != self.host_id:
            raise LobbyError("Only the host can start the next mission.")
        self.match.next_mission()
        self.check_over()

    def save_run(self):
        owner = self.owner if self.owner in self.players else self.host()
        if owner:
            self.save_data(owner, self.match.run.save())

    def on_player_removed(self, member):
        self.finish({"outcome": "left", "missions": self.match.run.missions,
                     "reason": f"{member.name} left: the run was saved after its last finished mission."})

    def check_over(self):
        if self.match.result is not None:
            self.finish(self.match.result)
