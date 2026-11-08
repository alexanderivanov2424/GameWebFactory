"""Polyomino shapes on a grid (cards that place shapes, buildings of several cells).

A shape is a list of cells (r, c, ...) inside a height x width box; anything after r and c in a
cell tuple (a tile, a symbol) is kept as is when the shape turns. Shapes turn clockwise in
quarter turns and are never mirrored.

    from gamekit.shapes import parse, rotate, rotations

    cells, height, width = parse(["##", "#."])     # [(0, 0), (0, 1), (1, 0)], 2, 2
    turned, h, w = rotate(cells, height, width)    # one quarter turn clockwise
    pieces, sizes = rotations(cells, height, width)  # all 4 (0-3 quarter turns), [(h, w)] each

parse(rows, filled="#", max_size=5)   rows of text, `filled` marking the shape's cells; raises
    ValueError (the message data.py logs) when rows aren't 1..max_size equal-length strings or
    hold no filled cell. Other characters are empty.
"""


def parse(rows, filled="#", max_size=5):
    if not isinstance(rows, list) or not 1 <= len(rows) <= max_size or not all(isinstance(r, str) for r in rows):
        raise ValueError(f"shape must be a list of 1 to {max_size} strings")
    width = len(rows[0])
    if not 1 <= width <= max_size or any(len(r) != width for r in rows):
        raise ValueError(f"shape rows must all have the same length, 1 to {max_size}")
    cells = [(r, c) for r, row in enumerate(rows) for c, ch in enumerate(row) if ch == filled]
    if not cells:
        raise ValueError(f"shape needs at least one {filled!r}")
    return cells, len(rows), width


def rotate(cells, height, width):
    """One quarter turn clockwise: the cell at (r, c) moves to (c, height - 1 - r)."""
    return [(c, height - 1 - r, *rest) for r, c, *rest in cells], width, height


def rotations(cells, height, width):
    """The 4 clockwise rotations (0-3 quarter turns) -> (pieces, sizes)."""
    pieces, sizes = [list(cells)], [(height, width)]
    for _ in range(3):
        turned, h, w = rotate(pieces[-1], *sizes[-1])
        pieces.append(turned)
        sizes.append((h, w))
    return pieces, sizes
