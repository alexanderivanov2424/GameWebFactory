"""Host settings declared once: validated on the server, drawn by the client.

A game lists its settings in the class attribute SETTINGS; LobbyGame then provides
default_settings() and clean_settings() from it, and sends the list to clients as
state.settingsSpec, which AppLobbyUI.settingsForm (web/gamekit/lobby-ui.js) turns into inputs.

    from gamekit import Int, LobbyGame

    class Game(LobbyGame):
        SETTINGS = {
            "boardSize": Int("Board size", default=3, low=3, high=10),
            "winLength": Int("Pieces in a row to win", default=3, low=3, high="boardSize"),
            "wallChance": Int("Wall chance", default=15, low=0, high=100, suffix="%"),
        }

Int(label, default, low, high, suffix="", hint="")
    A whole number. Anything else is rejected with "<label> must be a whole number.";
    out-of-range values are clamped. `low`/`high` may name another setting (a key in
    SETTINGS declared *before* this one), e.g. high="boardSize": the bound follows that
    setting's value, on the server and in the client's input.

Settings missing from an update keep their current value. For rules that span several
settings beyond a linked bound, override clean_settings, call super().clean_settings(settings),
then adjust or raise LobbyError.
"""

from gamekit.validate import whole_number


class Int:
    def __init__(self, label, default, low, high, suffix="", hint=""):
        self.label = label
        self.default = default
        self.low = low
        self.high = high
        self.suffix = suffix
        self.hint = hint

    def bounds(self, values):
        def bound(b):
            return values[b] if isinstance(b, str) else b

        return bound(self.low), bound(self.high)

    def clean(self, value, values):
        low, high = self.bounds(values)
        return whole_number(value, self.label, low, high)

    def spec(self, key):
        spec = {"key": key, "type": "int", "label": self.label, "suffix": self.suffix, "hint": self.hint}
        for name, bound in (("min", self.low), ("max", self.high)):
            spec[name + "From" if isinstance(bound, str) else name] = bound
        return spec


def defaults(fields):
    """The default settings: {key: default}, with linked bounds applied."""
    return clean(fields, {}, {})


def clean(fields, settings, current):
    """Validate `settings` (from the host) against `fields`; missing keys keep `current` values."""
    values = {}
    for key, field in fields.items():
        value = settings.get(key, current.get(key, field.default))
        values[key] = field.clean(value, values)
    return values


def spec(fields):
    """JSON-friendly description of the fields, sent to clients as state.settingsSpec."""
    return [field.spec(key) for key, field in fields.items()]
