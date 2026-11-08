"""Block Blast: one player's 9x9 board and the geometry of placing pieces on it.

A board is a list of SIZE rows of SIZE cells. A cell is None (empty) or a tuple
(tile, symbol): a tile type name (tiles.py) and a symbol name (symbols.py) or None.
A piece (what a card places, in one rotation) is a list of (dr, dc, tile, symbol).

    board = new_board()
    fits(board, piece, row, col)      True if every tile lands on an empty cell on the board
                                      (row, col = where the piece's top-left corner goes)
    place(board, piece, row, col)     puts the tiles down (call fits first)
    full_lines(board)                 (rows, cols): indexes of the full rows and columns
    line_cells(rows, cols)            the set of (r, c) in those lines (crossings once)
    clear(board, rows, cols)          empties them; returns [(r, c, cell)] removed, each cell
                                      once even where a row and a column cross
    layers(cells, height, width)      {"tiles": [...], "symbols": [...]}: rows of one-letter
                                      codes ("." = none), how boards and pieces reach clients
    public(board)                     layers() of a whole board
"""

from . import symbols, tiles

SIZE = 9
EMPTY = "."  # "no tile / no symbol" in the layer codes


def new_board():
    return [[None] * SIZE for _ in range(SIZE)]


def fits(board, piece, row, col):
    for dr, dc, _, _ in piece:
        r, c = row + dr, col + dc
        if not (0 <= r < SIZE and 0 <= c < SIZE) or board[r][c] is not None:
            return False
    return True


def place(board, piece, row, col):
    for dr, dc, tile, symbol in piece:
        board[row + dr][col + dc] = (tile, symbol)


def full_lines(board):
    rows = [r for r in range(SIZE) if all(board[r][c] is not None for c in range(SIZE))]
    cols = [c for c in range(SIZE) if all(board[r][c] is not None for r in range(SIZE))]
    return rows, cols


def line_cells(rows, cols):
    return {(r, c) for r in rows for c in range(SIZE)} | {(r, c) for c in cols for r in range(SIZE)}


def clear(board, rows, cols):
    removed = []
    for r, c in sorted(line_cells(rows, cols)):
        removed.append((r, c, board[r][c]))
        board[r][c] = None
    return removed


def layers(cells, height, width):
    """cells: {(r, c): (tile, symbol)} -> two layers of code strings."""
    tile_rows, symbol_rows = [], []
    for r in range(height):
        tile_row, symbol_row = [], []
        for c in range(width):
            cell = cells.get((r, c))
            tile_row.append(tiles.TILE_TYPES[cell[0]].code if cell else EMPTY)
            symbol_row.append(symbols.SYMBOLS[cell[1]].code if cell and cell[1] else EMPTY)
        tile_rows.append("".join(tile_row))
        symbol_rows.append("".join(symbol_row))
    return {"tiles": tile_rows, "symbols": symbol_rows}


def public(board):
    cells = {(r, c): board[r][c] for r in range(SIZE) for c in range(SIZE) if board[r][c] is not None}
    return layers(cells, SIZE, SIZE)
