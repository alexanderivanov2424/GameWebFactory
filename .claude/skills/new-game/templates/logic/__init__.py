"""{{GAME_NAME}}: the game's rules, kept apart from the lobby (server.py).

Modules (keep this list and NOTES.md's map up to date as you add more):
    match.py    Match: the state of one game in progress and the rules that change it.

Code here knows players only by public id ("p1", "p2", ...), never by Member objects, the
network or the lobby phase, so tests can drive it directly (see tests/). It may import
gamekit (TurnQueue, SecretChoices, LobbyError, gamekit.validate, gamekit.data), never
`server`. Import sibling modules relatively (`from .board import Board`).

Avoid monolithic files: one topic per module, and split a module (match.py included) when it
mixes topics or passes ~400 lines. match.py keeps the state and turn flow and calls the
others. For example:
    board.py    the board/map and geometry (neighbours, line of sight, walls)
    cards.py    content loaders (gamekit.data) for JSON files in a folder next to server.py,
                e.g. Path(__file__).resolve().parent.parent / "cards"
    effects.py  one function per card/ability type
    scoring.py  end-of-game scoring
Timers (self.schedule), finish() and saved player data stay in server.py: Match reports what
happened (e.g. `self.result`, a stage name) and server.py reacts.
"""
