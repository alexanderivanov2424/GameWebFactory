"""Validating what players send. Each helper raises LobbyError, whose message the player sees.

    whole_number(value, label, low, high)            int clamped to [low, high]
    whole_number(value, label, low, high, clamp=False)  int, or LobbyError if out of range
    one_of(value, choices, message)                  value if it's in choices
    cell(value, size, message)                       [row, col] on a size x size board -> (row, col)
    clean_text(value, limit)                         stripped string cut to limit ("" if not a string)

Check types with `type(x) is int` (bool is an int subclass), as these helpers do.
"""

from server.utils import clean_text  # noqa: F401  (re-exported for games)


class LobbyError(Exception):
    """Raise to reject a request. The message is shown to the player who sent it."""


def whole_number(value, label, low=None, high=None, clamp=True):
    if type(value) is not int:
        raise LobbyError(f"{label} must be a whole number.")
    if clamp:
        if low is not None:
            value = max(value, low)
        if high is not None:
            value = min(value, high)
        return value
    if (low is not None and value < low) or (high is not None and value > high):
        raise LobbyError(f"{label} must be from {low} to {high}.")
    return value


def one_of(value, choices, message):
    if value not in choices:
        raise LobbyError(message)
    return value


def cell(value, size, message="That's not a square on the board."):
    if (
        isinstance(value, list) and len(value) == 2
        and all(type(v) is int and 0 <= v < size for v in value)
    ):
        return value[0], value[1]
    raise LobbyError(message)
