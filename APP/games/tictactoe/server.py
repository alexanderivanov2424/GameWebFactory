"""Color Tic-Tac-Toe: tic-tac-toe for any number of players, each with their own color.

Lobby: each player picks a unique color. The host sets the board size and how many
pieces in a row win.
Game: turn order is random. Players take turns placing a piece; the first to get
`winLength` in a row (horizontally, vertically or diagonally) wins.

Player options:  {"color": "#rrggbb"}
Settings:        {"boardSize": 3, "winLength": 3}
Game messages:   {"action": "place", "row": 0, "col": 2}
"""

import random
import re

from gamekit import PLAYING, Int, LobbyError, LobbyGame, TurnQueue
from gamekit.validate import cell

COLOR = re.compile(r"^#[0-9a-f]{6}$")
DEFAULT_COLORS = [
    "#e5484d", "#4a5cff", "#1a8a4a", "#f5a524", "#8e4ec6",
    "#12a594", "#d6409f", "#ff8b3e", "#0091ff", "#6b7280",
]
DIRECTIONS = ((0, 1), (1, 0), (1, 1), (1, -1))


class Game(LobbyGame):
    MIN_PLAYERS = 2
    MAX_PLAYERS = 8
    SETTINGS = {
        "boardSize": Int("Board size", default=3, low=3, high=10),
        "winLength": Int("Pieces in a row to win", default=3, low=3, high="boardSize"),
    }
    ACTIONS = {"place": "place"}

    def __init__(self, room):
        super().__init__(room)
        self.reset_game()

    # --- Lobby -----------------------------------------------------------------

    def default_options(self, member):
        taken = {p.options.get("color") for p in self.players if p is not member}
        for color in DEFAULT_COLORS:
            if color not in taken:
                return {"color": color}
        while True:
            color = f"#{random.randrange(0x1000000):06x}"
            if color not in taken:
                return {"color": color}

    def clean_options(self, member, options):
        color = options.get("color")
        color = color.lower() if isinstance(color, str) else ""
        if not COLOR.match(color):
            raise LobbyError("Pick a color with R, G and B each from 0 to 255.")
        for other in self.players:
            if other is not member and other.options.get("color") == color:
                raise LobbyError(f"{other.name} already has that color.")
        return {"color": color}

    # --- Game ------------------------------------------------------------------

    def reset_game(self):
        self.size = 0
        self.win_length = 0
        self.board = []
        self.pieces = {}  # public id -> {"name", "color"}, fixed when the game starts
        self.queue = TurnQueue()
        self.moves = 0
        self.last_move = None  # [row, col] of the most recent piece

    def start_game(self):
        self.size = self.settings["boardSize"]
        self.win_length = self.settings["winLength"]
        self.board = [[None] * self.size for _ in range(self.size)]
        self.pieces = {p.id: {"name": p.name, "color": p.options["color"]} for p in self.players}
        order = list(self.pieces)
        random.shuffle(order)
        self.queue = TurnQueue(order)  # Every move costs 1, so this is round-robin.
        self.moves = 0
        self.last_move = None  # [row, col] of the most recent piece

    def game_state(self):
        return {
            "size": self.size,
            "winLength": self.win_length,
            "board": self.board,
            "pieces": self.pieces,
            "lastMove": self.last_move,
            "turnOrder": self.queue.order(),
            "turn": self.queue.current() if self.phase == PLAYING else None,
        }

    def place(self, member, data):
        if self.queue.current() != member.id:
            raise LobbyError("It's not your turn.")
        row, col = cell([data.get("row"), data.get("col")], self.size)
        if self.board[row][col] is not None:
            raise LobbyError("That square is taken.")

        self.board[row][col] = member.id
        self.moves += 1
        self.last_move = [row, col]

        line = self.winning_line(row, col)
        if line:
            self.finish({"winner": member.id, "line": line, "reason": None})
        elif self.moves == self.size * self.size:
            self.finish({"winner": None, "line": [], "reason": "The board is full."})
        else:
            self.queue.advance(member.id)

    def on_player_removed(self, member):
        if member.id not in self.queue:
            return
        self.queue.remove(member.id)
        if len(self.queue) == 1:
            self.finish({"winner": self.queue.current(), "line": [], "reason": "Everyone else left."})

    def winning_line(self, row, col):
        """Return the cells of a winning line through (row, col), or None."""
        owner = self.board[row][col]
        for dr, dc in DIRECTIONS:
            cells = [(row, col)]
            for sign in (1, -1):
                r, c = row + dr * sign, col + dc * sign
                while 0 <= r < self.size and 0 <= c < self.size and self.board[r][c] == owner:
                    cells.append((r, c))
                    r, c = r + dr * sign, c + dc * sign
            if len(cells) >= self.win_length:
                return sorted(cells)
        return None
