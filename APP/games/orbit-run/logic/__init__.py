"""Orbit Run: the game's rules, kept apart from the lobby (server.py).

Modules (keep this list and NOTES.md's map up to date as you add more):
    match.py     Match: one run in one game: mission flow (draw, upkeep, deal, captain), tricks,
                 task status, end of mission (effects on the ship, run over)
    cards.py     the 40-card deck, dealing, follow-suit rule, trick winner
    draft.py     Draft: drafting a mission's tasks from the captain, in laps, with the pass rule
    tasks.py     task cards from tasks/*.json: goal kinds (tricks, cards) and their status
    missions.py  mission cards from missions/*.json and the 3 mission decks
    ship.py      Run: the ship's resources, caps, upkeep, effects, and the saved-run format

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
