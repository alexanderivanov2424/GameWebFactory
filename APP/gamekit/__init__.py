"""gamekit: the shared Python library games are built on (server side).

Games import everything they need from here; they never import the site server (`server`).

    from gamekit import LobbyGame, LobbyError, PLAYING, FINISHED, Int, TurnQueue, SecretChoices
    from gamekit import RealtimeGame                    # real-time games (tick loop)
    from gamekit import FullState, PatchState, Snapshots  # SYNC choices
    from gamekit.sync import quantize                   # round floats so deltas stay small
    from gamekit.validate import whole_number, one_of, cell, clean_text
    from gamekit.data import load_json_dir, load_json   # content files (cards, units, ...)
    from gamekit import turtle                          # turtle("reason"): emergency site shutdown

Saved player data: LobbyGame.load_data / save_data / account_name (see lobby.py).

Modules (each header documents its API):
    lobby.py     LobbyGame: members, host, ready/start, phases, state sync, timers, ACTIONS
    realtime.py  RealtimeGame: LobbyGame on a fixed tick, buffered inputs, ping
    sync.py      FullState / PatchState / Snapshots: how state reaches clients (SYNC = ...)
    settings.py  Int(...): host settings declared once (server validation + client inputs)
    validate.py  LobbyError and validators for what players send
    turns.py     TurnQueue: turn order by counters (cost 1 per action = round-robin)
    choices.py   SecretChoices: hidden simultaneous picks, revealed together
    data.py      Loading and validating JSON content files
    sim.py       Sim: drives a game through the real lobby for tests (no network)

Client-side counterpart: web/gamekit/ (room.js, lobby.js, lobby-ui.js, dom.js, realtime.js).
"""

from gamekit.choices import SecretChoices
from gamekit.lobby import FINISHED, LOBBY, PLAYING, LobbyGame
from gamekit.realtime import RealtimeGame
from gamekit.settings import Int
from gamekit.sync import FullState, PatchState, Snapshots
from gamekit.turns import TurnQueue
from gamekit.validate import LobbyError
from server.turtle import turtle  # emergency shutdown for safety checks (server/turtle.py)

__all__ = ["FINISHED", "LOBBY", "PLAYING", "FullState", "Int", "LobbyError", "LobbyGame", "PatchState",
           "RealtimeGame", "SecretChoices", "Snapshots", "TurnQueue", "turtle"]
