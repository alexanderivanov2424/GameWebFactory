"""Block Blast: shared test helpers (not a test file: run_tests.py only collects test_*.py).

Import from a test file with
    helpers = importlib.import_module("games.block-blast.tests.helpers")  # the id contains "-"

    new_match(players=2, **settings)   a Match with a fixed seed (players "p1".."pN"), default
                                       settings unless given (e.g. market="cost", costSize=4)
    give(match, pid, card_id)          a fresh instance of card_id in pid's hand -> its uid
    cell(letter) / rows(grid)          board cells written as one letter (below), and back
    fill(match, pid, cells, letter)    put that cell on each (r, c) of pid's board
    row_cells(r, skip) / col_cells(c, skip)   the (r, c) of a row / column, minus `skip`

Letters: "#" blue blank, "C"/"A"/"S"/"R"/"E" that symbol on a blue tile, lowercase = that symbol
on a grey tile ("+" grey blank), "G" a goblin tile, "." empty.
"""

import importlib
import random

GAME = "block-blast"
Match = importlib.import_module(f"games.{GAME}.logic.match").Match
board = importlib.import_module(f"games.{GAME}.logic.board")
symbols = importlib.import_module(f"games.{GAME}.logic.symbols")

SETTINGS = {"health": 10, "market": "conveyor", "conveyorSize": 5, "costSize": 10,  # the lobby's defaults
            "packs": ["base", "chapel", "goblin", "siege"]}


def new_match(players=2, **settings):
    names = {f"p{i + 1}": f"Player {i + 1}" for i in range(players)}
    return Match(names, {**SETTINGS, **settings}, rng=random.Random(1))


def give(match, pid, card_id):
    """Put a fresh instance of card_id into pid's hand; returns its uid."""
    card = match.seats[pid].deck.make(card_id)
    match.seats[pid].hand.append(card)
    return card["uid"]


def cell(letter):
    if letter == "#":
        return ("blue", None)
    if letter == "+":
        return ("grey", None)
    if letter == "G":
        return ("goblin", None)
    if letter.islower():
        return ("grey", symbols.BY_CODE[letter.upper()].name)
    return ("blue", symbols.BY_CODE[letter].name)


def letter_of(c):
    if c is None:
        return "."
    tile, symbol = c
    code = symbols.SYMBOLS[symbol].code if symbol else None
    if tile == "goblin":
        return "G"
    if tile == "grey":
        return code.lower() if code else "+"
    return code or "#"


def rows(grid):
    """A board as strings of the letters above ("." empty)."""
    return ["".join(letter_of(c) for c in row) for row in grid]


def fill(match, pid, cells, letter="#"):
    for r, c in cells:
        match.seats[pid].board[r][c] = cell(letter)


def row_cells(r, skip=()):
    return [(r, c) for c in range(board.SIZE) if c not in skip]


def col_cells(c, skip=()):
    return [(r, c) for r in range(board.SIZE) if r not in skip]
